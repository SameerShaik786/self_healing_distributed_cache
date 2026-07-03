# Self-Healing Distributed Cache - Complete Architecture Guide

## System Overview

A **distributed cache system** with 3 nodes that:
- Store key-value pairs across multiple nodes
- Self-heal from node failures  
- Maintain data consistency across the cluster
- Automatically rebalance when nodes join/leave

```
┌─────────────────────────────────────────────────────────────┐
│                    CACHE CLUSTER (3 NODES)                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   NODE A     │  │   NODE B     │  │   NODE C     │       │
│  │ (Port 5001)  │  │ (Port 5002)  │  │ (Port 5003)  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│       │                 │                 │                   │
│       │ HTTP REST       │ HTTP REST       │                   │
│       │ API             │ API             │                   │
│       └─────────────────┼─────────────────┘                   │
│                         │                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  In-Memory   │  │  In-Memory   │  │  In-Memory   │       │
│  │   Cache      │  │   Cache      │  │   Cache      │       │
│  │  (Dict)      │  │  (Dict)      │  │  (Dict)      │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│       │                 │                 │                   │
│       ↓                 ↓                 ↓                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   SQLite     │  │   SQLite     │  │   SQLite     │       │
│  │   Database   │  │   Database   │  │   Database   │       │
│  │  node_a.db   │  │  node_b.db   │  │  node_c.db   │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ gRPC Communication (Inter-node replication)            │ │
│  │  Port 50051 ←→ Port 50052 ←→ Port 50053              │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase Breakdown

### Phase 1: Single-Node Foundation
**Goal**: Single cache node with persistence

**Components Built**:
- **FastAPI HTTP Server**: REST API for cache operations
  - `GET /cache/get?key=foo` → Returns value or 404
  - `PUT /cache/put` → Stores key-value pair
  - `DELETE /cache/delete?key=foo` → Removes key
  
- **In-Memory Cache Layer**: Python dictionary for fast access
  - Stores: `{key: (value, version)}`
  - Read hits from memory first (~microseconds)
  - Falls back to database on miss
  
- **SQLite Database**: Persistent storage with SQLAlchemy ORM
  - Table: `cache_entries(id, key, value, created_at, updated_at, expires_at, version, node_id, is_deleted)`
  - One `.db` file per node
  
- **Docker Containerization**: Multi-container orchestration
  - 3 services: `cache_node_a`, `cache_node_b`, `cache_node_c`
  - Custom Docker network: `cache-network`
  - Volume mounts for database persistence

**Data Flow**:
```
HTTP Request (GET key_foo)
    ↓
FastAPI Route Handler
    ↓
Check in-memory cache
    ├─ Hit → Return value (version known)
    └─ Miss → Query SQLite
              ├─ Found → Return + update memory cache
              └─ Not Found → Return 404
```

**Why This Design**:
- In-memory cache provides microsecond latency for frequently accessed keys
- Database ensures durability across restarts
- Docker allows easy scaling to 3 nodes
- Single node foundation before adding distributed complexity

---

### Phase 2: Failure Detection
**Goal**: Cluster awareness and health monitoring

**Components Added**:

1. **gRPC Service** (`cache_node/protos/cache.proto`):
   - **Heartbeat**: Each node sends "I'm alive" message every 5 seconds
   - **Get/Put/Delete**: Operations replicate to peer nodes over gRPC
   - Binary protocol = faster than HTTP + automatic connection pooling

2. **NodeRegistry** (`cache_node/app/services/node_registry.py`):
   - Maps node_id → {address, status, last_heartbeat_time, missed_pings_count}
   - `mark_alive()`: Reset missed_pings when heartbeat received
   - `mark_dead()`: Node is down after 3 missed heartbeats (15 seconds)
   - `get_peer_nodes()`: Returns list of currently alive nodes

3. **Heartbeat Health Check Loop**:
   ```
   Every 5 seconds:
     FOR each peer node:
       SEND heartbeat via gRPC
       ON success: mark_alive()
       ON timeout: increment_missed_ping()
       IF missed_pings > 3: mark_dead()
   ```

**Why This Design**:
- 5-second heartbeat interval balances responsiveness vs. network overhead
- 3-miss threshold = 15 second failure detection time (reasonable for detecting dead nodes)
- NodeRegistry is the "source of truth" for cluster topology
- gRPC provides efficient binary serialization for inter-node communication

---

### Phase 3: Quorum & Consistency
**Goal**: Data consistency across replicas using quorum voting

**Problem Solved**: What if 2 nodes get value X and 1 gets value Y? Which is correct?

**Solution: Last-Write-Wins (LWW) Versioning**

1. **VersionVector** (`cache_node/app/services/version_vector.py`):
   - Tuple: `(timestamp, node_id)`
   - Comparison logic:
     ```python
     if local.timestamp > remote.timestamp:
         return "newer"  # Local write happened after
     elif local.timestamp == remote.timestamp:
         if local.node_id > remote.node_id:
             return "newer"  # Tie-breaker: higher node_id wins
     else:
         return "older"
     ```
   - **Why this works**: Latest timestamp = most recent write. Node_id tie-break ensures deterministic outcome.

2. **QuorumManager** (`cache_node/app/services/quorum_manager.py`):
   - Every write operation tracked with unique `operation_id`
   - For PUT/DELETE: Node sends operation to 2 peer nodes
   - **Quorum satisfied** when: 2/3 nodes acknowledge (local + 2 peers)
   - If quorum not met within 5 seconds → return 503 (service unavailable)
   
   ```
   PUT request to node_a:
     │
     ├─→ Create write operation with id=uuid
     │
     ├─→ Store locally with version=(now, node_a)
     │
     ├─→ Send to node_b via gRPC (async)
     │   └─→ node_b replies with ack + its version
     │
     ├─→ Send to node_c via gRPC (async)
     │   └─→ node_c replies with ack + its version
     │
     └─→ Wait up to 5 seconds for 2 total acks
         ├─ Got 2 acks → Return 200 OK (quorum met)
         ├─ Got 1 ack → Return 503 Service Unavailable
         └─ Timeout → Return 503
   ```

3. **Storage with Versioning** (`cache_node/app/services/storage_service.py`):
   - Each entry in database has `version=(timestamp, node_id)`
   - On receive from peer: Compare versions
   - **Keep newer version**: `if peer_version.timestamp > local_version.timestamp`
   - **Update both memory + database** to stay in sync

**Why This Design**:
- Quorum voting ensures write acknowledgment from majority
- LWW resolution prevents inconsistent state (all nodes converge to same value)
- Timestamp + node_id is deterministic (no user choice, reproducible)
- 5-second timeout prevents hanging requests

**Example Consistency Resolution**:
```
Timeline:
T=100ms: node_a writes "value_v1" (version: 100, node_a)
T=105ms: node_b writes "value_v2" (version: 105, node_b)
T=110ms: All nodes have both versions

Resolution: 105 > 100 → ALL nodes keep "value_v2"
Result: Consistency achieved ✓
```

---

### Phase 4: Consistent Hashing & Rebalancing
**Goal**: Distribute keys evenly; minimize data movement on node changes

**Problem**: With N nodes, which node stores which key? And when a node joins/leaves, minimize key migration.

**Solution: Consistent Hash Ring**

1. **Hash Ring Concept**:
   ```
   Hash all keys and all nodes onto a ring [0, 2^32):
   
   Keys: key_1=0x2341, key_2=0x9234, key_3=0xabcd
   Nodes: node_a=0x1000, node_b=0x5000, node_c=0x8000
   
   Ring (0 → 2^32):
     0x0 ──────── node_a ──────── 0x5000 ──────── 0x8000 ──────── 2^32
               ↓ key_1(0x2341)   ↓ key_2(0x9234) ↓ key_3(0xabcd)
   
   Assigned to:
   - key_1 → node_a (first node clockwise from hash)
   - key_2 → node_b
   - key_3 → node_c
   ```

2. **Virtual Nodes** (160 per physical node):
   - Prevents "hot spots" where one node gets too many keys
   - With 160 virtual nodes × 3 physical nodes = even distribution
   - Calculate: `hash(node_a + "_vnode_0"), hash(node_a + "_vnode_1"), ..., hash(node_a + "_vnode_159")`

3. **Replica Strategy** (2 replicas per key):
   ```
   For key_foo:
   1. Find primary node (hash of key on ring)
   2. Find replica_1: next node clockwise
   3. Find replica_2: next node clockwise from replica_1
   
   Result: key stored on 3 nodes for 2 replicas + 1 backup
   ```

4. **Rebalancing on Node Join**:
   ```
   Before: 3 nodes (a, b, c)
   After: 4 nodes (a, b, c, d)
   
   Effect: ~50% of key-replica pairs move to new node (expected with 2 replicas)
   
   Example:
   - key_1 was: a→b→c
   - Now: d→b→c (moved from a to d)
   
   Migration: async copy key_1 from a→d, then delete from a
   ```

**Why This Design**:
- Consistent hash = minimal key movement (only ~1/N of keys move per node change)
- Virtual nodes = even load distribution
- Replicas = fault tolerance (key not lost if one node dies)
- Deterministic algorithm = all nodes independently calculate same assignments

---

### Phase 5: Observability & Finalization
**Goal**: Monitor performance; understand system behavior; document everything

**Components Added**:

1. **Prometheus Metrics** (`cache_node/app/services/metrics_service.py`):
   - **Counters** (ever-increasing):
     - `cache_hits_total`: Times key was found
     - `cache_misses_total`: Times key not found
     - `replication_success_total`: Successful replication operations
     - `replication_failed_total`: Failed replication operations
     - `quorum_met_total`: Write operations that achieved quorum
     - `quorum_failed_total`: Write operations that failed quorum
   
   - **Histograms** (latency distribution):
     - `cache_get_duration_seconds`: How long GET takes
     - `cache_put_duration_seconds`: How long PUT takes
     - `cache_delete_duration_seconds`: How long DELETE takes
     - `replication_latency_seconds`: Network latency to peers
   
   - **Gauges** (point-in-time values):
     - `active_nodes`: Count of alive nodes right now
     - `memory_cache_entries`: Number of keys in RAM
     - `rebalancing_in_progress`: Is rebalancing happening (0/1)
     - `rebalancing_keys_moved_total`: How many keys moved so far

   Example metrics output:
   ```
   # HELP cache_hits_total Total cache hits
   # TYPE cache_hits_total counter
   cache_hits_total{node_id="node_a"} 1523.0
   
   # HELP cache_get_duration_seconds Time taken to get a key
   # TYPE cache_get_duration_seconds histogram
   cache_get_duration_seconds_bucket{le="0.001",node_id="node_a"} 892.0
   cache_get_duration_seconds_bucket{le="0.005",node_id="node_a"} 1401.0
   cache_get_duration_seconds_sum{node_id="node_a"} 5.234
   cache_get_duration_seconds_count{node_id="node_a"} 1523.0
   ```

2. **Structured JSON Logging** (`cache_node/app/services/logging_setup.py`):
   - Every log is valid JSON with:
     - `timestamp`: ISO 8601 format (e.g., "2026-07-03T10:30:45.123Z")
     - `level`: DEBUG, INFO, WARNING, ERROR
     - `logger`: Component name (e.g., "cache_node.app.routes")
     - `message`: Human-readable description
     - `node_id`: Which node generated this log
     - `context`: Extra data relevant to the event
   
   Example:
   ```json
   {
     "timestamp": "2026-07-03T10:30:45.123Z",
     "level": "INFO",
     "logger": "cache_node.app.routes",
     "message": "PUT request received",
     "node_id": "node_a",
     "context": {
       "key": "user:1234",
       "value_size_bytes": 512,
       "operation_id": "op-abc-def"
     }
   }
   ```
   
   **Why JSON**: Logs are queryable. Tools like ELK Stack or Loki can parse and search:
   - `jq '.context.operation_id' logs.jsonl` → Find all logs for operation
   - `grep 'level.*ERROR' logs.jsonl` → Find all errors
   - Dashboards can visualize trends

3. **Performance Benchmarking** (`benchmarks/benchmark.py`):
   ```
   Measures:
   - Throughput: GET 2,500 ops/sec
   - Latency p50: 0.4ms (median)
   - Latency p99: 2.1ms (99th percentile)
   
   Usage:
   $ python benchmarks/benchmark.py
   
   Output:
   ================================================================================
   Benchmark: GET Operations
   ================================================================================
   Total Operations: 500
   Total Time: 0.20s
   Throughput: 2500.00 ops/sec
   
   Latency Statistics:
     Average: 0.40ms
     P50 (median): 0.38ms
     P95: 0.85ms
     P99: 2.10ms
   ```

**Metrics Endpoint**:
```
GET http://localhost:5001/metrics
→ Returns Prometheus-format metrics (used by Prometheus scraper)
```

---

## Request Flow - Complete Walkthrough

### Scenario: PUT request arrives at node_a

```
PUT /cache/put
Body: {"key": "user:1234", "value": {"name": "Alice", "age": 30}}

┌──────────────────────────────────────────────────────┐
│ 1. Request arrives at node_a HTTP server (port 5001)  │
│    → FastAPI route handler: async def cache_put()    │
└──────────────────────────────────────────────────────┘
          ↓

┌──────────────────────────────────────────────────────┐
│ 2. Logging: Log incoming request                      │
│    logger.info("PUT received", context={              │
│      "key": "user:1234", "operation_id": "op-xyz"   │
│    })                                                  │
└──────────────────────────────────────────────────────┘
          ↓

┌──────────────────────────────────────────────────────┐
│ 3. Metrics: Start latency timer                        │
│    start_time = time.time()                           │
└──────────────────────────────────────────────────────┘
          ↓

┌──────────────────────────────────────────────────────┐
│ 4. Storage: Save locally with version                │
│    version = (now_timestamp, "node_a")               │
│    storage_engine.put(key, value, version)           │
│    → Updates in-memory cache: _memory_cache[key] =   │
│                   (value, version)                    │
│    → Updates database: INSERT cache_entries(...)     │
└──────────────────────────────────────────────────────┘
          ↓

┌──────────────────────────────────────────────────────┐
│ 5. Replication: Send to peers (gRPC - async)         │
│    Consistent hash determines replicas:              │
│      replicas = hash_ring.get_replicas("user:1234")  │
│      → [node_b, node_c]                              │
│                                                       │
│    FOR each replica_node in [node_b, node_c]:       │
│      Send: gRPC PutRequest(                          │
│        key="user:1234",                              │
│        value=...,                                     │
│        version=(timestamp, "node_a"),                │
│        operation_id="op-xyz"                         │
│      )                                                │
│      AWAIT response with timeout=1000ms              │
└──────────────────────────────────────────────────────┘
          ↓ (Parallel: node_b and node_c process)

┌──────────────────────────────────────────────────────┐
│ Node_b receives PUT:                                  │
│   1. Receive gRPC request                             │
│   2. Extract version from request                     │
│   3. Query database: SELECT current_version          │
│   4. Compare: remote_version vs local_version        │
│      if remote > local:                              │
│        Update local entry                            │
│        Update memory cache                           │
│   5. Send ACK response                                │
│                                                       │
│ Same for node_c                                       │
└──────────────────────────────────────────────────────┘
          ↓

┌──────────────────────────────────────────────────────┐
│ 6. Quorum Check: Wait for acks                        │
│    quorum_manager.wait_for_quorum("op-xyz", timeout=5s) │
│                                                       │
│    Tracking:                                         │
│    - Self (node_a): Always counts as 1 ack          │
│    - node_b ack: ✓ (received at 50ms)              │
│    - node_c ack: ✓ (received at 65ms)              │
│                                                       │
│    Total acks: 3 ≥ 2 (quorum met!) → return True    │
└──────────────────────────────────────────────────────┘
          ↓

┌──────────────────────────────────────────────────────┐
│ 7. Metrics: Record success                           │
│    metrics.quorum_met("node_a") → counter++          │
│    metrics.replication_success("node_a", "put")      │
│    duration = time.time() - start_time               │
│    metrics.record_latency(put_latency, "node_a",     │
│                          start_time)                  │
│    → Histogram bucket for 0.052s → bucket++          │
└──────────────────────────────────────────────────────┘
          ↓

┌──────────────────────────────────────────────────────┐
│ 8. Response: Return 200 OK                            │
│    {                                                  │
│      "status": "success",                            │
│      "key": "user:1234",                             │
│      "version": "2026-07-03T10:30:45.052Z-node_a",  │
│      "replication_time_ms": 65                       │
│    }                                                  │
└──────────────────────────────────────────────────────┘
```

---

## Consistency Guarantees

### Write Consistency: Strong Consistency (Quorum)
- All 3 nodes have identical value before returning 200 OK
- If quorum fails (< 2 nodes ack), request fails with 503
- **Tradeoff**: Latency increases (wait for network round-trips)

### Read Consistency: Eventual Consistency
- GET reads from local node (fast)
- If local is stale, other nodes are fresher
- But will eventually become consistent via heartbeat replication
- **Tradeoff**: Temporarily stale reads possible, but fast (1ms)

### Failure Scenarios Handled

| Scenario | Behavior |
|----------|----------|
| Node_b dies during PUT | node_a + node_c = 2 acks → quorum met → 200 OK |
| Node_b & node_c die during PUT | node_a only = 1 ack → quorum failed → 503 |
| Network partition (a,b vs c) | Depends on which is smaller. 2 nodes in a partition proceed |
| Duplicate PUT request | operation_id prevents duplicate writes |
| Clock skew (timestamps differ) | node_id tie-break ensures deterministic winner |

---

## Production Deployment Checklist

- [ ] Configure 3 nodes with unique NODE_ID, GRPC_PORT env vars
- [ ] Set up shared network (Docker network or same VPC)
- [ ] Configure Prometheus scraper to collect `/metrics` every 15 seconds
- [ ] Set up ELK Stack or Loki for log aggregation
- [ ] Alert on `quorum_failed_total > threshold`
- [ ] Alert on `active_nodes < 2`
- [ ] Monitor `cache_get_duration_seconds_bucket` (p99 latency)
- [ ] Run `python benchmarks/benchmark.py` monthly to track performance regression
- [ ] Set up log rotation (JSON logs grow fast)

---

## Summary Table

| Layer | Technology | Purpose |
|-------|-----------|---------|
| HTTP API | FastAPI + Uvicorn | REST endpoints for cache ops |
| gRPC | gRPC + Protocol Buffers | Inter-node replication |
| Storage | SQLAlchemy + SQLite | Persistent key-value store |
| Caching | Python dict | In-memory for fast reads |
| Health | Heartbeat loop + NodeRegistry | Failure detection |
| Consistency | Version vectors + quorum | Data consensus |
| Distribution | Consistent hash | Key assignment to nodes |
| Rebalancing | Virtual nodes + RebalancingManager | Handle node changes |
| Metrics | Prometheus | Performance monitoring |
| Logging | JSON formatter | Structured debugging |

---

**Total Lines of Code**: ~2,500 LOC (services, routes, tests, protos)
**Languages**: Python 3.11+, Protocol Buffers, SQL
**Docker Images**: 1 image × 3 containers
**Database Size**: ~1MB per node (depending on entries)
**Startup Time**: ~2 seconds per node
**Memory Footprint**: ~50MB per node (in-memory cache + gRPC)
