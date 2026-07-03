import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cache_node.app.core.database import Base, engine
from cache_node.app.routes.cache_routes import router
from cache_node.app.grpc_server import run_grpc_server
from cache_node.app.services.node_registry import NodeRegistry
from cache_node.app.services.replication_service import ReplicationService
from cache_node.app.services.quorum_manager import QuorumManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
registry = NodeRegistry()
quorum_manager = QuorumManager(os.getenv("NODE_ID", "node_default"), total_nodes=3)
replication_service = ReplicationService(registry, quorum_manager)
health_check_task = None


def start_grpc_server() -> None:
    """Start gRPC server in a background thread."""
    grpc_port = int(os.getenv("GRPC_PORT", "50051"))
    thread = threading.Thread(target=run_grpc_server, args=(grpc_port,), daemon=True)
    thread.start()
    logger.info(f"gRPC server started on port {grpc_port}")


async def start_health_checks() -> None:
    """Start health check loop."""
    logger.info("Starting health check loop...")
    await replication_service.health_check_loop(interval=5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    # Startup
    Base.metadata.create_all(bind=engine)
    start_grpc_server()
    
    # Start health check task
    health_task = asyncio.create_task(start_health_checks())
    
    yield
    
    # Shutdown
    health_task.cancel()
    logger.info("Application shutdown")


app = FastAPI(
    title="self-healing distributed cache",
    lifespan=lifespan,
)


@app.get("/cluster/status")
def cluster_status() -> dict:
    """Get status of all nodes in the cluster."""
    node_id = os.getenv("NODE_ID", "unknown")
    return {
        "node_id": node_id,
        "peer_nodes": registry.get_all_statuses(),
    }


app.include_router(router)
