"""Core load testing engine for Q-Guardian.

Provides configurable async load testing with latency tracking,
throughput measurement, memory profiling, and comprehensive results.
"""

from __future__ import annotations

import asyncio
import statistics
import time
import tracemalloc
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoadTestConfig:
    """Configuration for a load test run."""

    concurrent_sessions: int = 100
    duration_seconds: float = 30.0
    ramp_up_seconds: float = 5.0
    target_sessions: int = 100

    def __post_init__(self) -> None:
        if self.concurrent_sessions < 1:
            raise ValueError("concurrent_sessions must be >= 1")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0")
        if self.ramp_up_seconds < 0:
            raise ValueError("ramp_up_seconds must be >= 0")
        if self.ramp_up_seconds > self.duration_seconds:
            raise ValueError("ramp_up_seconds must be <= duration_seconds")


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LoadTestResult:
    """Comprehensive results from a load test run."""

    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    peak_latency_ms: float = 0.0
    throughput_rps: float = 0.0
    duration_seconds: float = 0.0
    memory_peak_mb: float = 0.0
    memory_avg_mb: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    scenario_name: str = ""
    config: LoadTestConfig | None = None

    def summary_dict(self) -> dict[str, Any]:
        """Return a serializable summary dictionary."""
        return {
            "scenario_name": self.scenario_name,
            "total_requests": self.total_requests,
            "successful": self.successful,
            "failed": self.failed,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "peak_latency_ms": round(self.peak_latency_ms, 2),
            "throughput_rps": round(self.throughput_rps, 2),
            "duration_seconds": round(self.duration_seconds, 2),
            "memory_peak_mb": round(self.memory_peak_mb, 2),
            "memory_avg_mb": round(self.memory_avg_mb, 2),
        }


# ---------------------------------------------------------------------------
# Scenario ABC
# ---------------------------------------------------------------------------


class LoadTestScenario(ABC):
    """Abstract base class for load test scenarios.

    Subclass this to define a specific workload.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable scenario name."""

    @abstractmethod
    async def setup(self, config: LoadTestConfig) -> None:
        """One-time setup before the scenario runs.

        Called once before the load test begins. Use this to
        initialize shared resources, create guardians, etc.
        """

    @abstractmethod
    async def execute_session(self, session_id: int) -> bool:
        """Execute a single session/work unit.

        Called concurrently by the engine. Returns True on success,
        False on failure. Each call should be self-contained.

        Args:
            session_id: A unique integer for this concurrent unit.
        """

    @abstractmethod
    async def teardown(self) -> None:
        """Cleanup after the scenario completes.

        Called once after the load test finishes. Close resources here.
        """


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class LoadTestEngine:
    """Async load testing engine with ramp-up, latency tracking,
    and memory measurement.
    """

    def __init__(self, config: LoadTestConfig) -> None:
        self._config = config

    async def run(self, scenario: LoadTestScenario) -> LoadTestResult:
        """Run a load test scenario and return results.

        Uses a producer/consumer model: a launcher task continuously
        spawns single-request worker tasks. The semaphore limits
        in-flight concurrency. Workers stop being created after
        ``duration_seconds`` and in-flight workers are awaited.

        Args:
            scenario: The scenario to execute.

        Returns:
            Comprehensive LoadTestResult.
        """
        await scenario.setup(self._config)

        latencies: list[float] = []
        errors: list[dict[str, Any]] = []
        successful = 0
        failed = 0
        lock = asyncio.Lock()

        semaphore = asyncio.Semaphore(self._config.concurrent_sessions)

        # Memory tracking
        tracemalloc.start()
        mem_samples: list[int] = []
        process: Any = None

        if _HAS_PSUTIL:
            process = psutil.Process()

        start_time = time.perf_counter()

        async def _execute_one(request_id: int) -> None:
            nonlocal successful, failed
            async with semaphore:
                req_start = time.perf_counter()
                try:
                    ok = await scenario.execute_session(request_id)
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    async with lock:
                        errors.append({
                            "session_id": request_id,
                            "error": str(exc),
                            "time": time.perf_counter() - start_time,
                        })

                req_end = time.perf_counter()
                latency_ms = (req_end - req_start) * 1000.0
                async with lock:
                    latencies.append(latency_ms)
                    if ok:
                        successful += 1
                    else:
                        failed += 1

            # Sample memory after each request
            current, _peak = tracemalloc.get_traced_memory()
            mem_samples.append(current)
            if process is not None:
                try:
                    process.memory_info()
                except (psutil.Error, OSError):
                    pass

        async def _launcher() -> list[asyncio.Task[None]]:
            """Launch worker tasks for the duration of the test."""
            tasks: list[asyncio.Task[None]] = []
            request_id = 0
            end_time = start_time + self._config.duration_seconds

            while time.perf_counter() < end_time:
                elapsed = time.perf_counter() - start_time
                # Ramp-up: delay task creation proportionally
                if self._config.ramp_up_seconds > 0 and elapsed < self._config.ramp_up_seconds:
                    # During ramp-up, launch at reduced rate
                    progress = elapsed / self._config.ramp_up_seconds
                    active_slots = max(1, int(self._config.concurrent_sessions * progress))
                    # Small sleep to avoid spinning during ramp-up
                    await asyncio.sleep(0.005)
                else:
                    active_slots = self._config.concurrent_sessions

                # Only launch if we have capacity
                in_flight = sum(1 for t in tasks if not t.done())
                if in_flight < active_slots:
                    task = asyncio.create_task(_execute_one(request_id))
                    tasks.append(task)
                    request_id += 1
                else:
                    await asyncio.sleep(0.001)

            return tasks

        # Run launcher and collect all tasks
        tasks = await _launcher()

        # Wait for all in-flight tasks to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.perf_counter()
        actual_duration = end_time - start_time

        tracemalloc.stop()

        total_requests = successful + failed
        error_rate = failed / total_requests if total_requests > 0 else 0.0
        throughput = total_requests / actual_duration if actual_duration > 0 else 0.0

        # Latency statistics
        sorted_lat = sorted(latencies) if latencies else [0.0]
        avg_lat = statistics.mean(sorted_lat)
        p50 = _percentile(sorted_lat, 50)
        p95 = _percentile(sorted_lat, 95)
        p99 = _percentile(sorted_lat, 99)
        peak_lat = max(sorted_lat) if sorted_lat else 0.0

        # Memory statistics
        if mem_samples:
            mem_avg = statistics.mean(mem_samples) / (1024 * 1024)
            mem_peak = max(mem_samples) / (1024 * 1024)
        else:
            mem_avg = 0.0
            mem_peak = 0.0

        await scenario.teardown()

        return LoadTestResult(
            total_requests=total_requests,
            successful=successful,
            failed=failed,
            error_rate=error_rate,
            avg_latency_ms=avg_lat,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            peak_latency_ms=peak_lat,
            throughput_rps=throughput,
            duration_seconds=actual_duration,
            memory_peak_mb=mem_peak,
            memory_avg_mb=mem_avg,
            latencies_ms=latencies,
            errors=errors,
            scenario_name=scenario.name,
            config=self._config,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(data: list[float], pct: float) -> float:
    """Calculate the p-th percentile from sorted data."""
    if not data:
        return 0.0
    k = (len(data) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(data):
        return data[-1]
    return data[f] + (k - f) * (data[c] - data[f])
