import os
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from cache_node.app.services.storage_service import StorageEngine
from cache_node.app.services.version_vector import VersionVector

router = APIRouter()


class PutRequest(BaseModel):
    key: str
    value: str


class DeleteRequest(BaseModel):
    key: str


def get_quorum_manager():
    """Dependency injection for quorum manager."""
    from cache_node.app.main import quorum_manager, replication_service
    return quorum_manager, replication_service


def get_rebalancing_manager():
    """Dependency injection for rebalancing manager."""
    from cache_node.app.main import rebalancing_manager
    return rebalancing_manager


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/cache/put")
async def put_cache(
    payload: PutRequest,
    managers=Depends(get_quorum_manager),
) -> dict[str, object]:
    """Put with quorum voting."""
    quorum_manager, replication_service = managers
    node_id = os.getenv("NODE_ID", "node_default")
    
    # Create write operation
    op_id = quorum_manager.create_write(payload.key, payload.value)
    timestamp = int(datetime.now(UTC).timestamp())
    version = VersionVector(timestamp, node_id)
    
    # Write locally
    storage = StorageEngine()
    success, final_version = storage.put(payload.key, payload.value, version)
    
    if not success:
        raise HTTPException(status_code=500, detail="local write failed")
    
    # Replicate to peers
    await replication_service.replicate_write(op_id, payload.key, payload.value, timestamp)
    
    # Wait for quorum
    quorum_met = await quorum_manager.wait_for_quorum(op_id, timeout=5.0)
    quorum_manager.cleanup_operation(op_id)
    
    if not quorum_met:
        raise HTTPException(status_code=503, detail="quorum not met - operation failed")
    
    return {
        "status": "ok",
        "key": payload.key,
        "value": payload.value,
        "version": final_version.timestamp,
    }


@router.get("/cache/get")
def get_cache(key: str) -> dict[str, object]:
    """Get a value from cache."""
    storage = StorageEngine()
    result = storage.get(key)
    
    if result is None:
        raise HTTPException(status_code=404, detail="key not found")
    
    value, version = result
    return {
        "status": "ok",
        "key": key,
        "value": value,
        "version": version.timestamp,
        "node_id": version.node_id,
    }


@router.delete("/cache/delete")
async def delete_cache(
    payload: DeleteRequest,
    managers=Depends(get_quorum_manager),
) -> dict[str, object]:
    """Delete with quorum voting."""
    quorum_manager, replication_service = managers
    node_id = os.getenv("NODE_ID", "node_default")
    
    # Create write operation
    op_id = quorum_manager.create_write(payload.key, "")
    timestamp = int(datetime.now(UTC).timestamp())
    version = VersionVector(timestamp, node_id)
    
    # Delete locally
    storage = StorageEngine()
    success = storage.delete(payload.key, version)
    
    if not success:
        raise HTTPException(status_code=404, detail="key not found")
    
    quorum_manager.cleanup_operation(op_id)
    
    return {"status": "ok", "key": payload.key}


@router.get("/rebalancing/status")
def rebalancing_status(
    rebalancing_manager=Depends(get_rebalancing_manager),
) -> dict[str, object]:
    """Get current rebalancing status."""
    active_job_id = rebalancing_manager.get_active_job_id()
    all_jobs = rebalancing_manager.get_all_jobs()
    
    return {
        "has_active_job": rebalancing_manager.has_active_job(),
        "active_job_id": active_job_id,
        "all_jobs": all_jobs,
    }


@router.get("/rebalancing/job/{job_id}")
def rebalancing_job_status(
    job_id: str,
    rebalancing_manager=Depends(get_rebalancing_manager),
) -> dict[str, object]:
    """Get status of a specific rebalancing job."""
    status = rebalancing_manager.get_job_status(job_id)
    
    if status is None:
        raise HTTPException(status_code=404, detail="job not found")
    
    return status
