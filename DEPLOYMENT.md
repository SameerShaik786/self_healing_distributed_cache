# Deployment & Operations Guide

## Quick Start (Docker Compose)

### Prerequisites
- Docker and Docker Compose installed
- Python 3.11+ (for benchmarking)
- Git

### Step 1: Clone Repository
```bash
git clone https://github.com/SameerShaik786/self_healing_distributed_cache.git
cd self_healing_distributed_cache
```

### Step 2: Build Docker Images
```bash
docker-compose build
```

### Step 3: Start 3-Node Cluster
```bash
docker-compose up -d
```

Logs will show:
```
cache_node_a  | {"timestamp": "2026-07-03...", "level": "INFO", "message": "Creating database tables"}
cache_node_a  | {"timestamp": "2026-07-03...", "level": "INFO", "message": "gRPC server started on port 50051"}
cache_node_b  | {"timestamp": "2026-07-03...", "level": "INFO", "message": "Creating database tables"}
cache_node_c  | {"timestamp": "2026-07-03...", "level": "INFO", "message": "Creating database tables"}
```

### Step 4: Verify Cluster Health
```bash
curl http://localhost:5001/cluster/status
```

Expected output:
```json
{
  "node_id": "node_a",
  "peer_nodes": {
    "node_b": {"address": "cache_node_b:50052", "status": "alive"},
    "node_c": {"address": "cache_node_c:50053", "status": "alive"}
  }
}
```

### Step 5: Test Cache Operations
```bash
# PUT - Store a key
curl -X PUT http://localhost:5001/cache/put \
  -H "Content-Type: application/json" \
  -d '{"key": "user:1", "value": {"name": "Alice", "age": 30}}'

# GET - Retrieve a key
curl http://localhost:5001/cache/get?key=user:1

# DELETE - Remove a key
curl -X DELETE http://localhost:5001/cache/delete?key=user:1
```

---

## Monitoring & Observability

### Prometheus Metrics
Metrics are available at all nodes:
```bash
curl http://localhost:5001/metrics  # node_a
curl http://localhost:5002/metrics  # node_b
curl http://localhost:5003/metrics  # node_c
```

### Configure Prometheus Scraper
Create `prometheus.yml`:
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

Access Prometheus UI: `http://localhost:9090`

### Key Metrics to Monitor

| Metric | Alert If | Typical Value |
|--------|----------|---------------|
| `active_nodes` | < 2 | 3 |
| `quorum_failed_total` | increasing rapidly | ~0 |
| `cache_get_duration_seconds` (p99) | > 10ms | 1-2ms |
| `replication_failed_total` | increasing rapidly | ~0 |
| `memory_cache_entries` | N/A (informational) | varies |

### JSON Logs
View logs from running container:
```bash
docker logs cache_node_a -f
```

Each line is valid JSON. Pipe to `jq` for querying:
```bash
# Extract error messages
docker logs cache_node_a | jq 'select(.level=="ERROR")'

# Extract all operations and their latency
docker logs cache_node_a | jq 'select(.context.operation_id) | {operation: .context.operation_id, latency_ms: .context.latency_ms}'
```

---

## Running Tests

### Unit Tests (All Phases)
```bash
# Enter virtual environment (if not in container)
source .venv/bin/activate

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_consistency.py -v

# Run with coverage report
python -m pytest tests/ --cov=cache_node --cov-report=html
```

Expected output:
```
tests/test_consistency.py::test_version_vector_newer PASSED
tests/test_consistency.py::test_version_vector_older PASSED
tests/test_node_registry.py::test_node_registry_initialization PASSED
tests/test_rebalancing.py::TestConsistentHash::test_deterministic PASSED
...
============================= 23 passed in 3.70s =============================
```

---

## Performance Benchmarking

### Run Benchmark Suite
```bash
# Ensure cluster is running
docker-compose up -d

# Run benchmarks
python benchmarks/benchmark.py
```

Expected output:
```
============================================================
DISTRIBUTED CACHE SYSTEM - PERFORMANCE BENCHMARK
============================================================
Testing with 500 operations per benchmark

Running GET benchmark...
============================================================
Benchmark: GET Operations
============================================================
Total Operations: 500
Total Time: 0.20s
Throughput: 2500.00 ops/sec

Latency Statistics:
  Average: 0.40ms
  P50 (median): 0.38ms
  P95: 0.85ms
  P99: 2.10ms
  Min: 0.12ms
  Max: 8.50ms

Running PUT benchmark...
============================================================
Benchmark: PUT Operations
============================================================
Total Operations: 500
Total Time: 1.05s
Throughput: 476.19 ops/sec

Latency Statistics:
  Average: 2.10ms
  P50 (median): 1.95ms
  P95: 4.50ms
  P99: 7.20ms

Running DELETE benchmark...
============================================================
Benchmark: DELETE Operations
============================================================
Total Operations: 500
Total Time: 1.15s
Throughput: 434.78 ops/sec

Latency Statistics:
  Average: 2.30ms
  P50 (median): 2.15ms
  P95: 5.10ms
  P99: 8.95ms

============================================================
SUMMARY COMPARISON
============================================================
Operation      Throughput         Avg Latency        P99 Latency
────────────────────────────────────────────────────────────────
GET            2500.00 ops/s      0.40ms             2.10ms
PUT            476.19 ops/s       2.10ms             7.20ms
DELETE         434.78 ops/s       2.30ms             8.95ms
```

**Why PUT/DELETE are slower than GET**:
- GET only reads from local node (1 operation)
- PUT/DELETE must achieve quorum (3 network round-trips)
- Quorum adds ~2-3ms for gRPC latency

### Interpreting Results

**Good performance indicators**:
- GET throughput > 1000 ops/sec ✓
- GET p99 latency < 5ms ✓
- PUT p99 latency < 10ms ✓ (due to network)
- No errors or timeouts ✓

**Performance regression if**:
- GET throughput drops below 500 ops/sec
- Any p99 latency > 50ms
- Quorum failures increase

---

## Scaling to More Nodes

### Add a 4th Node

**Step 1**: Update docker-compose.yml
```yaml
services:
  ...
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

**Step 2**: Update cache_node/app/services/quorum_manager.py
```python
# Change total_nodes from 3 to 4
quorum_manager = QuorumManager(node_id, total_nodes=4)
```

**Quorum recalculation**:
- 3 nodes: need 2/3 acks → 67% majority
- 4 nodes: need 3/4 acks → 75% majority
- 5 nodes: need 3/5 acks → 60% majority (less strict)

**Step 3**: Redeploy
```bash
docker-compose up -d
```

**Step 4**: Rebalancing automatically triggers
- Consistent hash redistributes keys to node_d
- NodeRegistry adds node_d to peer list
- Rebalancing job tracks key migration progress

---

## Troubleshooting

### Cluster Not Healthy
```bash
# Check which nodes are down
curl http://localhost:5001/cluster/status

# View node logs
docker logs cache_node_a
docker logs cache_node_b
docker logs cache_node_c

# Restart specific node
docker-compose restart cache_node_b
```

### Quorum Failures Increasing
```bash
# Check replication latency
curl http://localhost:5001/metrics | grep replication_latency

# If latency > 1 second, network issues
# Solution: Check Docker network, firewall rules, or node resources
```

### Memory Cache Growing Too Large
```bash
# Check memory cache size
curl http://localhost:5001/metrics | grep memory_cache_entries

# If > 100,000 entries, implement TTL or eviction policy
# Currently: All entries kept forever
```

### Database File Corruption
```bash
# SQLite databases stored in volumes
docker volume ls | grep cache-data

# To reset:
docker-compose down -v
docker-compose up -d
```

### High Latency Detected
```bash
# Profile operation latency
curl http://localhost:5001/metrics | grep cache_get_duration

# If histogram buckets cluster at high end (> 0.1s):
# - Check CPU load on nodes: docker stats
# - Check network: docker network inspect cache-network
# - Reduce concurrent requests or scale to more nodes
```

---

## Advanced: Manual Node Configuration

Instead of docker-compose, run nodes individually:

```bash
# Terminal 1: Node A
NODE_ID=node_a GRPC_PORT=50051 python -m uvicorn cache_node.app.main:app --host 0.0.0.0 --port 5001 --reload

# Terminal 2: Node B
NODE_ID=node_b GRPC_PORT=50052 python -m uvicorn cache_node.app.main:app --host 0.0.0.0 --port 5002 --reload

# Terminal 3: Node C
NODE_ID=node_c GRPC_PORT=50053 python -m uvicorn cache_node.app.main:app --host 0.0.0.0 --port 5003 --reload
```

**Note**: Nodes must know about each other. By default, they try to connect to `cache_node_a`, `cache_node_b`, `cache_node_c` hostnames (Docker DNS). For bare metal, update `OTHER_NODES` env var.

---

## Backup & Restore

### Backup Data
```bash
# Backup all databases
docker exec cache_node_a cp /app/data/node_a.db /backups/node_a.db.$(date +%s)
docker exec cache_node_b cp /app/data/node_b.db /backups/node_b.db.$(date +%s)
docker exec cache_node_c cp /app/data/node_c.db /backups/node_c.db.$(date +%s)

# Or use volume snapshots
docker volume create cache-backup
docker run --rm -v cache-data-a:/data -v cache-backup:/backup \
  alpine cp /data/node_a.db /backup/
```

### Restore Data
```bash
# Stop cluster
docker-compose down

# Copy backup file to volume
docker run --rm -v cache-data-a:/data -v cache-backup:/backup \
  alpine cp /backup/node_a.db /data/

# Start cluster
docker-compose up -d
```

---

## Disaster Recovery

### Scenario: 2 Nodes Down
**Current state**: Only node_a alive. Quorum = 1/3 (failed)

**Recovery**:
1. Restart node_b: `docker-compose up cache_node_b`
2. Quorum restored: 2/3 ✓
3. Pending writes resume: `PUT` requests succeed again
4. Wait 5-15 seconds for consistency
5. Restart node_c: `docker-compose up cache_node_c`

### Scenario: Complete Cluster Failure (All 3 Down)
**Data loss**: NO - all data persisted in SQLite databases

**Recovery**:
1. Start cluster: `docker-compose up -d`
2. Wait 5-10 seconds for initialization
3. Check health: `curl http://localhost:5001/cluster/status`
4. Data automatically restored from databases

### Scenario: Corrupted Database
**Detection**: Container exits with error on startup

**Recovery**:
1. Remove volume: `docker volume rm cache-data-a`
2. Restart node: `docker-compose up cache_node_a`
3. Node starts fresh (empty)
4. Data syncs from replicas via heartbeat replication

---

## Configuration Reference

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NODE_ID` | `node_default` | Unique identifier (node_a, node_b, node_c) |
| `GRPC_PORT` | `50051` | gRPC server port (50051, 50052, 50053) |
| `DATABASE_URL` | `sqlite:///node.db` | Database connection string |
| `LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |

### Docker Compose Overrides

```bash
# Start with debug logging
docker-compose up -d
docker-compose exec cache_node_a bash
export LOG_LEVEL=DEBUG
python -m uvicorn cache_node.app.main:app --reload

# Run with custom ports
docker-compose -f docker-compose.override.yml up -d
```

---

## Summary

**Production Checklist**:
- ✅ 3-node cluster running in Docker
- ✅ Metrics scraped by Prometheus every 15s
- ✅ Logs aggregated to ELK/Loki
- ✅ Alerts configured for quorum failures
- ✅ Benchmarks run weekly
- ✅ Backups automated daily
- ✅ Disaster recovery tested quarterly

**Performance SLOs**:
- GET p99 latency: < 5ms
- PUT p99 latency: < 10ms (due to quorum)
- Availability: 99.9% (2/3 quorum)
- Throughput: > 1000 GET ops/sec

