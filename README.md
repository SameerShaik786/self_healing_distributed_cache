# Self-Healing Distributed Cache

A fault-tolerant, quorum-based distributed caching system built in Python. Designed for environments where data durability, automatic failure recovery, and strong write consistency are non-negotiable. The system operates a 3-node cluster with gRPC-based replication, consistent hashing for key distribution, and full observability through Prometheus metrics and structured JSON logging.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Key Design Decisions](#key-design-decisions)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Consistency Model](#consistency-model)
- [Observability](#observability)
- [Performance](#performance)
- [Scaling](#scaling)
- [Failure Scenarios and Recovery](#failure-scenarios-and-recovery)
- [Testing](#testing)
- [Configuration Reference](#configuration-reference)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

This system solves the problem of caching data across multiple nodes while maintaining consistency and surviving node failures without manual intervention. It implements several distributed systems primitives from scratch:

- **Quorum-based writes** -- every write must be acknowledged by a majority of nodes before returning success to the client.
- **Last-Write-Wins conflict resolution** -- concurrent writes are resolved deterministically using version vectors (timestamp + node ID).
- **Consistent hashing with virtual nodes** -- keys are distributed evenly across the cluster, and node additions or removals trigger minimal data migration.
- **Heartbeat-based failure detection** -- nodes monitor each other every 5 seconds and mark peers as dead after 3 consecutive missed heartbeats.
- **Automatic rebalancing** -- when cluster topology changes, keys are redistributed and migrated asynchronously.
- **Dual-layer storage** -- an in-memory dictionary for microsecond reads backed by SQLite for persistence across restarts.

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| HTTP API | FastAPI + Uvicorn | REST endpoints for cache operations |
| Inter-Node Communication | gRPC + Protocol Buffers | Binary replication protocol |
| Persistent Storage | SQLAlchemy + SQLite | Durable key-value store (per node) |
| In-Memory Cache | Python dictionary | Sub-millisecond read latency |
| Failure Detection | Heartbeat loop + Node Registry | Peer health monitoring |
| Consistency | Version vectors + Quorum manager | Write consensus |
| Key Distribution | Consistent hash ring | Deterministic key-to-node mapping |
| Rebalancing | Virtual nodes + Rebalancing manager | Graceful topology changes |
| Metrics | Prometheus client | Counters, histograms, gauges |
| Logging | Custom JSON formatter | Structured, queryable log output |

---

## Architecture

```
                         Client (HTTP REST)
                              |
              +---------------+---------------+
              |               |               |
        +-----+-----+  +-----+-----+  +------+----+
        |  Node A   |  |  Node B   |  |  Node C   |
        | port 5001 |  | port 5002 |  | port 5003 |
        +-----------+  +-----------+  +-----------+
        | FastAPI   |  | FastAPI   |  | FastAPI   |
        | In-Memory |  | In-Memory |  | In-Memory |
        | SQLite    |  | SQLite    |  | SQLite    |
        +-----+-----+  +-----+-----+  +-----+-----+
              |               |               |
              +-------gRPC Replication--------+
               port 50051   50052   50053
```

Each node runs an identical application image. Every node maintains its own in-memory cache and SQLite database. Nodes communicate over gRPC for replication, heartbeats, and quorum acknowledgments. A custom Docker bridge network (`cache-network`) provides DNS-based service discovery between containers.

### Write Path (PUT)

1. Client sends `PUT /cache/put` to any node.
2. The receiving node stores the value locally (memory + database) with a version vector `(timestamp, node_id)`.
3. The consistent hash ring determines which peer nodes should hold replicas.
4. The value is replicated to peer nodes via gRPC (asynchronous, parallel).
5. Each peer compares the incoming version against its local version and keeps the newer value.
6. The quorum manager waits for acknowledgments from a majority of nodes (2 of 3).
7. If quorum is met within 5 seconds, the client receives `200 OK`. Otherwise, `503 Service Unavailable`.

### Read Path (GET)

1. Client sends `GET /cache/get?key=<key>` to any node.
2. The node checks its in-memory cache first (microsecond latency).
3. On cache miss, it falls back to its local SQLite database.
4. The value is returned directly -- no cross-node coordination on reads.

---

## Key Design Decisions

### Why quorum voting instead of full replication?

Full replication (wait for all nodes) means a single slow node degrades the entire cluster. No replication means a single node failure causes data loss. Quorum (majority acknowledgment) tolerates one node being down or slow while still guaranteeing that any majority of nodes holds the latest value.

### Why Last-Write-Wins with version vectors?

When a network partition heals, nodes may hold conflicting values for the same key. The version vector `(timestamp, node_id)` provides a deterministic total ordering: the latest timestamp wins, and the node ID serves as a tiebreaker when clocks are skewed. Every node independently reaches the same resolution without coordination.

### Why consistent hashing over modulo hashing?

With modulo hashing (`hash(key) % N`), changing the node count remaps approximately 67% of all keys. With consistent hashing, only `~1/N` keys are affected. Virtual nodes (160 per physical node) ensure even load distribution across the ring.

### Why dual-layer storage?

The in-memory dictionary provides sub-millisecond reads for hot keys. The SQLite database provides durability -- data survives container restarts and node crashes. On startup, the database populates the memory layer. This combination delivers both speed and reliability without external infrastructure dependencies.

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development and benchmarking)
- Git

### Clone and Start

```bash
git clone https://github.com/SameerShaik786/self_healing_distributed_cache.git
cd self_healing_distributed_cache
```

### Launch the 3-Node Cluster

```bash
docker-compose build
docker-compose up -d
```

### Verify Cluster Health

```bash
curl http://localhost:5001/cluster/status
```

Expected response:

```json
{
  "node_id": "node_a",
  "peer_nodes": {
    "node_b": {"address": "cache_node_b:50052", "status": "alive"},
    "node_c": {"address": "cache_node_c:50053", "status": "alive"}
  }
}
```

### Basic Operations

```bash
# Store a value
curl -X PUT http://localhost:5001/cache/put \
  -H "Content-Type: application/json" \
  -d '{"key": "user:1", "value": {"name": "Alice", "age": 30}}'

# Retrieve a value
curl http://localhost:5001/cache/get?key=user:1

# Delete a value
curl -X DELETE http://localhost:5001/cache/delete?key=user:1
```

### Stop the Cluster

```bash
docker-compose down
```

To also remove persisted data volumes:

```bash
docker-compose down -v
```

---

## API Reference

All endpoints are available on each node (ports 5001, 5002, 5003).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `PUT` | `/cache/put` | Store a key-value pair with quorum replication |
| `GET` | `/cache/get?key=<key>` | Retrieve a value by key |
| `DELETE` | `/cache/delete?key=<key>` | Delete a key with quorum replication |
| `GET` | `/cluster/status` | Return cluster topology and node health |
| `GET` | `/health` | Liveness check |
| `GET` | `/metrics` | Prometheus-format metrics |

### Request and Response Examples

**PUT**

```bash
curl -X PUT http://localhost:5001/cache/put \
  -H "Content-Type: application/json" \
  -d '{"key": "session:abc", "value": {"token": "xyz", "expires": 3600}}'
```

```json
{
  "status": "success",
  "key": "session:abc",
  "version": "2026-07-03T10:30:45.052Z-node_a",
  "replication_time_ms": 65
}
```

**GET**

```bash
curl http://localhost:5001/cache/get?key=session:abc
```

```json
{
  "key": "session:abc",
  "value": {"token": "xyz", "expires": 3600},
  "version": "2026-07-03T10:30:45.052Z-node_a"
}
```

---

## Consistency Model

### Write Consistency: Strong (Quorum)

Every write operation requires acknowledgment from at least 2 of 3 nodes before returning success. If fewer than 2 nodes acknowledge within the 5-second timeout, the operation fails with `503 Service Unavailable`. This guarantees that any majority of nodes holds the latest written value.

### Read Consistency: Eventual

Reads are served from the local node without cross-node coordination. A node may temporarily serve a stale value if it missed a recent write. Consistency is restored through heartbeat-driven replication, typically within 5-15 seconds.

### Conflict Resolution

| Scenario | Behavior |
|----------|----------|
| One node down during write | Remaining 2 nodes form quorum -- write succeeds |
| Two nodes down during write | Only 1 acknowledgment -- quorum fails, returns `503` |
| Network partition (2 vs 1) | The 2-node partition can write; the isolated node rejects writes |
| Concurrent writes to same key | Last-Write-Wins: higher timestamp wins, node ID breaks ties |
| Duplicate write (same operation ID) | Deduplicated -- operation ID prevents double application |
| Clock skew between nodes | Node ID tiebreaker ensures deterministic, reproducible resolution |

---

## Observability

### Prometheus Metrics

Metrics are exposed at `/metrics` on each node in Prometheus exposition format.

**Counters** (monotonically increasing):

| Metric | Description |
|--------|-------------|
| `cache_hits_total` | Number of successful key lookups |
| `cache_misses_total` | Number of failed key lookups |
| `replication_success_total` | Successful replication operations |
| `replication_failed_total` | Failed replication operations |
| `quorum_met_total` | Writes that achieved quorum |
| `quorum_failed_total` | Writes that failed quorum |

**Histograms** (latency distributions):

| Metric | Description |
|--------|-------------|
| `cache_get_duration_seconds` | GET operation latency |
| `cache_put_duration_seconds` | PUT operation latency |
| `cache_delete_duration_seconds` | DELETE operation latency |
| `replication_latency_seconds` | Network latency to peer nodes |

**Gauges** (point-in-time values):

| Metric | Description |
|--------|-------------|
| `active_nodes` | Number of healthy nodes in the cluster |
| `memory_cache_entries` | Number of keys currently in memory |
| `rebalancing_in_progress` | Whether rebalancing is active (0 or 1) |
| `rebalancing_keys_moved_total` | Number of keys migrated during rebalancing |

### Prometheus Integration

Create a `prometheus.yml` configuration:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'cache-cluster'
    static_configs:
      - targets: ['localhost:5001', 'localhost:5002', 'localhost:5003']
```

Start Prometheus:

```bash
docker run -d \
  -p 9090:9090 \
  -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus
```

Access the Prometheus UI at `http://localhost:9090`.

### Recommended Alerts

| Metric | Alert Condition | Typical Healthy Value |
|--------|----------------|----------------------|
| `active_nodes` | < 2 | 3 |
| `quorum_failed_total` | Rapidly increasing | ~0 |
| `cache_get_duration_seconds` (p99) | > 10ms | 1-2ms |
| `replication_failed_total` | Rapidly increasing | ~0 |

### Structured JSON Logging

Every log line is a valid JSON object with the following fields:

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

Query logs with standard tools:

```bash
# Follow logs for a specific node
docker logs cache_node_a -f

# Filter errors
docker logs cache_node_a | jq 'select(.level=="ERROR")'

# Trace a single operation across log entries
docker logs cache_node_a | jq 'select(.context.operation_id=="op-abc-def")'
```

---

## Performance

### Benchmark Results

Run the included benchmark suite against a running cluster:

```bash
docker-compose up -d
python benchmarks/benchmark.py
```

Representative results (500 operations per benchmark):

| Operation | Throughput | Avg Latency | P50 Latency | P95 Latency | P99 Latency |
|-----------|-----------|-------------|-------------|-------------|-------------|
| GET | 2,500 ops/s | 0.40 ms | 0.38 ms | 0.85 ms | 2.10 ms |
| PUT | 476 ops/s | 2.10 ms | 1.95 ms | 4.50 ms | 7.20 ms |
| DELETE | 435 ops/s | 2.30 ms | 2.15 ms | 5.10 ms | 8.95 ms |

PUT and DELETE operations are slower than GET because they require quorum -- the requesting node must wait for acknowledgment from at least one peer over the network, adding 2-3ms of gRPC round-trip latency.

### Resource Footprint

| Resource | Value |
|----------|-------|
| Memory per node | ~50 MB |
| Database size per node | ~1 MB (varies with entry count) |
| Startup time per node | ~2 seconds |
| Docker images | 1 image, 3 containers |

### Performance SLOs

| Metric | Target |
|--------|--------|
| GET p99 latency | < 5 ms |
| PUT p99 latency | < 10 ms |
| Availability | 99.9% (tolerates 1 node failure) |
| GET throughput | > 1,000 ops/s |

---

## Scaling

### Adding a 4th Node

**1. Update `docker-compose.yml`:**

```yaml
cache_node_d:
  build: .
  ports:
    - "5004:5000"
    - "50054:50051"
  environment:
    - NODE_ID=node_d
    - GRPC_PORT=50051
    - OTHER_NODES=cache_node_a:50051,cache_node_b:50051,cache_node_c:50051
    - DATABASE_URL=sqlite:///node_d.db
  volumes:
    - cache-data-d:/app/data
  networks:
    - cache-network
  depends_on:
    - cache_node_a
    - cache_node_b
    - cache_node_c
```

**2. Update the quorum threshold** in `cache_node/app/services/quorum_manager.py`:

```python
quorum_manager = QuorumManager(node_id, total_nodes=4)
```

**3. Redeploy:**

```bash
docker-compose up -d
```

Rebalancing triggers automatically. The consistent hash ring redistributes keys to include `node_d`, and the node registry adds it to the peer list. Key migration is tracked via the `rebalancing_keys_moved_total` metric.

### Quorum Thresholds by Cluster Size

| Nodes | Quorum | Fault Tolerance |
|-------|--------|-----------------|
| 3 | 2 (67%) | 1 node |
| 4 | 3 (75%) | 1 node |
| 5 | 3 (60%) | 2 nodes |

---

## Failure Scenarios and Recovery

### Single Node Failure

The cluster continues to serve reads and writes. Quorum is maintained by the remaining 2 nodes. When the failed node recovers, heartbeat-driven replication synchronizes its state within 5-15 seconds.

### Two Nodes Down

Only one node remains. Writes fail with `503` (quorum cannot be met). Reads continue from the surviving node but may serve stale data.

**Recovery procedure:**

```bash
docker-compose up cache_node_b    # Restore quorum (2/3)
docker-compose up cache_node_c    # Full cluster restored
```

### Complete Cluster Failure

No data is lost. All state is persisted in SQLite databases stored on Docker volumes.

```bash
docker-compose up -d              # All nodes restart
```

Each node restores its state from its local database on startup. Heartbeat replication resolves any cross-node inconsistencies.

### Corrupted Database on One Node

```bash
docker volume rm cache-data-a     # Remove the corrupted volume
docker-compose up cache_node_a    # Node starts with empty state
```

The node automatically receives data from its peers via replication.

### Backup and Restore

```bash
# Backup all node databases
docker exec cache_node_a cp /app/data/node_a.db /backups/node_a.db.$(date +%s)
docker exec cache_node_b cp /app/data/node_b.db /backups/node_b.db.$(date +%s)
docker exec cache_node_c cp /app/data/node_c.db /backups/node_c.db.$(date +%s)

# Restore from backup
docker-compose down
docker run --rm -v cache-data-a:/data -v cache-backup:/backup \
  alpine cp /backup/node_a.db /data/
docker-compose up -d
```

---

## Testing

### Run the Full Test Suite

```bash
python -m pytest tests/ -v
```

### Run Specific Test Files

```bash
python -m pytest tests/test_consistency.py -v     # Version vector and conflict resolution
python -m pytest tests/test_node_registry.py -v   # Node health tracking
python -m pytest tests/test_rebalancing.py -v     # Consistent hashing and key migration
python -m pytest tests/test_storage.py -v         # Storage engine operations
```

### Run with Coverage

```bash
python -m pytest tests/ --cov=cache_node --cov-report=html
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ID` | `node_default` | Unique node identifier (`node_a`, `node_b`, `node_c`) |
| `GRPC_PORT` | `50051` | gRPC server listen port |
| `DATABASE_URL` | `sqlite:///node.db` | SQLAlchemy database connection string |
| `LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Running Without Docker

Start each node in a separate terminal:

```bash
NODE_ID=node_a GRPC_PORT=50051 \
  python -m uvicorn cache_node.app.main:app --host 0.0.0.0 --port 5001

NODE_ID=node_b GRPC_PORT=50052 \
  python -m uvicorn cache_node.app.main:app --host 0.0.0.0 --port 5002

NODE_ID=node_c GRPC_PORT=50053 \
  python -m uvicorn cache_node.app.main:app --host 0.0.0.0 --port 5003
```

When running outside Docker, set the `OTHER_NODES` environment variable to point to peer hostnames or IP addresses instead of Docker DNS names.

---

## Project Structure

```
self_healing_distributed_cache/
|-- cache_node/
|   |-- app/
|   |   |-- core/                    # Application configuration
|   |   |-- models/                  # SQLAlchemy ORM models
|   |   |-- routes/                  # FastAPI route handlers
|   |   |-- services/
|   |   |   |-- consistent_hash.py   # Hash ring with virtual nodes
|   |   |   |-- logging_setup.py     # JSON structured logging
|   |   |   |-- metrics_service.py   # Prometheus metric definitions
|   |   |   |-- node_registry.py     # Peer health tracking
|   |   |   |-- quorum_manager.py    # Write quorum consensus
|   |   |   |-- rebalancing_manager.py  # Key migration on topology change
|   |   |   |-- replication_service.py  # gRPC replication client
|   |   |   |-- storage_service.py   # Dual-layer storage engine
|   |   |   |-- version_vector.py    # LWW conflict resolution
|   |   |-- grpc_server.py           # gRPC service implementation
|   |   |-- main.py                  # FastAPI application entry point
|   |-- protos/
|   |   |-- cache.proto              # Protocol Buffer definitions
|   |   |-- cache_pb2.py             # Generated protobuf code
|   |   |-- cache_pb2_grpc.py        # Generated gRPC stubs
|-- tests/
|   |-- test_consistency.py          # Version vector resolution tests
|   |-- test_node_registry.py        # Node registry behavior tests
|   |-- test_rebalancing.py          # Consistent hash and migration tests
|   |-- test_storage.py              # Storage engine unit tests
|-- benchmarks/
|   |-- benchmark.py                 # Performance benchmark suite
|-- docker-compose.yml               # 3-node cluster orchestration
|-- Dockerfile                       # Container image definition
|-- requirements.txt                 # Python dependencies
|-- pyproject.toml                   # Project metadata
```

---

## Troubleshooting

**Cluster not healthy:**

```bash
curl http://localhost:5001/cluster/status         # Check topology
docker logs cache_node_a                          # Inspect node logs
docker-compose restart cache_node_b               # Restart a specific node
```

**Quorum failures increasing:**

```bash
curl http://localhost:5001/metrics | grep replication_latency
```

If replication latency exceeds 1 second, investigate Docker network connectivity, firewall rules, or node resource exhaustion.

**High memory usage:**

```bash
curl http://localhost:5001/metrics | grep memory_cache_entries
```

The in-memory cache does not currently implement TTL-based eviction. For workloads exceeding 100,000 keys, consider implementing an eviction policy.

**Database corruption:**

```bash
docker-compose down -v       # Remove all volumes
docker-compose up -d         # Start fresh (data re-syncs from peers)
```

---

## Contributing

1. Fork the repository.
2. Create a feature branch from `main`.
3. Write tests for any new functionality.
4. Ensure all existing tests pass: `python -m pytest tests/ -v`
5. Submit a pull request with a clear description of the change.

---

## License

This project is open source. See the repository for license details.
