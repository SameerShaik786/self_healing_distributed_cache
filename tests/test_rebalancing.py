import os
os.environ.setdefault("NODE_ID", "test_node")

from cache_node.app.services.consistent_hash import ConsistentHash
from cache_node.app.services.rebalancing_manager import RebalancingManager, RebalancingJob


class TestConsistentHash:
    """Tests for consistent hashing."""

    def test_deterministic(self):
        """Test that hashing is deterministic."""
        hash1 = ConsistentHash(["node_a", "node_b", "node_c"])
        hash2 = ConsistentHash(["node_a", "node_b", "node_c"])
        
        # Same key should map to same nodes
        key = "test_key"
        replicas1 = hash1.get_replicas_for_key(key)
        replicas2 = hash2.get_replicas_for_key(key)
        
        assert replicas1 == replicas2

    def test_multiple_replicas(self):
        """Test that we get correct number of replicas."""
        hash_ring = ConsistentHash(["node_a", "node_b", "node_c"], replicas=2)
        
        replicas = hash_ring.get_replicas_for_key("test_key")
        assert len(replicas) == 2
        assert len(set(replicas)) == 2  # No duplicates

    def test_key_distribution(self):
        """Test that keys are distributed across nodes."""
        hash_ring = ConsistentHash(["node_a", "node_b", "node_c"], replicas=1)
        
        keys = [f"key_{i}" for i in range(100)]
        distribution = {"node_a": 0, "node_b": 0, "node_c": 0}
        
        for key in keys:
            replicas = hash_ring.get_replicas_for_key(key)
            distribution[replicas[0]] += 1
        
        # Check that distribution is roughly even
        avg = sum(distribution.values()) / len(distribution)
        for node, count in distribution.items():
            # Allow 50-50% deviation from average
            assert count > avg * 0.3, f"Node {node} has {count}, expected ~{avg}"

    def test_rebalance_on_join(self):
        """Test rebalancing when node joins."""
        hash_ring = ConsistentHash(["node_a", "node_b", "node_c"], replicas=2)
        keys = [f"key_{i}" for i in range(50)]
        
        # Count initial distribution
        initial_replicas = {}
        for key in keys:
            replicas = hash_ring.get_replicas_for_key(key)
            for node in replicas:
                if node not in initial_replicas:
                    initial_replicas[node] = 0
                initial_replicas[node] += 1
        
        # Simulate node join
        keys_from_old, keys_to_new = hash_ring.keys_to_move_on_join(
            "node_d", keys
        )
        
        # Some keys should move
        total_keys_to_move = sum(len(v) for v in keys_from_old.values())
        assert total_keys_to_move > 0, "Some keys should move on node join"

    def test_minimal_movement_on_join(self):
        """Test that minimal keys move on node join (1/N principle)."""
        hash_ring = ConsistentHash(["node_a", "node_b", "node_c"], replicas=2)
        keys = [f"key_{i}" for i in range(300)]
        
        # Count initial replicas
        initial_count = {}
        for key in keys:
            replicas = hash_ring.get_replicas_for_key(key)
            for node in replicas:
                if node not in initial_count:
                    initial_count[node] = 0
                initial_count[node] += 1
        
        # Join new node
        keys_from_old, keys_to_new = hash_ring.keys_to_move_on_join(
            "node_d", keys
        )
        
        total_moved = len(keys_to_new["keys"])
        # With 4 nodes and replicas=2, roughly 50% of keys should move
        # (because we're going from 3 nodes to 4 nodes with 2 replicas)
        expected_max = len(keys) * 0.6  # Allow variance
        assert total_moved < expected_max, f"Too many keys moved: {total_moved} > {expected_max}"


class TestRebalancingManager:
    """Tests for rebalancing job management."""

    def test_create_job(self):
        """Test creating a rebalancing job."""
        manager = RebalancingManager()
        job_id = manager.create_job("join", ["node_d"])
        
        assert job_id is not None
        assert manager.get_job_status(job_id) is not None

    def test_job_lifecycle(self):
        """Test job creation, start, and completion."""
        manager = RebalancingManager()
        job_id = manager.create_job("join", ["node_d"])
        
        # Check initial state
        status = manager.get_job_status(job_id)
        assert status["status"] == "pending"
        assert not manager.has_active_job()
        
        # Start job
        manager.start_job(job_id)
        assert manager.has_active_job()
        assert manager.get_active_job_id() == job_id
        
        # Update progress
        manager.set_total_keys(job_id, 100)
        manager.update_progress(job_id, 50)
        
        status = manager.get_job_status(job_id)
        assert status["status"] == "in_progress"
        assert status["keys_moved"] == 50
        assert status["progress_percent"] == 50
        
        # Complete job
        manager.complete_job(job_id)
        assert not manager.has_active_job()
        
        status = manager.get_job_status(job_id)
        assert status["status"] == "completed"

    def test_single_active_job(self):
        """Test that only one job can be active."""
        manager = RebalancingManager()
        job1 = manager.create_job("join", ["node_d"])
        job2 = manager.create_job("leave", ["node_c"])
        
        # Start first job
        assert manager.start_job(job1) is True
        
        # Try to start second job (should fail)
        assert manager.start_job(job2) is False
        
        # After completing first, can start second
        manager.complete_job(job1)
        assert manager.start_job(job2) is True

    def test_job_failure(self):
        """Test failing a job."""
        manager = RebalancingManager()
        job_id = manager.create_job("join", ["node_d"])
        
        manager.start_job(job_id)
        manager.fail_job(job_id)
        
        status = manager.get_job_status(job_id)
        assert status["status"] == "failed"
        assert not manager.has_active_job()

    def test_get_all_jobs(self):
        """Test retrieving all jobs."""
        manager = RebalancingManager()
        job1 = manager.create_job("join", ["node_d"])
        job2 = manager.create_job("leave", ["node_c"])
        
        all_jobs = manager.get_all_jobs()
        assert len(all_jobs) == 2
        assert any(j["job_id"] == job1 for j in all_jobs)
        assert any(j["job_id"] == job2 for j in all_jobs)
