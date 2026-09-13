"""Cross-dataset metric aggregation.

Supports three aggregation modes:

* ``macro`` — unweighted mean of per-dataset means (each dataset is equal).
* ``weighted`` — dataset-size weighted mean of per-dataset means.
* ``micro`` — pooled estimate over samples (approximated as the sample-size
  weighted mean of per-dataset means; true micro pooling would require the
  per-sample outcome table, which is only present in out-of-fold score files).

Distributions across datasets use the sample standard deviation. When only one
dataset contributes, the standard deviation is ``None`` — an empty estimation
never masquerades as a measurement spread.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from q_guardian.analytics import provider as provider_module
from q_guardian.observability.analytics.statistics import StatisticsEngine

if TYPE_CHECKING:
    from q_guardian.analytics.models import NormalizedResult

AGGREGATION_MACRO = "macro"
AGGREGATION_WEIGHTED = "weighted"
AGGREGATION_MICRO = "micro"

VALID_MODES = (AGGREGATION_MACRO, AGGREGATION_WEIGHTED, AGGREGATION_MICRO)


class AggregationMode(StrEnum):
    MACRO = AGGREGATION_MACRO
    WEIGHTED = AGGREGATION_WEIGHTED
    MICRO = AGGREGATION_MICRO


@dataclass
class AggregateMetric:
    """Cross-dataset aggregate for one (provider, metric) pair."""

    metric: str
    mean: float
    std: float | None
    datasets: int
    dataset_means: list[float] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "mean": self.mean,
            "std": self.std,
            "datasets": self.datasets,
            "dataset_means": self.dataset_means,
            "weights": self.weights,
        }


@dataclass
class ProviderAggregate:
    """Aggregate metrics for one provider across datasets."""

    provider: str
    cls: str
    metrics: dict[str, AggregateMetric] = field(default_factory=dict)
    datasets: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "class": self.cls,
            "datasets": self.datasets,
            "metrics": {metric: aggregate.as_dict() for metric, aggregate in self.metrics.items()},
        }


@dataclass
class CrossDatasetAggregation:
    """The full cross-dataset aggregation table for a collection."""

    mode: str
    providers: dict[str, ProviderAggregate] = field(default_factory=dict)
    datasets: list[str] = field(default_factory=list)
    fallback_count: int = 0

    @property
    def provider_ids(self) -> list[str]:
        return list(self.providers)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "datasets": self.datasets,
            "weighted_fallback_count": self.fallback_count,
            "providers": {pid: value.as_dict() for pid, value in self.providers.items()},
        }


def _provider_sort_key(pid: str) -> tuple[int, int, str]:
    if pid == provider_module.FUSION_PROVIDER:
        return (0, 0, pid)
    cls = provider_module.provider_class(pid)
    rank = 0 if cls == "classical" else 1 if cls == "quantum" else 2
    return (1, rank, pid)


def aggregate_results(
    results: list[NormalizedResult],
    mode: str = AGGREGATION_MACRO,
) -> CrossDatasetAggregation:
    """Aggregate normalized results across datasets in the requested mode."""
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported aggregation mode: {mode!r}")
    weighted = mode in (AGGREGATION_WEIGHTED, AGGREGATION_MICRO)

    datasets = [result.dataset_id for result in results]
    providers = sorted({provider for result in results for provider in result.providers})

    fallback_count = sum(1 for result in results if weighted and result.samples <= 0)

    provider_aggregates: dict[str, ProviderAggregate] = {}
    for pid in providers:
        provider_results = [result for result in results if pid in result.providers]
        metrics_union: dict[str, list[tuple[NormalizedResult, float]]] = {}
        for result in provider_results:
            for metric, stats in result.metrics[pid].items():
                metrics_union.setdefault(metric, []).append((result, stats.mean))

        aggregate_metrics: dict[str, AggregateMetric] = {}
        for metric, pairs in sorted(metrics_union.items()):
            means = [value for _result, value in pairs]
            weights = _weights_for(pairs, weighted)
            if weighted:
                mean_value = _weighted_mean(means, weights)
                std_value = _weighted_std(means, weights)
            else:
                mean_value = StatisticsEngine.mean(means)
                std_value = StatisticsEngine.std_dev(means) if len(means) > 1 else None
            aggregate_metrics[metric] = AggregateMetric(
                metric=metric,
                mean=round(float(mean_value), 6),
                std=_rounded_optional(std_value),
                datasets=len(means),
                dataset_means=means,
                weights=weights,
            )

        provider_aggregates[pid] = ProviderAggregate(
            provider=pid,
            cls=provider_module.provider_class(pid),
            datasets=list(dict.fromkeys(result.dataset_id for result in provider_results)),
            metrics=aggregate_metrics,
        )

    return CrossDatasetAggregation(
        mode=mode,
        providers=provider_aggregates,
        datasets=datasets,
        fallback_count=fallback_count,
    )


def _weights_for(
    pairs: list[tuple[NormalizedResult, float]],
    weighted: bool,
) -> list[float]:
    if not weighted:
        return [1.0] * len(pairs)
    return [float(result.samples) if result.samples > 0 else 1.0 for result, _value in pairs]


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    total = sum(weights)
    if total <= 0:
        return StatisticsEngine.mean(values)
    return sum(value * weight for value, weight in zip(values, weights, strict=False)) / total


def _weighted_std(values: list[float], weights: list[float]) -> float | None:
    if len(values) < 2:
        return None
    total = sum(weights)
    if total <= 0:
        return StatisticsEngine.std_dev(values)
    mean = _weighted_mean(values, weights)
    variance = sum(
        weight * (value - mean) ** 2 for value, weight in zip(values, weights, strict=False)
    )
    return math.sqrt(variance)


def _rounded_optional(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return round(value, 6)
