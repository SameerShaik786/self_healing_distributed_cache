import os

os.environ.setdefault("NODE_ID", "test_node")

from datetime import datetime, UTC
from cache_node.app.core.database import Base, engine
from cache_node.app.services.storage_service import StorageEngine
from cache_node.app.services.version_vector import VersionVector


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_storage_put_get_delete():
    storage = StorageEngine()
    
    # Create version
    version = VersionVector(int(datetime.now(UTC).timestamp()), "test_node")
    
    # Put
    success, v = storage.put("alpha", "one", version)
    assert success is True
    
    # Get
    result = storage.get("alpha")
    assert result is not None
    value, retrieved_version = result
    assert value == "one"

    # Delete
    success = storage.delete("alpha", version)
    assert success is True
    
    # Should be gone
    result = storage.get("alpha")
    assert result is None
