import logging
import os
from datetime import datetime, UTC
from concurrent import futures

import grpc

from cache_node.protos import cache_pb2, cache_pb2_grpc
from cache_node.app.services.storage_service import StorageEngine

logger = logging.getLogger(__name__)


class CacheServicer(cache_pb2_grpc.CacheServiceServicer):
    def __init__(self):
        self.storage = StorageEngine()
        self.node_id = os.getenv("NODE_ID", "node_default")

    def Heartbeat(self, request, context):
        """Respond to heartbeat from another node."""
        return cache_pb2.HeartbeatResponse(
            node_id=self.node_id,
            alive=True,
            timestamp=int(datetime.now(UTC).timestamp()),
        )

    def Get(self, request, context):
        """Get a value from the cache."""
        value = self.storage.get(request.key)
        if value is None:
            return cache_pb2.GetResponse(found=False, value="", version=0)
        return cache_pb2.GetResponse(found=True, value=value, version=1)

    def Put(self, request, context):
        """Put a value into the cache."""
        success = self.storage.put(request.key, request.value)
        return cache_pb2.PutResponse(success=success, version=request.version + 1)

    def Delete(self, request, context):
        """Delete a key from the cache."""
        success = self.storage.delete(request.key)
        return cache_pb2.DeleteResponse(success=success)


def run_grpc_server(port: int = 50051) -> None:
    """Start the gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    cache_pb2_grpc.add_CacheServiceServicer_to_server(CacheServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    
    logger.info(f"gRPC server starting on port {port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_grpc_server()
