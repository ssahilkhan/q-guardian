"""Classical vs quantum provider comparison.

Aggregates per-dataset provider results into per-class summaries and compares
classical and quantum performance metric by metric. Advantage claims are
guarded: a difference is only described as an advantage when it exceeds the
combined cross-dataset uncertainty. When quantum results are absent, the
comparison says so instead of silently comparing to an empty estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from q_guardian.analytics import provider as provider_module
from q_guardian.analytics.models import (
    HIGHER_IS_BETTER_METRICS,
    MetricStats,
    NormalizedResult,
)
from q_guardian.observability.analytics.statistics import StatisticsEngine

_OUTCOME_METRICS = (
    "accuracy",
    "precision",
    "recall",
    "specificity",
    "f1_score",
    "roc_auc",
    "pr_auc",
    "matthews_corrcoef",
    "expected_calibration_error",
    "brier_score",
    "false_positive_rate",
    "false_negative_rate",
)


@dataclass
class ClassMetric:
    """Per-class, per-metric cross-dataset summary."""

    metric: str
    mean: float
    std: float | None
    datasets: int
    providers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "mean": self.mean,
            "std": self.std,
            "datasets": self.datasets,
            "providers": self.providers,
        }


@dataclass
class ClassSummary:
    """Cross-dataset summary for one provider class."""

    cls: str
    providers: list[str] = field(default_factory=list)
    metrics: dict[str, ClassMetric] = field(default_factory=dict)
    datasets: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "class": self.cls,
            "providers": self.providers,
            "datasets": self.datasets,
            "metrics": {metric: value.as_dict() for metric, value in self.metrics.items()},
        }


@dataclass
class ComparisonDelta:
    """One metric's classical-minus-quantum delta and its conclusion."""

    metric: str
    classical_mean: float | None
    quantum_mean: float | None
    delta: float | None
    conclusion: str
    higher_is_better: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "classical_mean": self.classical_mean,
            "quantum_mean": self.quantum_mean,
            "delta": self.delta,
            "conclusion": self.conclusion,
            "higher_is_better": self.higher_is_better,
        }


@dataclass
class ClassicalQuantumComparison:
    """Full classical vs quantum comparison for a collection of results."""

    classes: dict[str, ClassSummary] = field(default_factory=dict)
    deltas: dict[str, ComparisonDelta] = field(default_factory=dict)
    conclusions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "classes": {cls: value.as_dict() for cls, value in self.classes.items()},
            "deltas": {metric: value.as_dict() for metric, value in self.deltas.items()},
            "conclusions": self.conclusions,
        }


_COMPARABLE_CLASSES = ("classical", "quantum", "fusion")


def compare_classical_quantum(results: list[NormalizedResult]) -> ClassicalQuantumComparison:
    """Compare classical, quantum and fusion classes across datasets."""
    summaries = _build_class_summaries(results)
    deltas = _build_deltas(summaries)
    conclusions = _build_conclusions(summaries, deltas)
    return ClassicalQuantumComparison(
        classes=summaries,
        deltas=deltas,
        conclusions=conclusions,
    )


def _build_class_summaries(
    results: list[NormalizedResult],
) -> dict[str, ClassSummary]:
    summaries: dict[str, ClassSummary] = {cls: ClassSummary(cls=cls) for cls in _COMPARABLE_CLASSES}
    members: dict[str, dict[str, list[tuple[NormalizedResult, dict[str, MetricStats]]]]] = {}
    for result in results:
        for pid, provider_metrics in result.metrics.items():
            cls = provider_module.provider_class(pid)
            if cls not in _COMPARABLE_CLASSES:
                continue
            if pid not in summaries[cls].providers:
                summaries[cls].providers.append(pid)
            if result.dataset_id not in summaries[cls].datasets:
                summaries[cls].datasets.append(result.dataset_id)
            members.setdefault(cls, {}).setdefault(pid, []).append((result, provider_metrics))

    for cls, summary in summaries.items():
        if not summary.providers:
            continue
        metric_pool: dict[str, list[float]] = {}
        for _pid, pairs in members[cls].items():
            for _result, provider_metrics in pairs:
                for metric in _OUTCOME_METRICS:
                    stats = provider_metrics.get(metric)
                    if stats is not None:
                        metric_pool.setdefault(metric, []).append(stats.mean)
        for metric, values in metric_pool.items():
            datasets = _count_datasets_with_metric(_sub_results(cls, members), metric)
            summary.metrics[metric] = ClassMetric(
                metric=metric,
                mean=round(StatisticsEngine.mean(values), 6),
                std=(
                    _rounded_optional(StatisticsEngine.std_dev(values)) if len(values) > 1 else None
                ),
                datasets=datasets,
                providers=summary.providers,
            )
    return summaries


def _sub_results(
    cls: str,
    members: dict[str, dict[str, list[tuple[NormalizedResult, dict[str, MetricStats]]]]],
) -> list[NormalizedResult]:
    results: list[NormalizedResult] = []
    for pairs in members.get(cls, {}).values():
        results.extend(result for result, _provider_metrics in pairs)
    return results


def _count_datasets_with_metric(results: list[NormalizedResult], metric: str) -> int:
    dataset_ids: set[str] = set()
    for result in results:
        if any(metric in provider_metrics for provider_metrics in result.metrics.values()):
            dataset_ids.add(result.dataset_id)
    return len(dataset_ids)


def _build_deltas(summaries: dict[str, ClassSummary]) -> dict[str, ComparisonDelta]:
    classical = summaries.get("classical")
    quantum = summaries.get("quantum")
    deltas: dict[str, ComparisonDelta] = {}
    if classical is None or quantum is None or not classical.providers or not quantum.providers:
        return deltas
    metrics = sorted(set(classical.metrics) & set(quantum.metrics))
    for metric in metrics:
        classical_mean = classical.metrics[metric].mean
        quantum_mean = quantum.metrics[metric].mean
        higher_is_better = metric in HIGHER_IS_BETTER_METRICS
        delta_value = classical_mean - quantum_mean
        conclusion = _delta_conclusion(
            metric,
            classical_mean,
            quantum_mean,
            classical.metrics[metric].std,
            quantum.metrics[metric].std,
            classical.metrics[metric].datasets,
            quantum.metrics[metric].datasets,
            higher_is_better,
        )
        deltas[metric] = ComparisonDelta(
            metric=metric,
            classical_mean=classical_mean,
            quantum_mean=quantum_mean,
            delta=round(delta_value, 6),
            conclusion=conclusion,
            higher_is_better=higher_is_better,
        )
    return deltas


def _delta_conclusion(
    metric: str,
    classical: float,
    quantum: float,
    classical_std: float | None,
    quantum_std: float | None,
    classical_datasets: int,
    quantum_datasets: int,
    higher_is_better: bool,
) -> str:
    def _favors_classical(direction: float) -> bool:
        return direction > 0.0 if higher_is_better else direction < 0.0

    direction = classical - quantum
    if classical_datasets < 2 or quantum_datasets < 2:
        return "single-dataset evidence only; not conclusive"
    if classical_std is None or quantum_std is None:
        return "no cross-dataset spread recorded; not conclusive"
    combined = classical_std + quantum_std
    if abs(direction) <= combined:
        return "within cross-dataset uncertainty; no clear advantage"
    if _favors_classical(direction):
        return f"classical {metric} exceeds quantum beyond combined uncertainty"
    return f"quantum {metric} exceeds classical beyond combined uncertainty"


def _build_conclusions(
    summaries: dict[str, ClassSummary],
    deltas: dict[str, ComparisonDelta],
) -> list[str]:
    conclusions: list[str] = []
    classical = summaries.get("classical")
    quantum = summaries.get("quantum")

    if classical is None or not classical.providers:
        conclusions.append("No classical providers present; comparison not possible.")
    if quantum is None or not quantum.providers:
        conclusions.append("No quantum provider results present; comparison not possible.")
        return conclusions
    if classical is None:
        return conclusions

    winner_metrics = [metric for metric, delta in deltas.items() if "exceeds" in delta.conclusion]
    if winner_metrics:
        conclusions.append(
            "Differences beyond combined uncertainty were observed on: "
            + ", ".join(sorted(winner_metrics))
            + ". These are per-dataset aggregate comparisons, not paired "
            "statistical tests."
        )
    else:
        conclusion = "No classical/quantum difference exceeds combined cross-dataset uncertainty."
        if deltas:
            appraise = next(iter(deltas.values()))
            if "single-dataset" in appraise.conclusion:
                conclusion = "Results rest on single-dataset evidence; no advantage is claimed."
        conclusions.append(conclusion)
    return conclusions


def _rounded_optional(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return round(value, 6)
