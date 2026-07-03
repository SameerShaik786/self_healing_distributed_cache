import asyncio
import logging
from datetime import datetime, UTC

import grpc

from cache_node.protos import cache_pb2, cache_pb2_grpc
from cache_node.app.services.node_registry import NodeRegistry

logger = logging.getLogger(__name__)


class ReplicationService:
    """Handles communication with peer nodes via gRPC."""

    def __init__(self, registry: NodeRegistry):
        self.registry = registry

    async def send_heartbeat(self, node_id: str, address: str) -> bool:
        """Send a heartbeat to a peer node."""
        try:
            async with grpc.aio.insecure_channel(address) as channel:
                stub = cache_pb2_grpc.CacheServiceStub(channel)
                request = cache_pb2.HeartbeatRequest(
                    node_id=self.registry.node_id,
                    timestamp=int(datetime.now(UTC).timestamp()),
                )
                response = await asyncio.wait_for(
                    stub.Heartbeat(request), timeout=2.0
                )
                self.registry.mark_alive(node_id)
                logger.debug(f"Heartbeat successful from {node_id}")
                return True
        except asyncio.TimeoutError:
            logger.warning(f"Heartbeat timeout to {node_id}")
            self.registry.increment_missed_ping(node_id)
            return False
        except grpc.RpcError as e:
            logger.warning(f"gRPC error to {node_id}: {e}")
            self.registry.increment_missed_ping(node_id)
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending heartbeat to {node_id}: {e}")
            self.registry.increment_missed_ping(node_id)
            return False

    async def broadcast_heartbeats(self) -> None:
        """Send heartbeats to all peer nodes."""
        peers = self.registry.get_peer_nodes()
        tasks = [
            self.send_heartbeat(node_id, address) for node_id, address in peers
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def health_check_loop(self, interval: int = 5) -> None:
        """Run periodic health checks on peer nodes."""
        while True:
            try:
                logger.debug("Running health checks...")
                await self.broadcast_heartbeats()

                # Check for dead nodes (3 missed pings)
                for node_id, info in self.registry.nodes.items():
                    if info["missed_pings"] >= 3 and info["status"] != "dead":
                        self.registry.mark_dead(node_id)
                        logger.warning(f"Node {node_id} marked as DEAD")

                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(interval)
