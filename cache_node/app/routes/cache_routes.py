from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cache_node.app.services.storage_service import StorageEngine

router = APIRouter()


class PutRequest(BaseModel):
    key: str
    value: str


class DeleteRequest(BaseModel):
    key: str


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/cache/put")
def put_cache(payload: PutRequest) -> dict[str, object]:
    storage = StorageEngine()
    success = storage.put(payload.key, payload.value)
    if not success:
        raise HTTPException(status_code=500, detail="write failed")
    return {"status": "ok", "key": payload.key, "value": payload.value}


@router.get("/cache/get")
def get_cache(key: str) -> dict[str, object]:
    storage = StorageEngine()
    value = storage.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail="key not found")
    return {"status": "ok", "key": key, "value": value}


@router.delete("/cache/delete")
def delete_cache(payload: DeleteRequest) -> dict[str, object]:
    storage = StorageEngine()
    success = storage.delete(payload.key)
    if not success:
        raise HTTPException(status_code=404, detail="key not found")
    return {"status": "ok", "key": payload.key}
