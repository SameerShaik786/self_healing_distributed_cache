import logging
import os
from datetime import datetime, UTC
from typing import Optional

logger = logging.getLogger(__name__)


class NodeRegistry:
    """Tracks the status of all nodes in the cluster."""

    def __init__(self):
        self.node_id = os.getenv("NODE_ID", "node_default")
        self.nodes: dict[str, dict] = {}
        self._initialize_nodes()

    def _initialize_nodes(self) -> None:
        """Initialize known nodes from environment."""
        # Define the cluster topology
        cluster_map = {
            "node_a": "cache_node_a:50051",
            "node_b": "cache_node_b:50051",
            "node_c": "cache_node_c:50051",
        }

        for node_id, address in cluster_map.items():
            if node_id != self.node_id:
                self.nodes[node_id] = {
                    "address": address,
                    "status": "unknown",
                    "last_heartbeat": None,
                    "missed_pings": 0,
                }

        logger.info(f"Initialized registry with {len(self.nodes)} peer nodes")

    def get_peer_nodes(self) -> list[tuple[str, str]]:
        """Return list of (node_id, address) for peer nodes."""
        return [(node_id, info["address"]) for node_id, info in self.nodes.items()]

    def mark_alive(self, node_id: str) -> None:
        """Mark a node as alive."""
        if node_id in self.nodes:
            self.nodes[node_id]["status"] = "alive"
            self.nodes[node_id]["last_heartbeat"] = datetime.now(UTC)
            self.nodes[node_id]["missed_pings"] = 0
            logger.debug(f"Marked {node_id} as alive")

    def mark_dead(self, node_id: str) -> None:
        """Mark a node as dead."""
        if node_id in self.nodes:
            self.nodes[node_id]["status"] = "dead"
            logger.warning(f"Marked {node_id} as dead")

    def increment_missed_ping(self, node_id: str) -> None:
        """Increment missed ping count."""
        if node_id in self.nodes:
            self.nodes[node_id]["missed_pings"] += 1

    def get_status(self, node_id: str) -> Optional[str]:
        """Get the current status of a node."""
        if node_id in self.nodes:
            return self.nodes[node_id]["status"]
        return None

    def get_all_statuses(self) -> dict:
        """Get status of all peer nodes."""
        return {
            node_id: {
                "status": info["status"],
                "missed_pings": info["missed_pings"],
                "last_heartbeat": info["last_heartbeat"].isoformat()
                if info["last_heartbeat"]
                else None,
            }
            for node_id, info in self.nodes.items()
        }
