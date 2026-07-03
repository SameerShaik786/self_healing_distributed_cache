import os
os.environ.setdefault("NODE_ID", "test_node")

from cache_node.app.services.node_registry import NodeRegistry


def test_node_registry_initialization():
    """Test that node registry initializes with peer nodes."""
    registry = NodeRegistry()
    peers = registry.get_peer_nodes()
    # test_node is not in cluster map, so it adds all 3 nodes as peers
    assert len(peers) >= 2


def test_node_registry_mark_alive():
    """Test marking a node as alive."""
    registry = NodeRegistry()
    registry.mark_alive("node_a")
    status = registry.get_status("node_a")
    assert status == "alive"
    assert registry.nodes["node_a"]["missed_pings"] == 0


def test_node_registry_mark_dead():
    """Test marking a node as dead."""
    registry = NodeRegistry()
    registry.mark_dead("node_a")
    status = registry.get_status("node_a")
    assert status == "dead"


def test_node_registry_missed_pings():
    """Test incrementing missed pings."""
    registry = NodeRegistry()
    registry.increment_missed_ping("node_a")
    registry.increment_missed_ping("node_a")
    assert registry.nodes["node_a"]["missed_pings"] == 2
