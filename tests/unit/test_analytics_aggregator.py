"""Unit tests for cross-dataset metric aggregation."""

from __future__ import annotations

import math

import pytest

from q_guardian.analytics.aggregator import (
    aggregate_results,
)
from q_guardian.analytics.models import MetricStats, NormalizedResult


def _result(
    dataset_id: str,
    *,
    roc: float = 0.8,
    samples: int = 100,
    provider: str = "fusion",
) -> NormalizedResult:
    return NormalizedResult(
        dataset_id=dataset_id,
        name=dataset_id,
        source="benchmark",
        samples=samples,
        metrics={provider: {"roc_auc": MetricStats.from_scalar(roc)}},
    )


class TestMacroAggregation:
    def test_macro_mean_across_datasets(self) -> None:
        results = [_result("ds-a", roc=0.85), _result("ds-b", roc=0.95)]
        agg = aggregate_results(results, mode="macro")

        assert agg.providers["fusion"].metrics["roc_auc"].mean == pytest.approx(0.9)
        assert agg.providers["fusion"].metrics["roc_auc"].datasets == 2

    def test_macro_std_for_two_datasets(self) -> None:
        results = [_result("ds-a", roc=0.85), _result("ds-b", roc=0.95)]
        agg = aggregate_results(results, mode="macro")
        expected_std = math.sqrt(((0.85 - 0.9) ** 2 + (0.95 - 0.9) ** 2) / 1)

        agg_std = agg.providers["fusion"].metrics["roc_auc"].std
        assert agg_std == pytest.approx(expected_std, abs=1e-4)

    def test_single_dataset_has_no_std(self) -> None:
        agg = aggregate_results([_result("ds-a", roc=0.85)], mode="macro")

        assert agg.providers["fusion"].metrics["roc_auc"].std is None


class TestWeightedAggregation:
    def test_weighted_mean_is_size_weighted(self) -> None:
        results = [_result("ds-a", roc=0.8, samples=100), _result("ds-b", roc=0.9, samples=300)]
        agg = aggregate_results(results, mode="weighted")

        expected = (0.8 * 100 + 0.9 * 300) / 400
        assert agg.providers["fusion"].metrics["roc_auc"].mean == pytest.approx(expected)

    def test_zero_samples_fallback_weight(self) -> None:
        results = [_result("ds-a", roc=0.8, samples=0), _result("ds-b", roc=0.9, samples=100)]
        agg = aggregate_results(results, mode="weighted")

        assert agg.fallback_count == 1
        expected = (0.8 * 1.0 + 0.9 * 100) / 101
        assert agg.providers["fusion"].metrics["roc_auc"].mean == pytest.approx(expected)


class TestMicroAggregation:
    def test_micro_matches_weighted(self) -> None:
        results = [_result("ds-a", roc=0.8, samples=100), _result("ds-b", roc=0.9, samples=300)]
        micro = aggregate_results(results, mode="micro")

        expected = (0.8 * 100 + 0.9 * 300) / 400
        assert micro.providers["fusion"].metrics["roc_auc"].mean == pytest.approx(expected)


class TestProviderOrdering:
    def test_fusion_first_then_classical_then_quantum(self) -> None:
        results = [
            _result("ds-a", provider="qsvm", samples=100, roc=0.7),
            _result("ds-b", provider="fusion", samples=100, roc=0.8),
            _result("ds-c", provider="isolation-forest", samples=100, roc=0.9),
        ]
        agg = aggregate_results(results, mode="macro")

        assert agg.provider_ids == ["fusion", "isolation-forest", "qsvm"]


class TestErrorHandling:
    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            aggregate_results([], mode="banana")

    def test_empty_results_returns_empty_aggregation(self) -> None:
        agg = aggregate_results([], mode="macro")

        assert agg.providers == {}
        assert agg.datasets == []
