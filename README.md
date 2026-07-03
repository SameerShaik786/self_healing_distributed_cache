# Self-Healing Distributed Cache

A resilient distributed cache system with automatic failure detection, replica promotion, and self-healing capabilities.

## Phase 1: Single-Node Cache Foundation (✅ Complete)

### What's included
- **Storage Engine**: In-memory cache + SQLite persistence
- **FastAPI Server**: HTTP endpoints for get/put/delete operations
- **Docker Support**: Single container + 3-node cluster orchestration
- **Health Check**: `/health` endpoint for monitoring

### Quick Start (Local)

```bash
# Activate virtual environment
source venv/bin/activate  # Mac/Linux
# or
venv\Scripts\activate  # Windows

# Run the FastAPI server
uvicorn cache_node.app.main:app --reload --port 5000

# Test endpoints
curl http://localhost:5000/health
curl -X POST http://localhost:5000/cache/put \
  -H "Content-Type: application/json" \
  -d '{"key":"demo","value":"hello"}'
curl http://localhost:5000/cache/get?key=demo
curl -X DELETE http://localhost:5000/cache/delete \
  -H "Content-Type: application/json" \
  -d '{"key":"demo"}'
```

### Quick Start (Docker - 3-Node Cluster)

```bash
# Build and start 3-node cluster
docker-compose up -d

# Check status
docker-compose ps

# Test node A
curl http://localhost:5001/health
curl -X POST http://localhost:5001/cache/put \
  -H "Content-Type: application/json" \
  -d '{"key":"test","value":"data"}'

# Read from node B (later: will sync via replication)
curl http://localhost:5002/cache/get?key=test

# View logs
docker-compose logs -f node_a

# Stop cluster
docker-compose down
```

### Architecture

```
StorageEngine
├── In-memory cache (fast reads)
└── SQLite database (persistence)
     └── CacheEntry table (key, value, version, timestamp)

FastAPI Server
├── /health → status check
├── /cache/put → write
├── /cache/get → read
└── /cache/delete → remove

Docker Setup
├── 3 nodes (node_a, node_b, node_c)
├── Ports: 5001, 5002, 5003 (FastAPI)
├── Ports: 50051, 50052, 50053 (gRPC - for Phase 2)
└── Shared network for inter-node communication
```

### Testing

```bash
# Run unit tests
pytest tests/test_storage.py -v

# Run with coverage
pytest tests/ --cov=cache_node
```

### What's Next: Phase 2

- Heartbeat-based health detection
- Replica promotion on node failure
- Automatic failover logic
- WriteLog tracking for recovery

---

## Environment Variables

```
NODE_ID=node_a  # Set in docker-compose, used for database naming
```

## Database

- SQLite file: `{NODE_ID}.db` (auto-created)
- Schema: `cache_entries` table with versioning support

## Requirements

- Python 3.11+
- Docker & Docker Compose (for cluster testing)
