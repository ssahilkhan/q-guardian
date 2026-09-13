"""Unit tests for the result artifact normalizer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from q_guardian.analytics.models import (
    SCOPE_EXTERNAL,
    SCOPE_INTERNAL,
    SCOPE_UNKNOWN,
    SOURCE_BASELINE,
    SOURCE_BENCHMARK,
    SOURCE_EVALUATION,
)
from q_guardian.analytics.normalizer import NormalizationError, normalize


def _benchmark(
    dataset_id: str = "ds-a",
    *,
    roc: float = 0.85,
    qsvm_roc: float = 0.88,
    fold_count: int = 3,
    threshold: float = 0.5,
    samples: int = 120,
) -> dict:
    metrics = {
        "fusion": {
            "roc_auc": {"mean": roc, "std": 0.05, "min": 0.8, "max": 0.9},
            "f1_score": {"mean": 0.62},
        },
        "isolation-forest": {"roc_auc": {"mean": 0.7}, "f1_score": {"mean": 0.4}},
        "qsvm": {"roc_auc": {"mean": qsvm_roc}, "f1_score": {"mean": 0.6}},
    }
    return {
        "dataset": {
            "id": dataset_id,
            "name": dataset_id,
            "license": "MIT",
            "homepage": "https://example.com",
        },
        "validation": "ok",
        "benchmark": {
            "config": {
                "seed": 7,
                "threshold": threshold,
                "evaluator": {"type": "linear", "quantum": False},
            },
            "dataset": {"total": samples, "threats": 40, "benign": 80},
            "cross_validation": {"fold_count": fold_count, "metrics": metrics},
        },
    }


def _benchmark_inner(dataset_id: str = "ds-x", *, roc: float = 0.8, fold_count: int = 5) -> dict:
    return {
        "config": {"dataset": dataset_id, "seed": 3, "samples": 200, "threshold": 0.5},
        "cross_validation": {
            "fold_count": fold_count,
            "metrics": {"fusion": {"roc_auc": {"mean": roc, "std": 0.02}}},
        },
    }


def _evaluation_row(
    *,
    dataset: str = "builtin",
    pool: str = "test",
    samples: int = 100,
    benign: int = 50,
    malicious: int = 50,
    available: bool = True,
) -> dict:
    return {
        "dataset": dataset,
        "pool": pool,
        "samples": samples,
        "benign": benign,
        "malicious": malicious,
        "detection_rate": 0.9,
        "benign_rejection_rate": 0.8,
        "fpr": 0.1,
        "fnr": 0.2,
        "f1": 0.84,
        "accuracy": 0.88,
        "roc_auc": 0.93,
        "pr_auc": 0.9,
        "available": available,
    }


class TestBenchmarkFormat:
    def test_outer_envelope_maps_metadata(self) -> None:
        (result,) = normalize(_benchmark())

        assert result.dataset_id == "ds-a"
        assert result.name == "ds-a"
        assert result.source == SOURCE_BENCHMARK
        assert result.scope == SCOPE_UNKNOWN
        assert result.samples == 120
        assert result.fold_count == 3
        assert result.threshold == 0.5
        assert result.seed == 7
        assert result.evaluator == {"type": "linear", "quantum": False}
        assert result.license == "MIT"
        assert result.homepage == "https://example.com"

    def test_outer_envelope_preserves_distribution(self) -> None:
        (result,) = normalize(_benchmark())
        roc = result.provider_metric("fusion", "roc_auc")

        assert roc is not None
        assert roc.mean == pytest.approx(0.85)
        assert roc.std == pytest.approx(0.05)
        assert roc.min == pytest.approx(0.8)
        assert roc.max == pytest.approx(0.9)

    def test_scalar_metrics_have_no_synthesized_std(self) -> None:
        (result,) = normalize(_benchmark())
        f1 = result.provider_metric("fusion", "f1_score")

        assert f1 is not None
        assert f1.mean == pytest.approx(0.62)
        assert f1.std is None
        assert f1.min is None
        assert f1.max is None

    def test_providers_in_insertion_order(self) -> None:
        (result,) = normalize(_benchmark())

        assert result.providers == ["fusion", "isolation-forest", "qsvm"]

    def test_inner_benchmark_maps_config_dataset(self) -> None:
        (result,) = normalize(_benchmark_inner())

        assert result.dataset_id == "ds-x"
        assert result.source == SOURCE_BENCHMARK
        assert result.samples == 200
        assert result.fold_count == 5
        assert result.threshold == 0.5
        assert result.provider_metric("fusion", "roc_auc").mean == pytest.approx(0.8)


class TestEvaluationFormat:
    def test_rows_expand_with_metric_renaming(self) -> None:
        report = {
            "config": {"eval": {"threshold": 0.5}, "model": {"type": "fusion"}},
            "matrix": [_evaluation_row()],
            "summary": {},
        }
        (result,) = normalize(report)

        assert result.source == SOURCE_EVALUATION
        assert result.scope == SCOPE_INTERNAL
        assert result.pool == "test"
        assert result.samples == 100
        assert result.threshold == 0.5
        assert result.provider_metric("fusion", "recall").mean == pytest.approx(0.9)
        assert result.provider_metric("fusion", "specificity").mean == pytest.approx(0.8)
        assert result.provider_metric("fusion", "false_positive_rate").mean == pytest.approx(0.1)
        assert result.provider_metric("fusion", "false_negative_rate").mean == pytest.approx(0.2)
        assert result.provider_metric("fusion", "f1_score").mean == pytest.approx(0.84)
        assert result.provider_metric("fusion", "accuracy").mean == pytest.approx(0.88)
        assert result.provider_metric("fusion", "roc_auc").mean == pytest.approx(0.93)
        assert result.provider_metric("fusion", "pr_auc").mean == pytest.approx(0.9)

    def test_missing_metrics_render_as_none(self) -> None:
        row = _evaluation_row()
        row.pop("detection_rate")
        report = {
            "config": {"eval": {"threshold": 0.5}},
            "matrix": [row],
            "summary": {},
        }
        (result,) = normalize(report)

        assert result.provider_metric("fusion", "recall") is None
        assert result.provider_metric("fusion", "accuracy").mean == pytest.approx(0.88)

    def test_external_pool_scoped_external(self) -> None:
        report = {
            "config": {},
            "matrix": [_evaluation_row(dataset="jbb", pool="external_jbb")],
            "summary": {},
        }
        (result,) = normalize(report)

        assert result.scope == SCOPE_EXTERNAL

    def test_empty_and_unavailable_rows_skipped(self) -> None:
        unavailable = _evaluation_row(dataset="uni-a", samples=0, available=False)
        empty = _evaluation_row(dataset="uni-b", samples=0)
        report = {
            "config": {},
            "matrix": [
                unavailable,
                empty,
                _evaluation_row(dataset="uni-c", samples=10),
            ],
            "summary": {},
        }

        results = normalize(report)
        assert [result.dataset_id for result in results] == ["uni-c"]


class TestBaselineFormat:
    def _baseline(self) -> dict:
        return {
            "default_threshold": 0.5,
            "feature_schema": {"handcrafted_dims": 4, "quantum_dims": 2, "total_dims": 6},
            "pools": {
                "validation": {
                    "samples": 110,
                    "benign": 100,
                    "malicious": 10,
                    "metrics_at_default": {
                        "fusion": {"accuracy": 0.8, "threshold": 0.5, "support": 110},
                        "isolation-forest": {"accuracy": 0.7},
                        "qsvm": {"accuracy": 0.9},
                    },
                },
                "external_jbb": {
                    "samples": 200,
                    "benign": 180,
                    "malicious": 20,
                    "metrics_at_default": {"fusion": {"accuracy": 0.5}},
                },
            },
        }

    def test_pools_expand_with_scopes(self) -> None:
        results = normalize(self._baseline())

        by_pool = {result.dataset_id: result for result in results}
        assert list(by_pool) == ["validation", "external_jbb"]
        assert by_pool["validation"].scope == SCOPE_INTERNAL
        assert by_pool["external_jbb"].scope == SCOPE_EXTERNAL
        assert by_pool["validation"].source == SOURCE_BASELINE
        assert by_pool["validation"].threshold == 0.5

    def test_bookkeeping_keys_excluded(self) -> None:
        (result,) = [r for r in normalize(self._baseline()) if r.dataset_id == "validation"]

        fusion_metrics = result.metrics["fusion"]
        assert set(fusion_metrics) == {"accuracy"}
        assert result.provider_metric("fusion", "threshold") is None
        assert result.provider_metric("fusion", "support") is None
        assert fusion_metrics["accuracy"].mean == pytest.approx(0.8)


class TestLoading:
    def test_from_json_file_sets_origin_path(self, tmp_path) -> None:
        path: Path = tmp_path / "source.json"
        path.write_text(json.dumps(_benchmark()), encoding="utf-8")

        (result,) = normalize(path)
        assert result.origin_path == str(path)

    def test_load_json_requires_object(self, tmp_path) -> None:
        path: Path = tmp_path / "array.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(NormalizationError):
            normalize(path)

    def test_unrecognized_shape_raises(self) -> None:
        with pytest.raises(NormalizationError):
            normalize({"something": "else"})

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(NormalizationError):
            normalize(123)  # type: ignore[arg-type]
