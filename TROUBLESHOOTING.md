# Troubleshooting & Debugging Guide

## Common Issues & Solutions

### Issue 1: "Connection refused" when accessing cache

**Symptoms**:
```
curl: (7) Failed to connect to localhost port 5001: Connection refused
```

**Causes**:
1. Container not running
2. Port not exposed
3. FastAPI server crashed

**Debug Steps**:
```bash
# Check if containers are running
docker-compose ps

# Check logs for errors
docker logs cache_node_a

# If container exited, restart it
docker-compose restart cache_node_a

# If still failing, check port conflicts
lsof -i :5001  # On macOS/Linux
netstat -ano | findstr :5001  # On Windows PowerShell

# Verify FastAPI is listening
curl http://localhost:5001/cluster/status -v
```

**Solution**:
- Restart containers: `docker-compose down && docker-compose up -d`
- If port conflict, update docker-compose.yml ports

---

### Issue 2: Quorum failures - "PUT returns 503 Service Unavailable"

**Symptoms**:
```
PUT /cache/put → 503 Service Unavailable
```

**Root Causes**:
1. 2+ nodes down (quorum = 0/3 or 1/3)
2. Network partition (nodes can't communicate)
3. gRPC timeout (peer too slow to respond)

**Debug Steps**:
```bash
# Check cluster status
curl http://localhost:5001/cluster/status

# Output shows which nodes are alive/dead
# If < 2 nodes alive → quorum impossible

# Check gRPC connectivity between nodes
# Inside a container, test gRPC:
docker exec cache_node_a /bin/bash
python -c "
import grpc
from cache_node.protos import cache_pb2_grpc

channel = grpc.insecure_channel('cache_node_b:50052')
stub = cache_pb2_grpc.CacheServiceStub(channel)
print('Connected to node_b')
channel.close()
"

# Check metrics for replication failures
curl http://localhost:5001/metrics | grep replication_failed

# Check latency to peers
curl http://localhost:5001/metrics | grep replication_latency_seconds
```

**Solutions**:
| Cause | Fix |
|-------|-----|
| Node down | Restart: `docker-compose restart cache_node_b` |
| Network partition | Check Docker network: `docker network inspect cache-network` |
| gRPC timeout (> 1s latency) | Increase timeout in `QuorumManager.wait_for_quorum()` |
| CPU overload | Check `docker stats` - scale to more resources |

---

### Issue 3: Data inconsistency - Different values on different nodes

**Symptoms**:
```bash
# On node_a
curl http://localhost:5001/cache/get?key=user:1
→ {"value": "Alice", "version": "2026-07-03T10:30:45-node_a"}

# On node_b
curl http://localhost:5002/cache/get?key=user:1
→ {"value": "Bob", "version": "2026-07-03T10:30:40-node_b"}
```

**Root Cause**: 
Concurrent writes from different nodes with timestamp conflicts

**Debug Steps**:
```bash
# Check version vector logic
# Examine the version tuple (timestamp, node_id)

# node_a: 2026-07-03T10:30:45 (45 seconds) - NEWER ✓
# node_b: 2026-07-03T10:30:40 (40 seconds) - OLDER ✗

# Verify LWW resolution is working:
grep "Version comparison" logs.json | jq '.context'

# Check if heartbeat replication happened
curl http://localhost:5001/metrics | grep cache_puts_total
curl http://localhost:5002/metrics | grep cache_puts_total
# Should be identical (all writes synced)
```

**Solutions**:
1. **Automatic**: Wait 5-15 seconds. Heartbeat loop will sync all nodes to newer value
2. **Manual**: Trigger replication:
   ```bash
   # Force PUT on node_a (highest authority due to newer timestamp)
   curl -X PUT http://localhost:5001/cache/put \
     -H "Content-Type: application/json" \
     -d '{"key": "user:1", "value": "Alice"}'
   ```
3. **Prevention**: Ensure clock sync across all nodes (NTP configured)

---

### Issue 4: High latency - Operations taking > 100ms

**Symptoms**:
```bash
# Benchmark shows
Latency P99: 500ms (expected < 10ms)
```

**Root Causes**:
1. High CPU usage on nodes
2. Network congestion
3. Disk I/O bottleneck (SQLite)
4. Too many concurrent requests overwhelming quorum

**Debug Steps**:
```bash
# Check CPU/Memory usage
docker stats --no-stream

# Check if disk is the issue
docker exec cache_node_a iostat -x

# Monitor active connections
docker exec cache_node_a ss -tuln

# Check Prometheus metrics for insight
curl http://localhost:5001/metrics | grep _duration_seconds_bucket

# Analyze histogram buckets
# If traffic clusters in 0.1s+ bucket → latency problem confirmed

# Check if it's gRPC latency or FastAPI
curl http://localhost:5001/cache/get?key=test \
  -w "Total time: %{time_total}s\n"
```

**Solutions**:
| Cause | Fix |
|-------|-----|
| High CPU (> 80%) | Reduce concurrent requests or scale to more nodes |
| Network congestion | Check bandwidth: `iftop`, `nethogs` inside container |
| Disk I/O wait (> 10%) | Move SQLite to faster disk or use `PRAGMA synchronous=NORMAL` |
| Too many replicas | Reduce replicas from 2 to 1 in `consistent_hash.py` |

**Optimization**: Enable write-ahead logging (WAL) in SQLite:
```python
# In database.py
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "timeout": 30,
        "check_same_thread": False,
    },
)

# Enable WAL mode (faster writes)
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
```

---

### Issue 5: Memory leak - Memory usage growing indefinitely

**Symptoms**:
```bash
docker stats
# MEMORY: 50MB → 100MB → 200MB → ...
```

**Root Causes**:
1. In-memory cache growing without limit (no eviction)
2. Pending operations list not cleaned up
3. Replication queue accumulating failed operations

**Debug Steps**:
```bash
# Check memory cache size in metrics
curl http://localhost:5001/metrics | grep memory_cache_entries

# If growing unbounded, implement TTL or max size

# Check for stuck pending operations
curl http://localhost:5001/metrics | grep replication_queue_size

# Monitor for 10 minutes
watch -n 1 "curl http://localhost:5001/metrics | grep memory_cache"
```

**Solutions**:
1. **Implement TTL eviction**:
   ```python
   # In storage_service.py, add periodic cleanup
   async def evict_expired_keys():
       while True:
           await asyncio.sleep(60)  # Every 60 seconds
           now = datetime.now(timezone.utc)
           session.query(CacheEntry).filter(
               CacheEntry.expires_at < now
           ).delete()
           session.commit()
   ```

2. **Cap in-memory cache size**:
   ```python
   MAX_MEMORY_ENTRIES = 10000
   
   if len(self._memory_cache) > MAX_MEMORY_ENTRIES:
       # Evict least recently used (LRU)
       oldest_key = min(self._memory_cache, 
                        key=lambda k: self._memory_cache[k][1])
       del self._memory_cache[oldest_key]
   ```

3. **Clean up stuck operations**:
   ```python
   # In quorum_manager.py, add cleanup
   for op_id, op in list(self.pending_operations.items()):
       if time.time() - op.start_time > 300:  # 5 minutes
           del self.pending_operations[op_id]
   ```

---

### Issue 6: Rebalancing stuck - Nodes not migrating keys

**Symptoms**:
```bash
# After adding node_d
curl http://localhost:5001/rebalancing/status
→ {"in_progress": true, "progress": "20%"}

# After 1 hour still at 20% - not progressing
```

**Root Causes**:
1. Rebalancing job crashed
2. Network timeout during key migration
3. Disk space issue on target node

**Debug Steps**:
```bash
# Check rebalancing job status
curl http://localhost:5001/rebalancing/job/{job_id}

# Check logs for rebalancing errors
docker logs cache_node_a | jq 'select(.context.event=="rebalancing")'

# Check disk space
docker exec cache_node_d df -h

# Check if new node is receiving data
curl http://localhost:5004/cache/get?key=*  # (not valid, for demo)
curl http://localhost:5004/metrics | grep memory_cache_entries
```

**Solutions**:
1. **Cancel stuck job and restart**:
   ```bash
   # In rebalancing_manager.py, add cancel method
   curl -X POST http://localhost:5001/rebalancing/cancel/{job_id}
   
   # Restart with fresh job_id
   curl -X POST http://localhost:5001/rebalancing/start
   ```

2. **Increase timeout for large migrations**:
   ```python
   # In rebalancing_manager.py
   MIGRATION_TIMEOUT = 300  # 5 minutes (was 60s)
   ```

3. **Free disk space**:
   ```bash
   docker exec cache_node_d rm -rf /tmp/*
   docker volume prune  # Remove unused volumes
   ```

---

### Issue 7: Tests failing after code changes

**Symptoms**:
```
FAILED tests/test_consistency.py::test_quorum_manager_wait_for_quorum
AttributeError: 'QuorumManager' has no attribute 'wait_for_quorum'
```

**Root Cause**: Code changed but tests not updated

**Debug Steps**:
```bash
# Run specific test with verbose output
python -m pytest tests/test_consistency.py::test_quorum_manager_wait_for_quorum -vv

# Show full traceback
python -m pytest tests/test_consistency.py -vv --tb=long

# Check if the method exists
python -c "from cache_node.app.services.quorum_manager import QuorumManager; print(dir(QuorumManager))"
```

**Solutions**:
1. Update the test to match new method signature
2. Restore method if it was accidentally removed
3. Run all tests to catch regressions:
   ```bash
   python -m pytest tests/ --tb=short
   ```

---

### Issue 8: JSON logs not parsing correctly

**Symptoms**:
```bash
docker logs cache_node_a | jq '.'
# jq: parse error: Invalid JSON...
```

**Root Cause**: Log line has non-JSON prefix or multiline format

**Debug Steps**:
```bash
# Check raw logs
docker logs cache_node_a | head -5

# Look for non-JSON lines (stack traces, etc.)
docker logs cache_node_a | head -100 | grep -v "^{" | head -10

# Check if Unicode issues
docker logs cache_node_a | file -

# Verify JSON is valid
docker logs cache_node_a | jq -s 'length'  # Count valid JSON lines
```

**Solutions**:
1. **Filter out non-JSON lines**:
   ```bash
   docker logs cache_node_a | grep "^{" | jq '.'
   ```

2. **Use jq with `try-catch` for invalid JSON**:
   ```bash
   docker logs cache_node_a | jq -R 'try fromjson' | jq 'select(.timestamp != null)'
   ```

3. **Configure logging format** (verify `logging_setup.py` uses JSONFormatter on all handlers)

---

## Performance Diagnostics

### Baseline Benchmark Results

After clean deployment, run baseline:
```bash
python benchmarks/benchmark.py
```

Expected results (on modern hardware):
- GET: 2000-5000 ops/sec, p99 < 5ms ✓
- PUT: 400-800 ops/sec, p99 < 10ms ✓ (due to quorum)
- DELETE: 350-700 ops/sec, p99 < 15ms ✓

### Monitoring Prometheus Query Examples

```promql
# Alert if quorum failures increasing
increase(quorum_failed_total[5m]) > 0

# Alert if active nodes < 2
active_nodes < 2

# Track p99 latency trend
histogram_quantile(0.99, cache_get_duration_seconds)

# Find slowest node
sort(cache_put_duration_seconds) desc

# Calculate cache hit ratio
cache_hits_total / (cache_hits_total + cache_misses_total)

# Track replication failures
increase(replication_failed_total[5m])
```

---

## Log Analysis Techniques

### Find all operations for a specific key

```bash
docker logs cache_node_a | jq 'select(.context.key == "user:1234")'
```

### Trace an operation by ID
```bash
docker logs cache_node_a | jq 'select(.context.operation_id == "op-abc-123")'
```

### Find slow operations
```bash
docker logs cache_node_a | jq 'select(.context.latency_ms > 100)'
```

### Calculate average latency
```bash
docker logs cache_node_a | \
  jq -s '[.[] | select(.context.operation=="PUT") | .context.latency_ms] | add / length'
```

### Generate request rate
```bash
docker logs cache_node_a | \
  jq '.timestamp' | \
  sort | uniq -c | tail -60  # Last 60 seconds
```

---

## Heap Dump Analysis (Advanced)

If memory usage spikes, generate heap dump:

```bash
# In Python (cache_node/app/main.py), add:
import tracemalloc

tracemalloc.start()

# ... later ...

# Get snapshot
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)
```

---

## Network Troubleshooting

### Test gRPC connectivity
```bash
# Inside a container
python -m grpcio.tools.protoc \
  -I cache_node/protos \
  --python_out=. \
  --grpc_python_out=. \
  cache_node/protos/cache.proto

# Then test connection
python << 'EOF'
import grpc
from cache_node.protos import cache_pb2, cache_pb2_grpc

channel = grpc.insecure_channel('cache_node_b:50052', options=[
    ('grpc.max_send_message_length', 100 * 1024 * 1024),
    ('grpc.max_receive_message_length', 100 * 1024 * 1024),
])
stub = cache_pb2_grpc.CacheServiceStub(channel)

# Test heartbeat
response = stub.Heartbeat(cache_pb2.HeartbeatRequest(node_id='node_a'))
print(f"Status: {response.status}, Active nodes: {response.active_nodes}")

channel.close()
EOF
```

### Monitor network traffic
```bash
# Inside container, use tcpdump to capture gRPC
docker exec cache_node_a tcpdump -i any -w /tmp/grpc.pcap port 50052

# Analyze with wireshark or tshark
docker exec cache_node_a tshark -r /tmp/grpc.pcap | head -20
```

---

## Getting Help

### Enable Debug Logging
```bash
# Restart with DEBUG level
docker-compose down
export LOG_LEVEL=DEBUG
docker-compose up -d

# Now logs will show more details
docker logs cache_node_a | jq 'select(.level=="DEBUG")'
```

### Collect Debug Bundle
```bash
#!/bin/bash
mkdir -p debug_bundle

# Collect metrics
curl http://localhost:5001/metrics > debug_bundle/metrics_a.txt
curl http://localhost:5002/metrics > debug_bundle/metrics_b.txt
curl http://localhost:5003/metrics > debug_bundle/metrics_c.txt

# Collect cluster status
curl http://localhost:5001/cluster/status > debug_bundle/status.json

# Collect logs (last 1000 lines)
docker logs cache_node_a --tail 1000 > debug_bundle/logs_a.jsonl
docker logs cache_node_b --tail 1000 > debug_bundle/logs_b.jsonl
docker logs cache_node_c --tail 1000 > debug_bundle/logs_c.jsonl

# Collect container info
docker inspect cache_node_a > debug_bundle/inspect_a.json
docker stats --no-stream > debug_bundle/stats.txt

tar -czf debug_bundle.tar.gz debug_bundle/
echo "Debug bundle created: debug_bundle.tar.gz"
```

Share `debug_bundle.tar.gz` for support

---

## Summary

| Problem | Check | Tool |
|---------|-------|------|
| Connection refused | `docker ps` | Docker |
| Slow operations | Metrics p99 | Prometheus |
| Data inconsistent | Version tuples | Logs + `jq` |
| Memory leak | `memory_cache_entries` | Metrics |
| Quorum failures | `active_nodes` | Metrics |
| Tests failing | Traceback | pytest |
| JSON parse errors | Log format | jq with try-catch |

