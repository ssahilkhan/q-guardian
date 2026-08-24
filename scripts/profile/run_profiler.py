"""CLI runner for Q-Guardian memory profiler.

Usage::

    python -m scripts.profile.run_profiler snapshot
    python -m scripts.profile.run_profiler monitor --duration 30 --interval 1
    python -m scripts.profile.run_profiler leak-detect --duration 60
    python -m scripts.profile.run_profiler analyze --output report.json
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path
from typing import Any

from scripts.profile.memory_profiler import (
    AllocationTracker,
    LeakDetector,
    MemoryProfiler,
    take_snapshot,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory-profiler",
        description="Q-Guardian Memory Profiling Tools",
    )
    sub = parser.add_subparsers(dest="mode", help="Profiling mode")

    # snapshot
    snap = sub.add_parser("snapshot", help="Take a single memory snapshot")
    snap.add_argument("--json", action="store_true", help="Output raw JSON")

    # monitor
    mon = sub.add_parser("monitor", help="Monitor memory over time")
    mon.add_argument(
        "--duration", type=float, default=10.0, help="Duration in seconds (default: 10)"
    )
    mon.add_argument(
        "--interval", type=float, default=1.0, help="Snapshot interval in seconds (default: 1)"
    )
    mon.add_argument("--output", type=str, default=None, help="Output file path for JSON report")

    # leak-detect
    leak = sub.add_parser("leak-detect", help="Detect potential memory leaks")
    leak.add_argument(
        "--duration", type=float, default=30.0, help="Detection duration in seconds (default: 30)"
    )
    leak.add_argument(
        "--interval", type=float, default=2.0, help="Snapshot interval in seconds (default: 2)"
    )
    leak.add_argument("--output", type=str, default=None, help="Output file path for JSON report")

    # analyze
    analyse = sub.add_parser("analyze", help="Analyse current tracemalloc state")
    analyse.add_argument(
        "--threshold",
        type=int,
        default=1024 * 1024,
        help="Large allocation threshold in bytes (default: 1MB)",
    )
    analyse.add_argument(
        "--top", type=int, default=20, help="Number of top allocations to show (default: 20)"
    )
    analyse.add_argument(
        "--output", type=str, default=None, help="Output file path for JSON report"
    )

    return parser


def _snapshot_mode(args: argparse.Namespace) -> None:
    snap = take_snapshot()
    if args.json:
        print(json.dumps(snap.to_dict(), indent=2))
    else:
        print(f"{'Memory Snapshot':=^50}")
        print(f"  Heap:       {snap.heap_mb:.2f} MB")
        print(f"  Resident:   {snap.resident_mb:.2f} MB")
        print(f"  Total:      {snap.total_mb:.2f} MB")
        print(f"  Objects:    {snap.objects_count:,}")
        print(f"  GC counts:  {snap.gc_counts}")


def _monitor_mode(args: argparse.Namespace) -> None:
    print(f"Monitoring memory for {args.duration:.0f}s (interval: {args.interval:.1f}s)...")
    profiler = MemoryProfiler(interval=args.interval)
    profiler.start()
    time.sleep(args.duration)
    profiler.stop()
    report = profiler.generate_report()

    _print_monitor_summary(report)

    if args.output:
        _save_json(report, args.output)


def _leak_detect_mode(args: argparse.Namespace) -> None:
    print(f"Running leak detection for {args.duration:.0f}s...")
    detector = LeakDetector()
    detector.set_baseline()
    print("  Baseline captured.")

    elapsed = 0.0
    while elapsed < args.duration:
        time.sleep(args.interval)
        detector.take_periodic()
        elapsed += args.interval
        print(f"  Snapshot at {elapsed:.1f}s")

    result = detector.analyse()
    _print_leak_summary(result)

    if args.output:
        _save_json(result, args.output)


def _analyze_mode(args: argparse.Namespace) -> None:
    print("Analysing tracemalloc allocations...")
    try:
        import tracemalloc

        tracemalloc.start(10)
    except Exception:
        pass

    tracker = AllocationTracker(size_threshold=args.threshold)
    large = tracker.scan()
    patterns = tracker.find_patterns()

    profiler = MemoryProfiler(top_n=args.top)
    top_allocs = profiler.top_allocations()

    report: dict[str, Any] = {
        "large_allocations_count": len(large),
        "large_allocations": [a.to_dict() for a in large],
        "file_hotspots": patterns,
        "top_allocations": [a.to_dict() for a in top_allocs],
    }

    print(f"  Large allocations (>= {args.threshold / 1024 / 1024:.1f} MB): {len(large)}")
    print("  Top file hotspots:")
    for fname, size in list(patterns.items())[:5]:
        print(f"    {fname}: {size / 1024 / 1024:.2f} MB")

    if args.output:
        _save_json(report, args.output)
        print(f"\nReport saved to {args.output}")

    try:
        import tracemalloc as _t

        if _t.is_tracing():
            _t.stop()
    except Exception:
        pass


def _print_monitor_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    leak = report["leak_analysis"]

    print(f"\n{'Monitoring Summary':=^50}")
    print(f"  Snapshots:     {summary['total_snapshots']}")
    print(f"  Peak heap:     {summary['peak_heap_mb']:.2f} MB")
    print(f"  Avg heap:      {summary['avg_heap_mb']:.2f} MB")
    print(f"  Object delta:  {summary['end_objects'] - summary['start_objects']:,}")
    print(f"  Leak suspect:  {leak['leak_suspected']}")
    if leak["leak_suspected"]:
        print(f"    Heap slope:  {leak['heap_slope_mb_per_sec']:.4f} MB/s")
        print(f"    Obj slope:   {leak['object_slope_per_sec']:.1f} obj/s")

    gc_stats = report.get("gc_statistics", {})
    if gc_stats.get("total_collections", 0) > 0:
        print(f"  GC collections: {gc_stats['total_collections']}")
        for gen, count in gc_stats.get("by_generation", {}).items():
            print(f"    {gen}: {count}")

    if report.get("top_allocations"):
        print(f"\n  Top {len(report['top_allocations'])} allocations:")
        for alloc in report["top_allocations"][:5]:
            print(f"    {alloc['filename']}:{alloc['lineno']} - {alloc['size_mb']:.4f} MB")


def _print_leak_summary(result: dict[str, Any]) -> None:
    print(f"\n{'Leak Detection Summary':=^50}")
    if "error" in result:
        print(f"  Error: {result['error']}")
        return

    print(f"  Baseline heap:   {result['baseline']['heap_mb']:.2f} MB")
    print(f"  Snapshots taken: {result['periodic_count']}")
    print(f"  Heap trend:      {result['heap_trend_slope_mb_per_step']:.4f} MB/step")
    print(f"  Suspects:        {result['suspects_count']}")

    for suspect in result["suspects"][:5]:
        print(
            f"    +{suspect['time_delta_sec']:.1f}s: "
            f"+{suspect['heap_delta_mb']:.2f} MB "
            f"({suspect['heap_growth_pct']:.1f}%)"
        )


def _save_json(data: dict[str, Any], path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"\nReport saved to {p}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.mode is None:
        parser.print_help()
        sys.exit(0)

    gc.disable()

    mode_map = {
        "snapshot": _snapshot_mode,
        "monitor": _monitor_mode,
        "leak-detect": _leak_detect_mode,
        "analyze": _analyze_mode,
    }

    try:
        mode_map[args.mode](args)
    except KeyboardInterrupt:
        print("\nProfiling interrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
