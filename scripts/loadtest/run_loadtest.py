"""Load test runner for Q-Guardian.

CLI entry point for executing load test scenarios with configurable
profiles and output formats.

Usage::

    python -m scripts.loadtest.run_loadtest
    python -m scripts.loadtest.run_loadtest --profile medium
    python -m scripts.loadtest.run_loadtest --scenario prompt_scan --duration 60
    python -m scripts.loadtest.run_loadtest --concurrency 500 --target 5000
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.loadtest.load_tester import LoadTestConfig, LoadTestEngine, LoadTestResult
from scripts.loadtest.reporter import LoadTestReporter
from scripts.loadtest.scenarios import (
    BurstScenario,
    MixedWorkloadScenario,
    PromptScanScenario,
    SessionLifecycleScenario,
)

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

_PROFILES: dict[str, dict[str, int]] = {
    "quick": {
        "concurrent_sessions": 50,
        "target_sessions": 100,
        "duration_seconds": 15,
        "ramp_up_seconds": 3,
    },
    "medium": {
        "concurrent_sessions": 200,
        "target_sessions": 500,
        "duration_seconds": 30,
        "ramp_up_seconds": 5,
    },
    "heavy": {
        "concurrent_sessions": 500,
        "target_sessions": 1000,
        "duration_seconds": 60,
        "ramp_up_seconds": 10,
    },
    "extreme": {
        "concurrent_sessions": 1000,
        "target_sessions": 5000,
        "duration_seconds": 120,
        "ramp_up_seconds": 20,
    },
}

_SCENARIO_MAP: dict[str, type] = {
    "prompt_scan": PromptScanScenario,
    "session_lifecycle": SessionLifecycleScenario,
    "mixed_workload": MixedWorkloadScenario,
    "burst": BurstScenario,
}

_RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loadtest",
        description="Q-Guardian Load Testing Framework",
    )
    parser.add_argument(
        "--profile",
        choices=list(_PROFILES.keys()),
        default="quick",
        help="Pre-defined load profile (default: quick)",
    )
    parser.add_argument(
        "--scenario",
        choices=[*list(_SCENARIO_MAP.keys()), "all"],
        default="all",
        help="Scenario to run (default: all)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Override concurrent sessions count",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Override test duration in seconds",
    )
    parser.add_argument(
        "--ramp-up",
        type=float,
        default=None,
        help="Override ramp-up period in seconds",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=None,
        help="Override target session count",
    )
    parser.add_argument(
        "--output",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format (default: both)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        default=True,
        help="Save results to results/ directory (default: true)",
    )
    parser.add_argument(
        "--compare",
        type=str,
        default=None,
        help="Path to a previous results JSON for comparison",
    )
    return parser


def _build_config(args: argparse.Namespace) -> LoadTestConfig:
    profile = _PROFILES[args.profile]
    duration = args.duration if args.duration is not None else float(profile["duration_seconds"])
    ramp_up = args.ramp_up if args.ramp_up is not None else float(profile["ramp_up_seconds"])
    # Clamp ramp_up so it never exceeds duration
    ramp_up = min(ramp_up, duration)
    return LoadTestConfig(
        concurrent_sessions=args.concurrency or profile["concurrent_sessions"],
        target_sessions=args.target or profile["target_sessions"],
        duration_seconds=duration,
        ramp_up_seconds=ramp_up,
    )


def _save_result(result: LoadTestResult, scenario_name: str) -> Path:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"{scenario_name}_{ts}.json"
    path = _RESULTS_DIR / filename
    path.write_text(LoadTestReporter.to_json(result), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run(args: argparse.Namespace) -> None:
    config = _build_config(args)

    scenarios_to_run: list[str] = (
        list(_SCENARIO_MAP.keys()) if args.scenario == "all" else [args.scenario]
    )

    all_results: list[LoadTestResult] = []
    engine = LoadTestEngine(config)

    for scenario_name in scenarios_to_run:
        scenario_cls = _SCENARIO_MAP[scenario_name]
        scenario: object
        if scenario_name == "burst":
            scenario = BurstScenario(burst_size=config.concurrent_sessions)
        else:
            scenario = scenario_cls()

        print(f"\n{'=' * 60}")
        print(f"Running scenario: {scenario_name}")
        print(f"  Concurrency: {config.concurrent_sessions}")
        print(f"  Duration:    {config.duration_seconds}s")
        print(f"  Ramp-up:     {config.ramp_up_seconds}s")
        print(f"{'=' * 60}\n")

        result = await engine.run(scenario)
        all_results.append(result)

        if args.output in ("markdown", "both"):
            print(LoadTestReporter.to_markdown(result))

        if args.output in ("json", "both"):
            if args.output == "both":
                print("\n--- JSON ---\n")
            print(LoadTestReporter.to_json(result))

        if args.save:
            path = _save_result(result, scenario_name)
            print(f"\nResults saved to: {path}")

    # Comparison
    if args.compare and all_results:
        compare_path = Path(args.compare)
        if compare_path.exists():
            baseline_data = json.loads(compare_path.read_text(encoding="utf-8"))
            if isinstance(baseline_data, list):
                baseline_data = baseline_data[0] if baseline_data else {}
            baseline = LoadTestResult(
                **{k: v for k, v in baseline_data.items() if k != "latencies_ms"}
            )
            baseline.latencies_ms = baseline_data.get("latencies_ms", [])
            current = all_results[0]
            print(f"\n{'=' * 60}")
            print("Comparison with baseline")
            print(f"{'=' * 60}\n")
            print(LoadTestReporter.compare_markdown(baseline, current))
        else:
            print(f"\nWarning: comparison file not found: {args.compare}")

    # Summary table for all scenarios
    if len(all_results) > 1:
        print(f"\n{'=' * 60}")
        print("Summary")
        print(f"{'=' * 60}\n")
        print(
            f"{'Scenario':<25} {'Requests':>10} {'Errors':>8} "
            f"{'Avg(ms)':>10} {'P95(ms)':>10} {'RPS':>10}"
        )
        print("-" * 75)
        for r in all_results:
            print(
                f"{r.scenario_name:<25} {r.total_requests:>10,} "
                f"{r.error_rate:>7.2%} {r.avg_latency_ms:>10.2f} "
                f"{r.p95_latency_ms:>10.2f} {r.throughput_rps:>10.2f}"
            )

    print(f"\nAll {len(all_results)} scenario(s) completed.")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
