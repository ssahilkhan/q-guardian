from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.benchmarks.benchmark_runner import BenchmarkResult, BenchmarkSuite
from scripts.benchmarks.benchmarks import (
    ALL_BENCHMARKS,
    EventBusBenchmark,
    MLEngineBenchmark,
    ObservabilityBenchmark,
    PolicyBenchmark,
    PromptSecurityBenchmark,
    RuntimeBenchmark,
    StartupBenchmark,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Q-Guardian Benchmark Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=100,
        help="Number of measured iterations (default: 100)",
    )
    parser.add_argument(
        "--warmup",
        "-w",
        type=int,
        default=10,
        help="Number of warmup iterations (default: 10)",
    )
    parser.add_argument(
        "--output-format",
        "-f",
        choices=["json", "text", "both"],
        default="both",
        help="Output format: json, text, or both (default: both)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output file path for JSON results",
    )
    parser.add_argument(
        "--suites",
        nargs="*",
        default=None,
        help="Run specific benchmark suites (default: all). Choices: "
        + " ".join(name for name, _ in ALL_BENCHMARKS),
    )
    parser.add_argument(
        "--compare",
        type=str,
        default=None,
        help="Path to a previous JSON results file to compare against",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default=None,
        help="Path to a baseline JSON results file to compare against",
    )
    return parser.parse_args()


async def _run_startup(iterations: int, warmup: int) -> list[BenchmarkResult]:
    return await StartupBenchmark(iterations=iterations, warmup=warmup).run()


async def _run_prompt_security(iterations: int, warmup: int) -> list[BenchmarkResult]:
    return await PromptSecurityBenchmark(iterations=iterations, warmup=warmup).run()


async def _run_policy(iterations: int, warmup: int) -> list[BenchmarkResult]:
    return await PolicyBenchmark(iterations=iterations, warmup=warmup).run()


async def _run_event_bus(iterations: int, warmup: int) -> list[BenchmarkResult]:
    return await EventBusBenchmark(iterations=iterations, warmup=warmup).run()


async def _run_runtime(iterations: int, warmup: int) -> list[BenchmarkResult]:
    return await RuntimeBenchmark(iterations=iterations, warmup=warmup).run()


async def _run_observability(iterations: int, warmup: int) -> list[BenchmarkResult]:
    return await ObservabilityBenchmark(iterations=iterations, warmup=warmup).run()


async def _run_ml(iterations: int, warmup: int) -> list[BenchmarkResult]:
    return await MLEngineBenchmark(iterations=iterations, warmup=warmup).run()


_SUITE_RUNNERS: dict[str, tuple[str, any]] = {
    "startup": ("Startup", _run_startup),
    "prompt_security": ("Prompt Security", _run_prompt_security),
    "policy": ("Policy Engine", _run_policy),
    "event_bus": ("Event Bus", _run_event_bus),
    "runtime": ("Runtime", _run_runtime),
    "observability": ("Observability", _run_observability),
    "ml": ("ML Inference", _run_ml),
}


async def _run_all_benchmarks(
    iterations: int, warmup: int, suites: list[str] | None = None
) -> BenchmarkSuite:
    suite = BenchmarkSuite(name="q-guardian-benchmarks")
    active_suites = suites or list(_SUITE_RUNNERS.keys())

    for suite_name in active_suites:
        if suite_name not in _SUITE_RUNNERS:
            print(f"Unknown suite: {suite_name}, skipping")
            continue

        label, runner = _SUITE_RUNNERS[suite_name]
        print(f"\nRunning {label} benchmarks...")
        try:
            results = await runner(iterations, warmup)
            for r in results:
                suite.add(r)
                print(f"  {r.name}: {r.avg_us:.1f} us/iter ({r.ops_per_sec:.0f} ops/s)")
        except Exception as e:
            print(f"  ERROR in {label}: {e}")

    return suite


def _print_results(suite: BenchmarkSuite, fmt: str) -> None:
    if fmt in ("text", "both"):
        suite.print_table()
    if fmt in ("json", "both"):
        print(f"\n{suite.to_json()}")


def _compare_results(suite: BenchmarkSuite, baseline_path: str) -> None:
    try:
        baseline = BenchmarkSuite.load_json(baseline_path)
        comparisons = suite.compare_with(baseline)
        print(f"\n{'=' * 120}")
        print(f"  Comparison with baseline: {baseline.name}")
        print(f"{'=' * 120}")
        print(
            f"{'Benchmark':<45} {'Baseline avg':>14} {'Current avg':>14} {'Delta %':>10} {'Status':>10}"
        )
        print(f"{'-' * 120}")
        for comp in comparisons:
            if comp["status"] == "new":
                print(f"{comp['name']:<45} {'N/A':>14} {'N/A':>14} {'N/A':>10} {'NEW':>10}")
            else:
                status = "REGRESS" if comp["regression"] else "OK"
                print(
                    f"{comp['name']:<45} "
                    f"{comp['baseline_avg_us']:>14.1f} "
                    f"{comp['current_avg_us']:>14.1f} "
                    f"{comp['avg_delta_pct']:>+9.2f}% "
                    f"{status:>10}"
                )
        print(f"{'=' * 120}")
    except Exception as e:
        print(f"\nComparison failed: {e}")


def _save_results(suite: BenchmarkSuite, output_path: str | None, fmt: str) -> Path | None:
    if output_path:
        path = Path(output_path)
    else:
        ts = int(time.time())
        path = Path(f"scripts/benchmarks/results_{ts}.json")

    saved = suite.save_json(path)
    print(f"\nResults saved to: {saved}")
    return saved


async def main() -> None:
    args = _parse_args()

    print("=" * 80)
    print("  Q-Guardian Benchmark Suite")
    print(f"  Iterations: {args.iterations}  |  Warmup: {args.warmup}")
    print(f"  Format: {args.output_format}")
    print("=" * 80)

    suite = await _run_all_benchmarks(args.iterations, args.warmup, args.suites)

    _print_results(suite, args.output_format)

    saved_path = _save_results(suite, args.output, args.output_format)

    if args.compare or args.baseline:
        baseline_path = args.compare or args.baseline
        if baseline_path:
            _compare_results(suite, baseline_path)


if __name__ == "__main__":
    asyncio.run(main())
