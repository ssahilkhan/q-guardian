"""Load test reporting for Q-Guardian.

Generates markdown and JSON reports from LoadTestResult objects,
supports run comparison, and identifies performance regressions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from scripts.loadtest.load_tester import LoadTestResult

# ---------------------------------------------------------------------------
# Thresholds for regression detection
# ---------------------------------------------------------------------------

_ERROR_RATE_REGRESSION_THRESHOLD: float = 0.05  # 5 % absolute increase
_LATENCY_REGRESSION_FACTOR: float = 1.5  # 50 % slower
_THROUGHPUT_REGRESSION_FACTOR: float = 0.7  # 30 % slower throughput


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


class LoadTestReporter:
    """Generates human-readable and machine-readable reports."""

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    @staticmethod
    def to_markdown(result: LoadTestResult) -> str:
        """Generate a markdown report from a single result.

        Args:
            result: The load test result.

        Returns:
            Markdown-formatted report string.
        """
        lines: list[str] = []
        lines.append(f"# Load Test Report — `{result.scenario_name}`")
        lines.append("")
        lines.append(f"*Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}*")
        lines.append("")

        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Requests | {result.total_requests:,} |")
        lines.append(f"| Successful | {result.successful:,} |")
        lines.append(f"| Failed | {result.failed:,} |")
        lines.append(f"| Error Rate | {result.error_rate:.2%} |")
        lines.append(f"| Duration | {result.duration_seconds:.2f}s |")
        lines.append(f"| Throughput | {result.throughput_rps:.2f} req/s |")
        lines.append("")

        lines.append("## Latency")
        lines.append("")
        lines.append("| Percentile | Latency (ms) |")
        lines.append("|------------|--------------|")
        lines.append(f"| Avg | {result.avg_latency_ms:.2f} |")
        lines.append(f"| P50 | {result.p50_latency_ms:.2f} |")
        lines.append(f"| P95 | {result.p95_latency_ms:.2f} |")
        lines.append(f"| P99 | {result.p99_latency_ms:.2f} |")
        lines.append(f"| Peak | {result.peak_latency_ms:.2f} |")
        lines.append("")

        lines.append("## Memory")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Peak | {result.memory_peak_mb:.2f} MB |")
        lines.append(f"| Average | {result.memory_avg_mb:.2f} MB |")
        lines.append("")

        if result.errors:
            lines.append("## Errors")
            lines.append("")
            lines.append(f"Total errors: {len(result.errors)}")
            lines.append("")
            # Show first 10 errors
            for err in result.errors[:10]:
                lines.append(
                    f"- session={err.get('session_id', '?')} "
                    f"error=`{err.get('error', 'unknown')}` "
                    f"time={err.get('time', 0):.2f}s"
                )
            if len(result.errors) > 10:
                lines.append(f"- ... and {len(result.errors) - 10} more")
            lines.append("")

        if result.config:
            lines.append("## Configuration")
            lines.append("")
            lines.append("| Parameter | Value |")
            lines.append("|-----------|-------|")
            lines.append(f"| Concurrent Sessions | {result.config.concurrent_sessions} |")
            lines.append(f"| Target Sessions | {result.config.target_sessions} |")
            lines.append(f"| Ramp-up Seconds | {result.config.ramp_up_seconds} |")
            lines.append(f"| Duration Seconds | {result.config.duration_seconds} |")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Comparison markdown
    # ------------------------------------------------------------------

    @staticmethod
    def compare_markdown(
        baseline: LoadTestResult,
        current: LoadTestResult,
    ) -> str:
        """Generate a side-by-side comparison report.

        Args:
            baseline: The reference result.
            current: The result to compare against baseline.

        Returns:
            Markdown comparison report.
        """
        lines: list[str] = []
        lines.append("# Load Test Comparison")
        lines.append("")
        lines.append(f"*Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}*")
        lines.append("")
        lines.append(
            f"**Baseline:** `{baseline.scenario_name}` ({baseline.total_requests} requests)"
        )
        lines.append(f"**Current:** `{current.scenario_name}` ({current.total_requests} requests)")
        lines.append("")

        lines.append("## Metrics Comparison")
        lines.append("")
        lines.append("| Metric | Baseline | Current | Change |")
        lines.append("|--------|----------|---------|--------|")

        rows = [
            ("Error Rate", f"{baseline.error_rate:.2%}", f"{current.error_rate:.2%}"),
            (
                "Avg Latency (ms)",
                f"{baseline.avg_latency_ms:.2f}",
                f"{current.avg_latency_ms:.2f}",
            ),
            (
                "P95 Latency (ms)",
                f"{baseline.p95_latency_ms:.2f}",
                f"{current.p95_latency_ms:.2f}",
            ),
            (
                "P99 Latency (ms)",
                f"{baseline.p99_latency_ms:.2f}",
                f"{current.p99_latency_ms:.2f}",
            ),
            (
                "Throughput (req/s)",
                f"{baseline.throughput_rps:.2f}",
                f"{current.throughput_rps:.2f}",
            ),
            (
                "Memory Peak (MB)",
                f"{baseline.memory_peak_mb:.2f}",
                f"{current.memory_peak_mb:.2f}",
            ),
        ]

        for label, base_val, cur_val in rows:
            lines.append(f"| {label} | {base_val} | {cur_val} | — |")

        lines.append("")

        regressions = LoadTestReporter.detect_regressions(baseline, current)
        if regressions:
            lines.append("## Regressions Detected")
            lines.append("")
            for reg in regressions:
                lines.append(f"- {reg}")
            lines.append("")
        else:
            lines.append("## No Regressions Detected")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    @staticmethod
    def to_json(result: LoadTestResult) -> str:
        """Generate a JSON report string.

        Args:
            result: The load test result.

        Returns:
            JSON-formatted string.
        """
        data = result.summary_dict()
        data["latencies_ms"] = (
            result.latencies_ms[:1000] if len(result.latencies_ms) > 1000 else result.latencies_ms
        )
        data["errors"] = result.errors[:100]
        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def results_to_json(results: list[LoadTestResult]) -> str:
        """Serialize multiple results to JSON.

        Args:
            results: List of load test results.

        Returns:
            JSON array string.
        """
        return json.dumps(
            [r.summary_dict() for r in results],
            indent=2,
            default=str,
        )

    # ------------------------------------------------------------------
    # Regression detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_regressions(
        baseline: LoadTestResult,
        current: LoadTestResult,
    ) -> list[str]:
        """Identify performance regressions between two runs.

        Args:
            baseline: The reference result.
            current: The result to compare.

        Returns:
            List of human-readable regression descriptions.
        """
        regressions: list[str] = []

        error_delta = current.error_rate - baseline.error_rate
        if error_delta > _ERROR_RATE_REGRESSION_THRESHOLD:
            regressions.append(
                f"Error rate increased by {error_delta:.2%} "
                f"({baseline.error_rate:.2%} -> {current.error_rate:.2%})"
            )

        if baseline.avg_latency_ms > 0:
            ratio = current.avg_latency_ms / baseline.avg_latency_ms
            if ratio >= _LATENCY_REGRESSION_FACTOR:
                regressions.append(
                    f"Average latency increased by "
                    f"{(ratio - 1) * 100:.1f}% "
                    f"({baseline.avg_latency_ms:.2f}ms -> "
                    f"{current.avg_latency_ms:.2f}ms)"
                )

        if baseline.p95_latency_ms > 0:
            ratio = current.p95_latency_ms / baseline.p95_latency_ms
            if ratio >= _LATENCY_REGRESSION_FACTOR:
                regressions.append(
                    f"P95 latency increased by "
                    f"{(ratio - 1) * 100:.1f}% "
                    f"({baseline.p95_latency_ms:.2f}ms -> "
                    f"{current.p95_latency_ms:.2f}ms)"
                )

        if baseline.throughput_rps > 0:
            ratio = current.throughput_rps / baseline.throughput_rps
            if ratio <= _THROUGHPUT_REGRESSION_FACTOR:
                regressions.append(
                    f"Throughput decreased by "
                    f"{(1 - ratio) * 100:.1f}% "
                    f"({baseline.throughput_rps:.2f}rps -> "
                    f"{current.throughput_rps:.2f}rps)"
                )

        if baseline.memory_peak_mb > 0:
            mem_ratio = current.memory_peak_mb / baseline.memory_peak_mb
            if mem_ratio >= 2.0:
                regressions.append(
                    f"Peak memory doubled "
                    f"({baseline.memory_peak_mb:.2f}MB -> "
                    f"{current.memory_peak_mb:.2f}MB)"
                )

        return regressions


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python reporter.py <results.json> [baseline.json]")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        for item in data:
            result = LoadTestResult(**{k: v for k, v in item.items() if k != "latencies_ms"})
            result.latencies_ms = item.get("latencies_ms", [])
            print(LoadTestReporter.to_markdown(result))
    else:
        result = LoadTestResult(**{k: v for k, v in data.items() if k != "latencies_ms"})
        result.latencies_ms = data.get("latencies_ms", [])
        print(LoadTestReporter.to_markdown(result))

    if len(sys.argv) >= 3:
        with open(sys.argv[2], encoding="utf-8") as f:
            baseline_data = json.load(f)
        baseline = LoadTestResult(**{k: v for k, v in baseline_data.items() if k != "latencies_ms"})
        baseline.latencies_ms = baseline_data.get("latencies_ms", [])
        print("\n--- COMPARISON ---\n")
        print(LoadTestReporter.compare_markdown(baseline, result))
