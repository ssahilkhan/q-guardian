"""Facade over the cross-dataset analytics pipeline.

``CrossDatasetAnalytics`` normalizes inputs (objects, dicts or files),
validates compatibility, aggregates, ranks, compares classical vs quantum and
analyzes generalization, producing a single serializable
``CrossDatasetReport``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from q_guardian.analytics.aggregator import AGGREGATION_MACRO, aggregate_results

if TYPE_CHECKING:
    from q_guardian.analytics.models import NormalizedResult


class AnalyticsError(ValueError):
    """Raised when the analytics pipeline cannot process its inputs."""


class CrossDatasetAnalytics:
    """Runs the full cross-dataset analytics pipeline."""

    def __init__(self, *, aggregation_mode: str = AGGREGATION_MACRO, strict: bool = True) -> None:
        if aggregation_mode not in ("macro", "weighted", "micro"):
            raise ValueError(f"Unsupported aggregation mode: {aggregation_mode!r}")
        self.aggregation_mode = aggregation_mode
        self.strict = strict

    def analyze(self, inputs: list[Any]) -> Any:
        """Normalize, validate, aggregate and compare the given inputs.

        Accepts ``BenchmarkReport`` instances, report dicts or paths/JSON
        file paths. Returns a ``CrossDatasetReport``.
        """
        from q_guardian.analytics import comparison, compatibility, generalization, reporting
        from q_guardian.analytics.normalizer import normalize

        results: list[NormalizedResult] = []
        for item in inputs:
            results.extend(normalize(item))
        if not results:
            raise AnalyticsError("No results were produced from the provided inputs")

        check = compatibility.validate(results)
        if self.strict and not check.compatible:
            raise AnalyticsError(
                "Results are not compatible for aggregation: " + "; ".join(check.errors)
            )

        aggregation = aggregate_results(results, mode=self.aggregation_mode)
        leaderboards = reporting.build_leaderboards(results)
        comparison_report = comparison.compare_classical_quantum(results)
        gen_report = generalization.analyze_generalization(results)
        return reporting.generate_report(
            results=results,
            mode=self.aggregation_mode,
            compatibility=check,
            aggregation=aggregation,
            leaderboards=leaderboards,
            comparison=comparison_report,
            generalization=gen_report,
        )

    def from_files(self, paths: list[str | Path]) -> Any:
        """Analyze report artifacts from JSON files."""
        resolved: list[Path] = []
        for path in paths:
            candidate = Path(path)
            if candidate.is_dir():
                resolved.extend(sorted(candidate.glob("*.json")))
            elif candidate.is_file():
                resolved.append(candidate)
            else:
                raise AnalyticsError(f"Input does not exist: {path}")
        if not resolved:
            raise AnalyticsError("No report files found in the provided inputs")
        return self.analyze(resolved)

    def save(self, report: Any, output_dir: str | Path) -> dict[str, Path]:
        """Write report.json, report.csv and report.md into ``output_dir``."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "report.json"
        csv_path = out_dir / "report.csv"
        md_path = out_dir / "report.md"
        report.write_json(json_path)
        report.write_csv(csv_path)
        report.write_markdown(md_path)
        return {"json": json_path, "csv": csv_path, "markdown": md_path}

    @staticmethod
    def load_report(path: str | Path) -> dict[str, Any]:
        """Load a previously generated report JSON for inspection."""
        report_path = Path(path)
        with open(report_path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise AnalyticsError(f"Report file must contain a JSON object: {path}")
        return loaded
