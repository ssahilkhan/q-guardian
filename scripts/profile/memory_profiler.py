"""Memory profiling tools for Q-Guardian.

Provides snapshot tracking, allocation analysis, and leak detection
using only the Python standard library.
"""

from __future__ import annotations

import gc
import sys
import threading
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MemorySnapshot:
    """Point-in-time memory measurement."""

    timestamp: float
    total_mb: float
    resident_mb: float
    heap_mb: float
    objects_count: int
    gc_counts: dict[int, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total_mb": self.total_mb,
            "resident_mb": self.resident_mb,
            "heap_mb": self.heap_mb,
            "objects_count": self.objects_count,
            "gc_counts": self.gc_counts,
        }


@dataclass
class AllocationInfo:
    """Single allocation record from tracemalloc."""

    filename: str
    lineno: int
    size: int
    traceback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "lineno": self.lineno,
            "size": self.size,
            "size_mb": round(self.size / (1024 * 1024), 4),
            "traceback": self.traceback,
        }


def _get_resident_mb() -> float:
    """Get resident set size in MB. Returns 0 on unsupported platforms."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / 1024
    except (ImportError, AttributeError):
        return 0.0


def take_snapshot() -> MemorySnapshot:
    """Capture a single memory snapshot."""
    objects = gc.get_objects()
    gc_counts = {i: c for i, c in enumerate(gc.get_count())}
    for gen in gc.get_stats():
        idx = gc.get_stats().index(gen)
        gc_counts[idx] = gen.get("collections", gc_counts.get(idx, 0))

    heap_mb = 0.0
    if tracemalloc.is_tracing():
        current, peak = tracemalloc.get_traced_memory()
        heap_mb = current / (1024 * 1024)

    total_mb = 0.0
    try:
        import psutil  # type: ignore[import-untyped]

        total_mb = psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        total_mb = heap_mb

    return MemorySnapshot(
        timestamp=time.time(),
        total_mb=round(total_mb, 4),
        resident_mb=round(_get_resident_mb(), 4),
        heap_mb=round(heap_mb, 4),
        objects_count=len(objects),
        gc_counts=gc_counts,
    )


class MemoryProfiler:
    """Interval-based memory profiler with tracemalloc integration."""

    def __init__(self, interval: float = 1.0, top_n: int = 20) -> None:
        self.interval = interval
        self.top_n = top_n
        self._snapshots: list[MemorySnapshot] = []
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._tracemalloc_started = False
        self._tracemalloc_snapshot: tracemalloc.Snapshot | None = None

    @property
    def snapshots(self) -> list[MemorySnapshot]:
        return list(self._snapshots)

    def start(self) -> None:
        """Begin profiling. Starts tracemalloc and background snapshot thread."""
        if not tracemalloc.is_tracing():
            tracemalloc.start(10)
            self._tracemalloc_started = True
        self._stop_event.clear()
        self._snapshots.clear()
        self._tracemalloc_snapshot = None
        self._snapshots.append(take_snapshot())
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> list[MemorySnapshot]:
        """Stop profiling and return collected snapshots."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 2)
            self._thread = None
        self._snapshots.append(take_snapshot())
        # Capture tracemalloc snapshot before stopping
        if tracemalloc.is_tracing():
            self._tracemalloc_snapshot = tracemalloc.take_snapshot()
        if self._tracemalloc_started:
            tracemalloc.stop()
            self._tracemalloc_started = False
        return self.snapshots

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self.interval)
            if not self._stop_event.is_set():
                self._snapshots.append(take_snapshot())

    def top_allocations(self, snapshot: tracemalloc.Snapshot | None = None) -> list[AllocationInfo]:
        """Return the top N allocations by size."""
        if snapshot is not None:
            snap = snapshot
        elif tracemalloc.is_tracing():
            snap = tracemalloc.take_snapshot()
        elif self._tracemalloc_snapshot is not None:
            snap = self._tracemalloc_snapshot
        else:
            return []
        stats = snap.statistics("lineno")
        results: list[AllocationInfo] = []
        for stat in stats[: self.top_n]:
            frame = stat.traceback[0] if stat.traceback else None
            results.append(
                AllocationInfo(
                    filename=frame.filename if frame else "<unknown>",
                    lineno=frame.lineno if frame else 0,
                    size=stat.size,
                    traceback=str(stat.traceback),
                )
            )
        return results

    def detect_leak(self) -> dict[str, Any]:
        """Analyse snapshots for memory growth trends."""
        if len(self._snapshots) < 3:
            return {"leak_suspected": False, "reason": "insufficient_snapshots"}

        heap_values = [s.heap_mb for s in self._snapshots]
        objects_values = [s.objects_count for s in self._snapshots]

        heap_growth = heap_values[-1] - heap_values[0]
        obj_growth = objects_values[-1] - objects_values[0]
        time_span = self._snapshots[-1].timestamp - self._snapshots[0].timestamp

        heap_slope = heap_growth / time_span if time_span > 0 else 0.0
        obj_slope = obj_growth / time_span if time_span > 0 else 0.0

        suspected = heap_slope > 0.1 or obj_slope > 100

        return {
            "leak_suspected": suspected,
            "heap_growth_mb": round(heap_growth, 4),
            "heap_slope_mb_per_sec": round(heap_slope, 4),
            "object_growth": obj_growth,
            "object_slope_per_sec": round(obj_slope, 2),
            "snapshots_analysed": len(self._snapshots),
            "time_span_sec": round(time_span, 2),
        }

    def gc_statistics(self) -> dict[str, Any]:
        """Return aggregated GC statistics across all snapshots."""
        if not self._snapshots:
            return {}

        totals: dict[int, int] = {}
        for snap in self._snapshots:
            for gen, count in snap.gc_counts.items():
                totals[gen] = totals.get(gen, 0) + count

        return {
            "total_collections": sum(totals.values()),
            "by_generation": {f"gen{g}": c for g, c in sorted(totals.items())},
            "snapshot_count": len(self._snapshots),
        }

    def generate_report(self) -> dict[str, Any]:
        """Build a full analysis report from collected snapshots."""
        leak = self.detect_leak()
        gc_stats = self.gc_statistics()
        top_allocs = self.top_allocations()

        heap_values = [s.heap_mb for s in self._snapshots]
        peak_heap = max(heap_values) if heap_values else 0.0
        avg_heap = sum(heap_values) / len(heap_values) if heap_values else 0.0

        return {
            "summary": {
                "total_snapshots": len(self._snapshots),
                "peak_heap_mb": round(peak_heap, 4),
                "avg_heap_mb": round(avg_heap, 4),
                "start_objects": self._snapshots[0].objects_count if self._snapshots else 0,
                "end_objects": self._snapshots[-1].objects_count if self._snapshots else 0,
            },
            "leak_analysis": leak,
            "gc_statistics": gc_stats,
            "top_allocations": [a.to_dict() for a in top_allocs],
            "snapshots": [s.to_dict() for s in self._snapshots],
        }


class AllocationTracker:
    """Track allocation hotspots and patterns."""

    def __init__(self, size_threshold: int = 1024 * 1024) -> None:
        self.size_threshold = size_threshold
        self._records: list[AllocationInfo] = []

    def scan(self, snapshot: tracemalloc.Snapshot | None = None) -> list[AllocationInfo]:
        """Scan current tracemalloc snapshot for large allocations."""
        snap = snapshot or tracemalloc.take_snapshot()
        stats = snap.statistics("lineno")
        large: list[AllocationInfo] = []
        for stat in stats:
            if stat.size >= self.size_threshold:
                frame = stat.traceback[0] if stat.traceback else None
                info = AllocationInfo(
                    filename=frame.filename if frame else "<unknown>",
                    lineno=frame.lineno if frame else 0,
                    size=stat.size,
                    traceback=str(stat.traceback),
                )
                large.append(info)
                self._records.append(info)
        return large

    def find_patterns(self) -> dict[str, int]:
        """Aggregate allocations by filename to find hotspots."""
        by_file: dict[str, int] = {}
        for rec in self._records:
            by_file[rec.filename] = by_file.get(rec.filename, 0) + rec.size
        return dict(sorted(by_file.items(), key=lambda kv: kv[1], reverse=True))

    def clear(self) -> None:
        self._records.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold_bytes": self.size_threshold,
            "total_tracked": len(self._records),
            "total_bytes": sum(r.size for r in self._records),
            "hotspots": self.find_patterns(),
            "allocations": [r.to_dict() for r in self._records[:100]],
        }


class LeakDetector:
    """Long-running leak detector using baseline comparison."""

    def __init__(self, baseline_interval: float = 5.0, detection_threshold: float = 0.2) -> None:
        self.baseline_interval = baseline_interval
        self.detection_threshold = detection_threshold
        self._baseline: MemorySnapshot | None = None
        self._periodic: list[MemorySnapshot] = []

    def set_baseline(self) -> MemorySnapshot:
        """Take a baseline snapshot."""
        self._baseline = take_snapshot()
        return self._baseline

    def take_periodic(self) -> MemorySnapshot:
        """Take a periodic snapshot and compare against baseline."""
        snap = take_snapshot()
        self._periodic.append(snap)
        return snap

    def analyse(self) -> dict[str, Any]:
        """Compare periodic snapshots to baseline for growth detection."""
        if self._baseline is None:
            return {"error": "no_baseline_set"}

        if not self._periodic:
            return {"error": "no_periodic_snapshots"}

        results: list[dict[str, Any]] = []
        suspects: list[dict[str, Any]] = []

        for snap in self._periodic:
            heap_delta = snap.heap_mb - self._baseline.heap_mb
            obj_delta = snap.objects_count - self._baseline.objects_count
            time_delta = snap.timestamp - self._baseline.timestamp

            is_growing = heap_delta > self._baseline.heap_mb * self.detection_threshold
            entry = {
                "timestamp": snap.timestamp,
                "heap_delta_mb": round(heap_delta, 4),
                "object_delta": obj_delta,
                "time_delta_sec": round(time_delta, 2),
                "heap_growth_pct": round(
                    (heap_delta / self._baseline.heap_mb * 100) if self._baseline.heap_mb > 0 else 0,
                    2,
                ),
                "suspect": is_growing,
            }
            results.append(entry)
            if is_growing:
                suspects.append(entry)

        # Linear regression over heap values for trend
        all_heap = [self._baseline.heap_mb] + [s.heap_mb for s in self._periodic]
        n = len(all_heap)
        if n >= 2:
            x_mean = (n - 1) / 2.0
            y_mean = sum(all_heap) / n
            numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(all_heap))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            slope = numerator / denominator if denominator > 0 else 0.0
        else:
            slope = 0.0

        return {
            "baseline": self._baseline.to_dict(),
            "periodic_count": len(self._periodic),
            "heap_trend_slope_mb_per_step": round(slope, 4),
            "suspects_count": len(suspects),
            "periods": results,
            "suspects": suspects,
        }


if __name__ == "__main__":
    print("Taking a single memory snapshot...")
    snap = take_snapshot()
    print(f"  Heap:       {snap.heap_mb:.2f} MB")
    print(f"  Resident:   {snap.resident_mb:.2f} MB")
    print(f"  Objects:    {snap.objects_count:,}")
    print(f"  GC counts:  {snap.gc_counts}")

    if tracemalloc.is_tracing() or True:
        print("\nStarting profiler for 3 seconds...")
        profiler = MemoryProfiler(interval=0.5)
        profiler.start()
        # Generate some allocations
        _ = [bytearray(1024) for _ in range(500)]
        time.sleep(3)
        snaps = profiler.stop()
        report = profiler.generate_report()
        print(f"  Snapshots collected: {report['summary']['total_snapshots']}")
        print(f"  Peak heap: {report['summary']['peak_heap_mb']:.2f} MB")
        print(f"  Leak suspected: {report['leak_analysis']['leak_suspected']}")
        print(f"  Top allocations: {len(report['top_allocations'])}")
