from datetime import datetime, UTC
import logging

logger = logging.getLogger(__name__)


class VersionVector:
    """
    Tracks version of data with timestamp and node_id.
    Used for conflict resolution via Last-Write-Wins (LWW).
    """

    def __init__(self, timestamp: int, node_id: str):
        self.timestamp = timestamp
        self.node_id = node_id

    def compare(self, other: "VersionVector") -> str:
        """
        Compare two versions.
        Returns: 'newer', 'older', 'equal', or 'concurrent'
        """
        if self.timestamp > other.timestamp:
            return "newer"
        elif self.timestamp < other.timestamp:
            return "older"
        else:
            # Same timestamp, use node_id for tie-breaking
            if self.node_id > other.node_id:
                return "newer"
            elif self.node_id < other.node_id:
                return "older"
            else:
                return "equal"

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "node_id": self.node_id,
        }

    @staticmethod
    def from_dict(data: dict) -> "VersionVector":
        return VersionVector(data["timestamp"], data["node_id"])

    def __repr__(self) -> str:
        return f"VersionVector(ts={self.timestamp}, node={self.node_id})"
