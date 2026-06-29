import os

os.environ.setdefault("NODE_ID", "test_node")

from cache_node.app.core.database import Base, engine
from cache_node.app.services.storage_service import StorageEngine


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_storage_put_get_delete():
    storage = StorageEngine()

    assert storage.put("alpha", "one") is True
    assert storage.get("alpha") == "one"

    assert storage.delete("alpha") is True
    assert storage.get("alpha") is None
