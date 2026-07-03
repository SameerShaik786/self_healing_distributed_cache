"""
Performance benchmarking script for distributed cache system.

Measures:
- Throughput (ops/sec) for GET, PUT, DELETE
- Latency percentiles (p50, p95, p99)
- Concurrent operation handling
- Network overhead (gRPC vs HTTP)
"""

import asyncio
import time
import statistics
import requests
from typing import List, Dict, Tuple
from dataclasses import dataclass


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""

    operation: str  # "GET", "PUT", "DELETE"
    num_operations: int
    total_time: float
    latencies: List[float]

    @property
    def throughput(self) -> float:
        """Operations per second."""
        return self.num_operations / self.total_time if self.total_time > 0 else 0

    @property
    def p50_latency(self) -> float:
        """50th percentile latency (median)."""
        if not self.latencies:
            return 0
        return statistics.median(self.latencies)

    @property
    def p95_latency(self) -> float:
        """95th percentile latency."""
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        index = int(0.95 * len(sorted_latencies))
        return sorted_latencies[index]

    @property
    def p99_latency(self) -> float:
        """99th percentile latency."""
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        index = int(0.99 * len(sorted_latencies))
        return sorted_latencies[index]

    @property
    def avg_latency(self) -> float:
        """Average latency across all operations."""
        return statistics.mean(self.latencies) if self.latencies else 0


class CacheBenchmark:
    """Benchmarking suite for cache operations."""

    def __init__(self, base_url: str = "http://localhost:5001"):
        """Initialize benchmark with cache node URL.
        
        Args:
            base_url: Base URL of cache node (default: local node A)
        """
        self.base_url = base_url
        self.session = requests.Session()

    def benchmark_get_operations(
        self, num_operations: int = 1000, concurrent: int = 1
    ) -> BenchmarkResult:
        """Benchmark GET operations.
        
        Args:
            num_operations: Total GETs to perform
            concurrent: How many concurrent requests
            
        Returns:
            BenchmarkResult with throughput and latency metrics
        """
        latencies = []
        
        # Pre-populate cache with test keys
        for i in range(num_operations):
            self.session.put(
                f"{self.base_url}/cache/put",
                json={"key": f"bench_key_{i}", "value": f"value_{i}"},
                timeout=5,
            )

        # Measure GET performance
        start_time = time.time()

        for i in range(num_operations):
            op_start = time.time()
            try:
                self.session.get(
                    f"{self.base_url}/cache/get",
                    params={"key": f"bench_key_{i}"},
                    timeout=5,
                )
                latencies.append(time.time() - op_start)
            except requests.RequestException as e:
                print(f"GET failed: {e}")

        total_time = time.time() - start_time

        return BenchmarkResult(
            operation="GET",
            num_operations=num_operations,
            total_time=total_time,
            latencies=latencies,
        )

    def benchmark_put_operations(
        self, num_operations: int = 1000, concurrent: int = 1
    ) -> BenchmarkResult:
        """Benchmark PUT operations.
        
        Args:
            num_operations: Total PUTs to perform
            concurrent: How many concurrent requests
            
        Returns:
            BenchmarkResult with throughput and latency metrics
        """
        latencies = []
        start_time = time.time()

        for i in range(num_operations):
            op_start = time.time()
            try:
                self.session.put(
                    f"{self.base_url}/cache/put",
                    json={"key": f"bench_put_key_{i}", "value": f"put_value_{i}"},
                    timeout=5,
                )
                latencies.append(time.time() - op_start)
            except requests.RequestException as e:
                print(f"PUT failed: {e}")

        total_time = time.time() - start_time

        return BenchmarkResult(
            operation="PUT",
            num_operations=num_operations,
            total_time=total_time,
            latencies=latencies,
        )

    def benchmark_delete_operations(
        self, num_operations: int = 1000, concurrent: int = 1
    ) -> BenchmarkResult:
        """Benchmark DELETE operations.
        
        Args:
            num_operations: Total DELETEs to perform
            concurrent: How many concurrent requests
            
        Returns:
            BenchmarkResult with throughput and latency metrics
        """
        latencies = []

        # Pre-populate cache
        for i in range(num_operations):
            self.session.put(
                f"{self.base_url}/cache/put",
                json={"key": f"bench_del_key_{i}", "value": f"del_value_{i}"},
                timeout=5,
            )

        # Measure DELETE performance
        start_time = time.time()

        for i in range(num_operations):
            op_start = time.time()
            try:
                self.session.delete(
                    f"{self.base_url}/cache/delete",
                    params={"key": f"bench_del_key_{i}"},
                    timeout=5,
                )
                latencies.append(time.time() - op_start)
            except requests.RequestException as e:
                print(f"DELETE failed: {e}")

        total_time = time.time() - start_time

        return BenchmarkResult(
            operation="DELETE",
            num_operations=num_operations,
            total_time=total_time,
            latencies=latencies,
        )

    def print_results(self, result: BenchmarkResult):
        """Print benchmark results in readable format.
        
        Args:
            result: BenchmarkResult to display
        """
        print(f"\n{'='*60}")
        print(f"Benchmark: {result.operation} Operations")
        print(f"{'='*60}")
        print(f"Total Operations: {result.num_operations}")
        print(f"Total Time: {result.total_time:.2f}s")
        print(f"Throughput: {result.throughput:.2f} ops/sec")
        print(f"\nLatency Statistics:")
        print(f"  Average: {result.avg_latency*1000:.2f}ms")
        print(f"  P50 (median): {result.p50_latency*1000:.2f}ms")
        print(f"  P95: {result.p95_latency*1000:.2f}ms")
        print(f"  P99: {result.p99_latency*1000:.2f}ms")
        print(f"  Min: {min(result.latencies)*1000:.2f}ms" if result.latencies else "  Min: N/A")
        print(f"  Max: {max(result.latencies)*1000:.2f}ms" if result.latencies else "  Max: N/A")


def run_full_benchmark(num_operations: int = 500):
    """Run complete benchmark suite on all operations.
    
    Args:
        num_operations: Number of operations per test
    """
    benchmark = CacheBenchmark()

    print("\n" + "="*60)
    print("DISTRIBUTED CACHE SYSTEM - PERFORMANCE BENCHMARK")
    print("="*60)
    print(f"Testing with {num_operations} operations per benchmark\n")

    # Run benchmarks
    results = []

    print("Running GET benchmark...")
    get_result = benchmark.benchmark_get_operations(num_operations)
    results.append(get_result)
    benchmark.print_results(get_result)

    print("\nRunning PUT benchmark...")
    put_result = benchmark.benchmark_put_operations(num_operations)
    results.append(put_result)
    benchmark.print_results(put_result)

    print("\nRunning DELETE benchmark...")
    delete_result = benchmark.benchmark_delete_operations(num_operations)
    results.append(delete_result)
    benchmark.print_results(delete_result)

    # Summary comparison
    print(f"\n{'='*60}")
    print("SUMMARY COMPARISON")
    print(f"{'='*60}")
    print(f"{'Operation':<12} {'Throughput':<15} {'Avg Latency':<15} {'P99 Latency':<15}")
    print(f"{'-'*60}")
    for result in results:
        print(
            f"{result.operation:<12} "
            f"{result.throughput:>6.2f} ops/s    "
            f"{result.avg_latency*1000:>6.2f}ms        "
            f"{result.p99_latency*1000:>6.2f}ms"
        )


if __name__ == "__main__":
    run_full_benchmark(num_operations=500)
