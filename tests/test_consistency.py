import os
os.environ.setdefault("NODE_ID", "test_node")

import asyncio
import pytest
from cache_node.app.services.version_vector import VersionVector
from cache_node.app.services.quorum_manager import QuorumManager


def test_version_vector_newer():
    """Test version vector comparison - newer timestamp."""
    v1 = VersionVector(100, "node_a")
    v2 = VersionVector(50, "node_b")
    assert v1.compare(v2) == "newer"


def test_version_vector_older():
    """Test version vector comparison - older timestamp."""
    v1 = VersionVector(50, "node_a")
    v2 = VersionVector(100, "node_b")
    assert v1.compare(v2) == "older"


def test_version_vector_tie_breaking():
    """Test version vector tie-breaking by node_id."""
    v1 = VersionVector(100, "node_c")
    v2 = VersionVector(100, "node_a")
    assert v1.compare(v2) == "newer"  # node_c > node_a


def test_version_vector_equal():
    """Test version vector equality."""
    v1 = VersionVector(100, "node_a")
    v2 = VersionVector(100, "node_a")
    assert v1.compare(v2) == "equal"


def test_quorum_manager_create_write():
    """Test creating a write operation."""
    manager = QuorumManager("node_a", total_nodes=3)
    op_id = manager.create_write("key1", "value1")
    assert op_id is not None
    assert manager.get_operation(op_id) is not None


def test_quorum_manager_acknowledge():
    """Test acknowledging writes."""
    manager = QuorumManager("node_a", total_nodes=3)
    op_id = manager.create_write("key1", "value1")
    
    # node_a starts with self ack (1/2 needed)
    assert not manager.is_quorum_met(op_id)
    
    # With node_b, we have 2/2 acks (meets quorum)
    manager.acknowledge_write(op_id, "node_b")
    assert manager.is_quorum_met(op_id)


@pytest.mark.asyncio
async def test_quorum_manager_wait_for_quorum():
    """Test waiting for quorum."""
    manager = QuorumManager("node_a", total_nodes=3)
    op_id = manager.create_write("key1", "value1")
    
    # Start a task that acknowledges after delay
    async def delayed_ack():
        await asyncio.sleep(0.1)
        manager.acknowledge_write(op_id, "node_b")
    
    ack_task = asyncio.create_task(delayed_ack())
    result = await manager.wait_for_quorum(op_id, timeout=1.0)
    await ack_task
    
    assert result is True


@pytest.mark.asyncio
async def test_quorum_manager_timeout():
    """Test quorum timeout."""
    manager = QuorumManager("node_a", total_nodes=3)
    op_id = manager.create_write("key1", "value1")
    
    result = await manager.wait_for_quorum(op_id, timeout=0.2)
    assert result is False
