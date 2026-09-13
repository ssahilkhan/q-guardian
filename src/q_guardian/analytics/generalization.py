"""Generalization analysis: internal vs external performance and consistency.

Given normalized results that carry a scope (``internal`` hold-out pools vs
``external`` datasets), this module computes the internal→external gap for the
fused detector and the cross-dataset consistency of the external results.
Everything is reported with the raw numbers; conclusions avoid extrapolation
beyond the measured datasets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from q_guardian.analytics import provider as provider_module
from q_guardian.analytics.models import (
    SCOPE_EXTERNAL,
    SCOPE_INTERNAL,
    NormalizedResult,
)
from q_guardian.observability.analytics.statistics import StatisticsEngine

_GAP_METRICS = (
    "f1_score",
    "roc_auc",
    "recall",
    "specificity",
    "accuracy",
)


@dataclass
class ScopeSummary:
    """Aggregate of one metric over one scope (internal or external)."""

    metric: str
    scope: str
    mean: float
    std: float | None
    min: float | None
    max: float | None
    datasets: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "scope": self.scope,
            "mean": self.mean,
            "std": self.std,
            "min": self.min,
            "max": self.max,
            "datasets": self.datasets,
        }


@dataclass
class GapReport:
    """Internal→external gap for the fused detector on one metric."""

    metric: str
    internal_mean: float
    external_mean: float
    gap: float
    internal_datasets: int
    external_datasets: int
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "internal_mean": self.internal_mean,
            "external_mean": self.external_mean,
            "gap": self.gap,
            "internal_datasets": self.internal_datasets,
            "external_datasets": self.external_datasets,
            "note": self.note,
        }


@dataclass
class GeneralizationReport:
    """Full generalization analysis for a collection of results."""

    provider: str
    per_external: list[dict[str, Any]] = field(default_factory=list)
    external_summary: dict[str, Any] = field(default_factory=dict)
    gaps: list[GapReport] = field(default_factory=list)
    conclusion: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "per_external": self.per_external,
            "external_summary": self.external_summary,
            "gaps": [gap.as_dict() for gap in self.gaps],
            "conclusion": self.conclusion,
        }


def analyze_generalization(
    results: list[NormalizedResult],
    provider: str = provider_module.FUSION_PROVIDER,
) -> GeneralizationReport:
    """Analyze internal vs external generalization for a provider."""
    internal = [result for result in results if result.scope == SCOPE_INTERNAL]
    external = [result for result in results if result.scope == SCOPE_EXTERNAL]

    per_external: list[dict[str, Any]] = []
    for result in external:
        stats = result.provider_metric(provider, "f1_score")
        roc = result.provider_metric(provider, "roc_auc")
        per_external.append(
            {
                "dataset_id": result.dataset_id,
                "samples": result.samples,
                "f1": stats.mean if stats is not None else None,
                "roc_auc": roc.mean if roc is not None else None,
            }
        )

    gaps: list[GapReport] = []
    for metric in _GAP_METRICS:
        internal_values = _collect(internal, provider, metric)
        external_values = _collect(external, provider, metric)
        if not internal_values or not external_values:
            continue
        internal_mean = StatisticsEngine.mean(internal_values)
        external_mean = StatisticsEngine.mean(external_values)
        note = ""
        if len(external_values) < 2:
            note = "single external dataset; gap is not conclusive evidence of a trend"
        gaps.append(
            GapReport(
                metric=metric,
                internal_mean=round(internal_mean, 6),
                external_mean=round(external_mean, 6),
                gap=round(external_mean - internal_mean, 6),
                internal_datasets=len(internal_values),
                external_datasets=len(external_values),
                note=note,
            )
        )

    external_summary: dict[str, Any] = {}
    for metric in ("f1_score", "roc_auc", "accuracy"):
        values = _collect(external, provider, metric)
        if values:
            external_summary[metric] = {
                "mean": round(StatisticsEngine.mean(values), 6),
                "std": (
                    _rounded_optional(StatisticsEngine.std_dev(values)) if len(values) > 1 else None
                ),
                "min": round(min(values), 6),
                "max": round(max(values), 6),
                "datasets": len(values),
            }

    conclusion = _conclusion(internal, external, gaps, provider)
    return GeneralizationReport(
        provider=provider,
        per_external=per_external,
        external_summary=external_summary,
        gaps=gaps,
        conclusion=conclusion,
    )


def _collect(
    results: list[NormalizedResult],
    provider: str,
    metric: str,
) -> list[float]:
    values: list[float] = []
    for result in results:
        stats = result.provider_metric(provider, metric)
        if stats is not None:
            values.append(stats.mean)
    return values


def _conclusion(
    internal: list[NormalizedResult],
    external: list[NormalizedResult],
    gaps: list[GapReport],
    provider: str,
) -> str:
    if not internal:
        return "No internal (hold-out) results present; generalization gap cannot be computed."
    if not external:
        return "No external dataset results present; generalization gap cannot be computed."
    if not gaps:
        return "No overlapping metrics between internal and external results."

    f1_gap = next((gap for gap in gaps if gap.metric == "f1_score"), None)
    auc_gap = next((gap for gap in gaps if gap.metric == "roc_auc"), None)
    if f1_gap is not None and auc_gap is not None:
        parts = [
            f"Fused {_provider_label(provider)} F1 drops by "
            f"{-f1_gap.gap:.4f} from internal ({f1_gap.internal_mean:.4f}) to external "
            f"({f1_gap.external_mean:.4f}); ROC-AUC {(auc_gap.gap):+.4f}."
        ]
        if len(external) < 2:
            parts.append("Evidence rests on a single external dataset and is not conclusive.")
        else:
            parts.append(
                "External consistency is reported in external_summary (mean/std/min/max across "
                f"{len(external)} external datasets)."
            )
        return " ".join(parts)
    return " ".join(f"{gap.metric}: {gap.gap:+.4f}" for gap in gaps)


def _provider_label(provider: str) -> str:
    if provider == provider_module.FUSION_PROVIDER:
        return "fusion"
    return provider


def _rounded_optional(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return round(value, 6)
