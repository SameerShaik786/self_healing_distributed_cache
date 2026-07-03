import asyncio
import logging
import uuid
from datetime import datetime, UTC
from typing import Optional

logger = logging.getLogger(__name__)


class WriteOperation:
    """Represents a write operation being replicated."""

    def __init__(self, op_id: str, key: str, value: str, node_id: str):
        self.op_id = op_id
        self.key = key
        self.value = value
        self.node_id = node_id
        self.timestamp = int(datetime.now(UTC).timestamp())
        self.acks_received = set([node_id])  # Start with self
        self.required_acks = 2  # 2/3 for quorum


class QuorumManager:
    """
    Manages quorum voting for write operations.
    Ensures 2/3 nodes acknowledge before returning success.
    """

    def __init__(self, node_id: str, total_nodes: int = 3):
        self.node_id = node_id
        self.total_nodes = total_nodes
        self.required_quorum = (total_nodes // 2) + 1  # 2/3
        self.pending_operations: dict[str, WriteOperation] = {}

    def create_write(self, key: str, value: str) -> str:
        """Create a new write operation and return operation ID."""
        op_id = str(uuid.uuid4())
        write_op = WriteOperation(op_id, key, value, self.node_id)
        self.pending_operations[op_id] = write_op
        logger.info(f"Created write op {op_id} for key={key}")
        return op_id

    def acknowledge_write(self, op_id: str, node_id: str) -> None:
        """Add acknowledgment from a peer node."""
        if op_id not in self.pending_operations:
            logger.warning(f"Received ack for unknown op {op_id}")
            return

        write_op = self.pending_operations[op_id]
        write_op.acks_received.add(node_id)
        logger.debug(f"Op {op_id}: ack from {node_id}, total acks: {len(write_op.acks_received)}")

    def is_quorum_met(self, op_id: str) -> bool:
        """Check if quorum has been met for a write operation."""
        if op_id not in self.pending_operations:
            return False

        write_op = self.pending_operations[op_id]
        quorum_met = len(write_op.acks_received) >= self.required_quorum
        logger.debug(
            f"Op {op_id}: {len(write_op.acks_received)}/{self.required_quorum} acks"
        )
        return quorum_met

    async def wait_for_quorum(self, op_id: str, timeout: float = 5.0) -> bool:
        """
        Wait for quorum with timeout.
        Returns True if quorum met, False if timeout.
        """
        start = datetime.now(UTC)
        while True:
            if self.is_quorum_met(op_id):
                logger.info(f"Op {op_id}: QUORUM MET")
                return True

            elapsed = (datetime.now(UTC) - start).total_seconds()
            if elapsed > timeout:
                logger.warning(f"Op {op_id}: TIMEOUT waiting for quorum")
                return False

            await asyncio.sleep(0.1)

    def cleanup_operation(self, op_id: str) -> None:
        """Remove a completed operation."""
        if op_id in self.pending_operations:
            del self.pending_operations[op_id]

    def get_operation(self, op_id: str) -> Optional[WriteOperation]:
        """Get a write operation by ID."""
        return self.pending_operations.get(op_id)
