"""Canonical data model for cross-dataset analytics.

Every supported source artifact (benchmark report, evaluation report, baseline
metrics file) is normalized onto ``NormalizedResult`` before aggregation. The
model keeps the original sample sizes and measurement provenance so aggregate
reports can always state where each number came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Canonical metric ordering for tables. Keys not listed here are rendered
# after the canonical block in sorted order.
CANONICAL_METRIC_ORDER = [
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
]

METRIC_LABELS: dict[str, str] = {
    "accuracy": "Accuracy",
    "precision": "Precision",
    "recall": "Recall",
    "specificity": "Specificity",
    "f1_score": "F1",
    "roc_auc": "ROC-AUC",
    "pr_auc": "PR-AUC",
    "matthews_corrcoef": "MCC",
    "expected_calibration_error": "ECE",
    "brier_score": "Brier",
    "false_positive_rate": "FPR",
    "false_negative_rate": "FNR",
}

HIGHER_IS_BETTER_METRICS = {
    "accuracy",
    "precision",
    "recall",
    "specificity",
    "f1_score",
    "roc_auc",
    "pr_auc",
    "matthews_corrcoef",
}

SOURCE_BENCHMARK = "benchmark"
SOURCE_EVALUATION = "evaluation"
SOURCE_BASELINE = "baseline"

SCOPE_INTERNAL = "internal"
SCOPE_EXTERNAL = "external"
SCOPE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class MetricStats:
    """Distribution summary for one (provider, metric) pair.

    ``std`` / ``min`` / ``max`` are optional: benchmark runs provide fold
    statistics, while single-pass evaluation rows do not. A missing
    distribution is rendered as ``-`` and never synthesized.
    """

    mean: float
    std: float | None = None
    min: float | None = None
    max: float | None = None

    @classmethod
    def from_scalar(cls, value: float) -> MetricStats:
        """Build stats from a single measured value (no fold distribution)."""
        return cls(mean=value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mean": self.mean,
            "std": self.std,
            "min": self.min,
            "max": self.max,
        }


@dataclass
class NormalizedResult:
    """One measured run of the detector on one dataset (or pool).

    ``metrics`` maps ``provider -> metric key -> MetricStats``. ``scope``
    records whether the run is over internal hold-out pools, external
    datasets, or unknown provenance, which drives the generalization
    analysis.
    """

    dataset_id: str
    name: str
    source: str
    metrics: dict[str, dict[str, MetricStats]] = field(default_factory=dict)
    scope: str = SCOPE_UNKNOWN
    pool: str | None = None
    samples: int = 0
    malicious: int = 0
    benign: int = 0
    license: str = ""
    homepage: str = ""
    available: bool = True
    note: str = ""
    fold_count: int | None = None
    seed: int | None = None
    threshold: float | None = None
    evaluator: dict[str, Any] = field(default_factory=dict)
    origin_path: str = "<in-memory>"

    @property
    def providers(self) -> list[str]:
        """Provider ids present in this result, in insertion order."""
        return list(self.metrics)

    def provider_metric(self, provider: str, metric: str) -> MetricStats | None:
        """Return the metric stats for a provider, or ``None``."""
        provider_metrics = self.metrics.get(provider)
        if provider_metrics is None:
            return None
        return provider_metrics.get(metric)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "source": self.source,
            "scope": self.scope,
            "pool": self.pool,
            "samples": self.samples,
            "malicious": self.malicious,
            "benign": self.benign,
            "available": self.available,
            "note": self.note,
            "fold_count": self.fold_count,
            "seed": self.seed,
            "threshold": self.threshold,
            "evaluator": self.evaluator,
            "origin_path": self.origin_path,
            "metrics": {
                provider: {metric: stats.as_dict() for metric, stats in provider_metrics.items()}
                for provider, provider_metrics in self.metrics.items()
            },
        }


def ordered_metric_keys(metrics: dict[str, MetricStats]) -> list[str]:
    """Return metric keys ordered canonically, then alphabetically."""
    present = set(metrics)
    ordered = [key for key in CANONICAL_METRIC_ORDER if key in present]
    ordered.extend(sorted(present - set(CANONICAL_METRIC_ORDER)))
    return ordered


def metric_label(metric: str) -> str:
    """Human-readable label for a metric key."""
    return METRIC_LABELS.get(metric, metric)
