"""Aggregate report generation: JSON, CSV and Markdown renderers.

The ``CrossDatasetReport`` bundles every analysis stage (compatibility,
per-dataset results, aggregation, leaderboards, classical/quantum comparison,
generalization) into one serializable document, and renders it as a flat CSV
long-table plus a human-readable Markdown report.
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from q_guardian.analytics.compatibility import CompatibilityReport
from q_guardian.analytics.models import (
    NormalizedResult,
    metric_label,
)

if TYPE_CHECKING:
    from q_guardian.analytics.aggregator import CrossDatasetAggregation
    from q_guardian.analytics.comparison import ClassicalQuantumComparison
    from q_guardian.analytics.generalization import GeneralizationReport
    from q_guardian.analytics.ranking import Leaderboard

_RANKING_METRICS = ("roc_auc", "f1_score")


@dataclass
class CrossDatasetReport:
    """The complete cross-dataset analytics report."""

    generated_at: str
    mode: str
    inputs: list[NormalizedResult] = field(default_factory=list)
    compatibility: CompatibilityReport = field(default_factory=CompatibilityReport)
    aggregation: CrossDatasetAggregation | None = None
    leaderboards: dict[str, Leaderboard] = field(default_factory=dict)
    comparison: ClassicalQuantumComparison | None = None
    generalization: GeneralizationReport | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "report_type": "cross-dataset-analytics",
            "generated_at": self.generated_at,
            "aggregation_mode": self.mode,
            "inputs": [result.as_dict() for result in self.inputs],
            "compatibility": self.compatibility.as_dict(),
            "aggregation": self.aggregation.as_dict() if self.aggregation else None,
            "leaderboards": {
                metric: board.as_dict() for metric, board in self.leaderboards.items()
            },
            "comparison": self.comparison.as_dict() if self.comparison else None,
            "generalization": self.generalization.as_dict() if self.generalization else None,
        }

    def to_markdown(self) -> str:
        """Render the report as Markdown for humans and CI."""
        lines: list[str] = [
            "# Q-Guardian Cross-Dataset Analytics Report",
            "",
            f"- Generated: {self.generated_at}",
            f"- Aggregation mode: {self.mode}",
            f"- Datasets: {len(self.inputs)}",
            "",
        ]
        lines.extend(self._inputs_markdown())
        lines.extend(self._compatibility_markdown())
        if self.aggregation is not None:
            lines.extend(self._aggregation_markdown())
        if self.leaderboards:
            lines.extend(self._leaderboards_markdown())
        if self.comparison is not None:
            lines.extend(self._comparison_markdown())
        if self.generalization is not None:
            lines.extend(self._generalization_markdown())
        return "\n".join(lines) + "\n"

    def to_csv(self) -> str:
        """Render the report as a flat CSV long-table for pivoting."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "report_type",
                "dataset_id",
                "source",
                "scope",
                "samples",
                "provider",
                "class",
                "metric",
                "mean",
                "std",
                "datasets",
                "mode",
            ]
        )
        for result in self.inputs:
            for provider, provider_metrics in result.metrics.items():
                for metric, stats in provider_metrics.items():
                    writer.writerow(
                        [
                            "dataset",
                            result.dataset_id,
                            result.source,
                            result.scope,
                            result.samples,
                            provider,
                            _provider_class(provider),
                            metric,
                            _csv_num(stats.mean),
                            _csv_num(stats.std),
                            len(self.inputs),
                            "",
                        ]
                    )
        if self.aggregation is not None:
            for pid, provider_aggregate in self.aggregation.providers.items():
                for metric, aggregate in provider_aggregate.metrics.items():
                    writer.writerow(
                        [
                            "aggregate",
                            "",
                            "",
                            "",
                            "",
                            pid,
                            _provider_class(pid),
                            metric,
                            _csv_num(aggregate.mean),
                            _csv_num(aggregate.std),
                            aggregate.datasets,
                            self.mode,
                        ]
                    )
        for metric, board in self.leaderboards.items():
            for pid in board.order():
                entry = board.providers[pid]
                writer.writerow(
                    [
                        "leaderboard",
                        "",
                        "",
                        "",
                        "",
                        pid,
                        _provider_class(pid),
                        metric,
                        _csv_num(entry.mean_value),
                        "",
                        entry.datasets_ranked,
                        f"rank:{entry.average_rank}",
                    ]
                )
        return output.getvalue()

    def write_json(self, path: str | Path) -> None:
        _write_text(path, json.dumps(self.as_dict(), indent=2, ensure_ascii=False))

    def write_markdown(self, path: str | Path) -> None:
        _write_text(path, self.to_markdown())

    def write_csv(self, path: str | Path) -> None:
        _write_text(path, self.to_csv())

    # ── markdown sections ─────────────────────────────────────────

    def _inputs_markdown(self) -> list[str]:
        lines = ["## Inputs", ""]
        lines.append("| Dataset | Source | Scope | Pool | Samples | Threshold | Providers |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for result in self.inputs:
            lines.append(
                f"| {_esc(result.dataset_id)} | {result.source} | {result.scope} "
                f"| {_esc(result.pool or '')} | {result.samples} "
                f"| {_fmt(result.threshold, 4)} | {_esc(', '.join(result.providers))} |"
            )
        lines.append("")
        return lines

    def _compatibility_markdown(self) -> list[str]:
        lines = ["## Compatibility", ""]
        if self.compatibility.compatible:
            status = "**YES**"
        else:
            status = "**NO (correct the errors before relying on the report)**"
        lines.append(f"Compatible for aggregation: {status}")
        if self.compatibility.errors:
            lines.append("Errors:")
            for error in self.compatibility.errors:
                lines.append(f"- {_esc(error)}")
            lines.append("")
        if self.compatibility.warnings:
            lines.append("Warnings:")
            for warning in self.compatibility.warnings:
                lines.append(f"- {_esc(warning)}")
            lines.append("")
        else:
            lines.append("No warnings.")
            lines.append("")
        return lines

    def _aggregation_markdown(self) -> list[str]:
        if self.aggregation is None:
            return []
        lines = [f"## Cross-dataset aggregates (mode: `{self.mode}`)", ""]
        if self.aggregation.fallback_count:
            lines.append(
                f"> Note: {self.aggregation.fallback_count} result(s) had unknown sample "
                "sizes and used weight 1.0 in this mode."
            )
            lines.append("")
        for pid, aggregate in self.aggregation.providers.items():
            title = f"### {_provider_label(pid)}"
            lines.append(title)
            lines.append("")
            rows = list(aggregate.metrics.items())
            if not rows:
                lines.append("_No comparable metrics._")
                lines.append("")
                continue
            rows.sort(key=lambda item: _metric_sort_key(item[0]))
            lines.append("| Metric | Mean | Std | Datasets |")
            lines.append("| --- | --- | --- | --- |")
            for metric, entry in rows:
                lines.append(
                    f"| {metric_label(metric)} | {_fmt(entry.mean, 4)} "
                    f"| {_fmt(entry.std, 4)} | {entry.datasets} |"
                )
            lines.append("")
        return lines

    def _leaderboards_markdown(self) -> list[str]:
        lines = ["## Cross-dataset ranking (average rank)", ""]
        for metric, board in self.leaderboards.items():
            lines.append(f"### Ranking by {metric_label(metric)}")
            lines.append("")
            lines.append("| Rank | Provider | Class | Avg rank | Datasets | Mean value |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for rank, pid in enumerate(board.order(), start=1):
                entry = board.providers[pid]
                lines.append(
                    f"| {rank} | {_provider_label(pid)} | {_provider_class(pid)} "
                    f"| {_fmt(entry.average_rank, 4)} | {entry.datasets_ranked} "
                    f"| {_fmt(entry.mean_value, 4)} |"
                )
            lines.append("")
        return lines

    def _comparison_markdown(self) -> list[str]:
        if self.comparison is None:
            return []
        lines = ["## Classical vs quantum", ""]
        summary_lines = 0
        for cls, summary in self.comparison.classes.items():
            if not summary.providers:
                continue
            lines.append(f"### {_class_label(cls)}")
            lines.append("")
            lines.append(f"- Providers: {_esc(', '.join(summary.providers))}")
            lines.append(f"- Datasets: {_esc(', '.join(summary.datasets))}")
            lines.append("")
            lines.append("| Metric | Mean | Std | Datasets |")
            lines.append("| --- | --- | --- | --- |")
            for metric, entry in summary.metrics.items():
                lines.append(
                    f"| {metric_label(metric)} | {_fmt(entry.mean, 4)} "
                    f"| {_fmt(entry.std, 4)} | {entry.datasets} |"
                )
            lines.append("")
            summary_lines += 1
        if not summary_lines:
            lines.append("_Neither classical nor quantum results were available._")
            lines.append("")
        if self.comparison.deltas:
            lines.append("### Deltas (classical minus quantum)")
            lines.append("")
            lines.append("| Metric | Classical | Quantum | Delta (C-Q) | Conclusion |")
            lines.append("| --- | --- | --- | --- | --- |")
            for metric, delta in self.comparison.deltas.items():
                lines.append(
                    f"| {metric_label(metric)} | {_fmt(delta.classical_mean, 4)} "
                    f"| {_fmt(delta.quantum_mean, 4)} | {_fmt(delta.delta, 4)} "
                    f"| {_esc(delta.conclusion)} |"
                )
            lines.append("")
        if self.comparison.conclusions:
            lines.append("### Conclusion")
            lines.append("")
            for conclusion in self.comparison.conclusions:
                lines.append(f"- {_esc(conclusion)}")
            lines.append("")
        return lines

    def _generalization_markdown(self) -> list[str]:
        if self.generalization is None:
            return []
        report = self.generalization
        lines = ["## Generalization", ""]
        lines.append(f"- Provider: `{report.provider}` (internal vs external pools)")
        lines.append("")
        if report.per_external:
            lines.append("### External per-dataset results")
            lines.append("")
            lines.append("| Dataset | Samples | F1 | ROC-AUC |")
            lines.append("| --- | --- | --- | --- |")
            for row in report.per_external:
                lines.append(
                    f"| {_esc(row['dataset_id'])} | {row['samples']} "
                    f"| {_fmt(row['f1'], 4)} | {_fmt(row['roc_auc'], 4)} |"
                )
            lines.append("")
        if report.external_summary:
            lines.append("### External consistency")
            lines.append("")
            lines.append("| Metric | Mean | Std | Min | Max | Datasets |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for metric in sorted(report.external_summary):
                entry = report.external_summary[metric]
                lines.append(
                    f"| {metric_label(metric)} | {_fmt(entry['mean'], 4)} "
                    f"| {_fmt(entry['std'], 4)} | {_fmt(entry['min'], 4)} "
                    f"| {_fmt(entry['max'], 4)} | {entry['datasets']} |"
                )
            lines.append("")
        if report.gaps:
            lines.append("### Internal -> external gaps")
            lines.append("")
            lines.append("| Metric | Internal | External | Delta (E-I) | Note |")
            lines.append("| --- | --- | --- | --- | --- |")
            for gap in report.gaps:
                lines.append(
                    f"| {metric_label(gap.metric)} | {_fmt(gap.internal_mean, 4)} "
                    f"| {_fmt(gap.external_mean, 4)} | {_fmt(gap.gap, 4)} "
                    f"| {_esc(gap.note)} |"
                )
            lines.append("")
        if report.conclusion:
            lines.append("### Conclusion")
            lines.append("")
            lines.append(report.conclusion)
            lines.append("")
        return lines


def _provider_label(provider: str) -> str:
    from q_guardian.analytics import provider as provider_module

    if provider == provider_module.FUSION_PROVIDER:
        return "Fusion"
    return provider


def _provider_class(provider: str) -> str:
    from q_guardian.analytics import provider as provider_module

    return provider_module.provider_class(provider)


def _class_label(cls: str) -> str:
    from q_guardian.analytics import provider as provider_module

    return provider_module.class_label(cls)


def _fmt(value: Any, precision: int) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "-"
    if isinstance(value, float):
        return f"{value:.{precision}f}"
    return str(value)


def _csv_num(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _esc(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _write_text(path: str | Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generate_report(
    results: list[NormalizedResult],
    *,
    mode: str,
    compatibility: CompatibilityReport,
    aggregation: CrossDatasetAggregation,
    leaderboards: dict[str, Leaderboard],
    comparison: ClassicalQuantumComparison,
    generalization: GeneralizationReport | None,
) -> CrossDatasetReport:
    """Assemble a report document from the analysis stages."""
    return CrossDatasetReport(
        generated_at=datetime.now(UTC).isoformat(),
        mode=mode,
        inputs=list(results),
        compatibility=compatibility,
        aggregation=aggregation,
        leaderboards=leaderboards,
        comparison=comparison,
        generalization=generalization,
    )


def build_leaderboards(results: list[NormalizedResult]) -> dict[str, Leaderboard]:
    """Build leaderboards for the default ranking metrics."""
    from q_guardian.analytics.ranking import build_leaderboard

    boards: dict[str, Leaderboard] = {}
    for metric in _RANKING_METRICS:
        board = build_leaderboard(results, metric=metric)
        if board.providers:
            boards[metric] = board
    return boards


def _metric_sort_key(metric: str) -> int:
    from q_guardian.analytics.models import CANONICAL_METRIC_ORDER

    if metric in CANONICAL_METRIC_ORDER:
        return CANONICAL_METRIC_ORDER.index(metric)
    return len(CANONICAL_METRIC_ORDER)
