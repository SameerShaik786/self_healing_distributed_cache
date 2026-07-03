"""
Prometheus metrics service for monitoring distributed cache operations.

Tracks:
- Cache hit/miss rates
- Replication latency
- Quorum voting success rates
- Rebalancing progress
- Node health status
"""

from prometheus_client import Counter, Histogram, Gauge
from typing import Dict
import time


class MetricsService:
    """Centralized metrics collection for cache operations."""

    # Cache operation counters - Count total operations by outcome
    cache_hits = Counter(
        "cache_hits_total",
        "Total cache hits (key found in memory/DB)",
        labelnames=["node_id"],
    )
    cache_misses = Counter(
        "cache_misses_total",
        "Total cache misses (key not found)",
        labelnames=["node_id"],
    )

    # Replication counters - Count successful/failed replications
    replication_success = Counter(
        "replication_success_total",
        "Successful replication operations",
        labelnames=["node_id", "operation"],  # operation: put, delete
    )
    replication_failed = Counter(
        "replication_failed_total",
        "Failed replication operations",
        labelnames=["node_id", "operation"],
    )

    # Quorum voting counters - Track consensus outcomes
    quorum_met = Counter(
        "quorum_met_total",
        "Quorum successfully met (2/3 nodes acknowledged)",
        labelnames=["node_id"],
    )
    quorum_failed = Counter(
        "quorum_failed_total",
        "Quorum failed (less than 2/3 nodes responded)",
        labelnames=["node_id"],
    )

    # Latency histograms - Measure operation duration in seconds
    get_latency = Histogram(
        "cache_get_duration_seconds",
        "Time taken to get a key from cache",
        labelnames=["node_id"],
        buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),  # Buckets in seconds
    )
    put_latency = Histogram(
        "cache_put_duration_seconds",
        "Time taken to put a key in cache",
        labelnames=["node_id"],
        buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
    )
    delete_latency = Histogram(
        "cache_delete_duration_seconds",
        "Time taken to delete a key from cache",
        labelnames=["node_id"],
        buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
    )
    replication_latency = Histogram(
        "replication_latency_seconds",
        "Time taken to replicate operation to peer node",
        labelnames=["node_id", "target_node"],
        buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
    )

    # Node health gauges - Current state metrics
    active_nodes = Gauge(
        "active_nodes",
        "Number of nodes currently alive in cluster",
        labelnames=["node_id"],
    )
    replication_queue_size = Gauge(
        "replication_queue_size",
        "Number of pending replications",
        labelnames=["node_id"],
    )
    memory_cache_size = Gauge(
        "memory_cache_entries",
        "Number of entries in in-memory cache",
        labelnames=["node_id"],
    )

    # Rebalancing progress gauges
    rebalancing_in_progress = Gauge(
        "rebalancing_in_progress",
        "Whether node is currently rebalancing (0/1)",
        labelnames=["node_id"],
    )
    rebalancing_keys_moved = Gauge(
        "rebalancing_keys_moved_total",
        "Total keys moved during current rebalancing",
        labelnames=["node_id"],
    )

    @staticmethod
    def record_cache_access(node_id: str, hit: bool):
        """Record a cache access (hit or miss).
        
        Args:
            node_id: ID of the node handling the request
            hit: True if key was found, False otherwise
        """
        if hit:
            MetricsService.cache_hits.labels(node_id=node_id).inc()
        else:
            MetricsService.cache_misses.labels(node_id=node_id).inc()

    @staticmethod
    def record_replication(
        node_id: str,
        operation: str,
        success: bool,
        duration_seconds: float = None,
    ):
        """Record a replication attempt.
        
        Args:
            node_id: ID of the node originating replication
            operation: "put" or "delete"
            success: True if replication succeeded
            duration_seconds: How long the operation took
        """
        if success:
            MetricsService.replication_success.labels(
                node_id=node_id, operation=operation
            ).inc()
        else:
            MetricsService.replication_failed.labels(
                node_id=node_id, operation=operation
            ).inc()

    @staticmethod
    def record_quorum_result(node_id: str, met: bool):
        """Record whether quorum voting succeeded.
        
        Args:
            node_id: ID of the node initiating quorum
            met: True if 2/3 nodes acknowledged
        """
        if met:
            MetricsService.quorum_met.labels(node_id=node_id).inc()
        else:
            MetricsService.quorum_failed.labels(node_id=node_id).inc()

    @staticmethod
    def update_active_nodes(node_id: str, count: int):
        """Update gauge showing active node count.
        
        Args:
            node_id: ID of the node making the update
            count: Number of alive nodes in cluster
        """
        MetricsService.active_nodes.labels(node_id=node_id).set(count)

    @staticmethod
    def update_memory_cache_size(node_id: str, size: int):
        """Update gauge showing in-memory cache entries.
        
        Args:
            node_id: ID of the node
            size: Number of entries in memory cache
        """
        MetricsService.memory_cache_size.labels(node_id=node_id).set(size)

    @staticmethod
    def start_latency_timer() -> float:
        """Start a timer for latency measurement.
        
        Returns:
            Current time in seconds (for passing to stop_latency_timer)
        """
        return time.time()

    @staticmethod
    def record_latency(histogram, node_id: str, start_time: float, **labels):
        """Record latency for a histogram.
        
        Args:
            histogram: The Histogram metric object
            node_id: ID of the node
            start_time: Time returned by start_latency_timer()
            **labels: Additional label key-values for the histogram
        """
        duration = time.time() - start_time
        histogram.labels(node_id=node_id, **labels).observe(duration)
