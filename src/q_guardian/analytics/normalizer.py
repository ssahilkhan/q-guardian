"""Normalize heterogeneous result artifacts onto a single canonical model.

Supported sources:

* ``BenchmarkReport.as_dict()`` and the standalone inner benchmark reports
  written by ``docs/output/evaluation/report.json`` (``benchmark`` source)
* ``EvaluationReport.as_dict()`` matrix rows (``evaluation`` source)
* ``reports/ml_baseline/baseline_metrics.json`` pools (``baseline`` source)

All three formats carry different provider structures, metric names and
distribution shapes. Normalization preserves the measured values and records
the originating format; it never synthesizes a distribution that was not
measured.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

from q_guardian.analytics.models import (
    SCOPE_EXTERNAL,
    SCOPE_INTERNAL,
    SCOPE_UNKNOWN,
    SOURCE_BASELINE,
    SOURCE_BENCHMARK,
    SOURCE_EVALUATION,
    MetricStats,
    NormalizedResult,
)

if TYPE_CHECKING:
    from q_guardian.benchmark.report import BenchmarkReport

ReportInput = Union["BenchmarkReport", dict[str, Any], Path, str]

_INTERNAL_POOLS = {"test", "validation", "internal"}
_EXTERNAL_POOLS = {"external_eval", "external_jbb", "external", "test:external"}

# evaluation matrix row metric -> canonical metric key.
_EVALUATION_METRIC_MAP = {
    "accuracy": "accuracy",
    "detection_rate": "recall",
    "benign_rejection_rate": "specificity",
    "fpr": "false_positive_rate",
    "fnr": "false_negative_rate",
    "f1": "f1_score",
    "roc_auc": "roc_auc",
    "pr_auc": "pr_auc",
}

# Bookkeeping fields embedded in some artifacts that are counts or settings
# rather than detection metrics; they are excluded from metric aggregation.
_BOOKKEEPING_KEYS = {
    "support",
    "threshold",
    "true_positives",
    "false_positives",
    "true_negatives",
    "false_negatives",
}


class NormalizationError(ValueError):
    """Raised when an artifact cannot be recognized and normalized."""


def normalize(report: ReportInput, *, origin_path: str = "<in-memory>") -> list[NormalizedResult]:
    """Normalize any supported artifact into one or more ``NormalizedResult``.

    Evaluation reports expand to one result per matrix row; baseline metric
    files expand to one result per pool; benchmark reports produce a single
    result.
    """
    if isinstance(report, (Path, str)):
        origin_path = str(report)
        report = _load_json(report)
    if isinstance(report, dict):
        return _normalize_dict(report, origin_path=origin_path)
    if hasattr(report, "as_dict"):
        return _normalize_dict(report.as_dict(), origin_path=origin_path)
    raise NormalizationError(f"Unsupported report type: {type(report).__name__}")


def _load_json(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise NormalizationError(f"Report file must contain a JSON object: {path}")
    return loaded


def _normalize_dict(report: dict[str, Any], *, origin_path: str) -> list[NormalizedResult]:
    kind = _detect_format(report)
    if kind == "benchmark":
        return [_from_benchmark(report, origin_path=origin_path)]
    if kind == "benchmark_inner":
        return [_from_benchmark_inner(report, origin_path=origin_path)]
    if kind == "evaluation":
        return _from_evaluation(report, origin_path=origin_path)
    if kind == "baseline":
        return _from_baseline(report, origin_path=origin_path)
    raise NormalizationError(
        "Unrecognized report shape; expected a benchmark, evaluation or baseline artifact"
    )


def _detect_format(report: dict[str, Any]) -> str:
    if isinstance(report.get("pools"), dict):
        return "baseline"
    if "matrix" in report and isinstance(report.get("matrix"), list) and "summary" in report:
        return "evaluation"
    benchmark = report.get("benchmark")
    if isinstance(benchmark, dict) and "cross_validation" in benchmark:
        # Outer envelope: {"dataset", "validation", "benchmark": {...}}
        return "benchmark"
    if "cross_validation" in report and "config" in report:
        # Standalone inner benchmark report.
        return "benchmark_inner"
    raise NormalizationError("Unrecognized report shape")


def _from_benchmark(report: dict[str, Any], *, origin_path: str) -> NormalizedResult:
    dataset = report["dataset"]
    benchmark = report["benchmark"]
    config = benchmark.get("config", {})
    dataset_stats = benchmark.get("dataset", {})
    cross_validation = benchmark.get("cross_validation", {})
    metrics = cross_validation.get("metrics", {})
    fold_count = cross_validation.get("fold_count")
    seed = config.get("seed")
    threshold = config.get("threshold")
    evaluator = config.get("evaluator", {})
    samples = int(dataset_stats.get("total", 0))
    malicious = int(dataset_stats.get("threats", 0))
    benign = int(dataset_stats.get("benign", 0))
    return NormalizedResult(
        dataset_id=str(dataset["id"]),
        name=str(dataset.get("name", dataset["id"])),
        source=SOURCE_BENCHMARK,
        scope=SCOPE_UNKNOWN,
        samples=samples,
        malicious=malicious,
        benign=benign,
        license=str(dataset.get("license", "")),
        homepage=str(dataset.get("homepage", "")),
        fold_count=_optional_int(fold_count),
        seed=_optional_int(seed),
        threshold=_optional_float(threshold),
        evaluator=_as_dict(evaluator),
        metrics=_metrics_map(metrics),
        origin_path=origin_path,
    )


def _from_benchmark_inner(report: dict[str, Any], *, origin_path: str) -> NormalizedResult:
    config = report.get("config", {})
    cross_validation = report.get("cross_validation", {})
    metrics = cross_validation.get("metrics", {})
    dataset_id = str(config.get("dataset", "unknown"))
    seed = config.get("seed")
    threshold = config.get("threshold")
    evaluator = config.get("evaluator", {})
    return NormalizedResult(
        dataset_id=dataset_id,
        name=dataset_id,
        source=SOURCE_BENCHMARK,
        scope=SCOPE_UNKNOWN,
        samples=_optional_int(config.get("samples")) or 0,
        fold_count=_optional_int(cross_validation.get("fold_count") or cross_validation.get("k")),
        seed=_optional_int(seed),
        threshold=_optional_float(threshold),
        evaluator=_as_dict(evaluator),
        metrics=_metrics_map(metrics),
        origin_path=origin_path,
    )


def _from_evaluation(report: dict[str, Any], *, origin_path: str) -> list[NormalizedResult]:
    config = report.get("config", {})
    matrix = report.get("matrix", [])
    threshold = (
        config.get("eval", {}).get("threshold")
        if isinstance(config.get("eval"), dict)
        else config.get("threshold")
    )
    evaluator_model = config.get("model", {})
    results: list[NormalizedResult] = []
    for row in matrix:
        if not isinstance(row, dict):
            continue
        if row.get("samples", 0) <= 0 and row.get("available", True) is False:
            continue
        if row.get("samples", 0) <= 0:
            continue
        pool = str(row.get("pool", ""))
        scope = _scope_for_pool(pool)
        metrics = _scalar_metrics(row)
        if not metrics:
            continue
        results.append(
            NormalizedResult(
                dataset_id=str(row.get("dataset", pool or "unknown")),
                name=str(row.get("dataset", pool or "unknown")),
                source=SOURCE_EVALUATION,
                scope=scope,
                pool=pool,
                samples=int(row.get("samples", 0)),
                malicious=int(row.get("malicious", 0)),
                benign=int(row.get("benign", 0)),
                available=bool(row.get("available", True)),
                note=str(row.get("note", "")),
                threshold=_optional_float(threshold),
                evaluator=_as_dict(evaluator_model) if isinstance(evaluator_model, dict) else {},
                metrics=metrics,
                origin_path=origin_path,
            )
        )
    return results


def _from_baseline(report: dict[str, Any], *, origin_path: str) -> list[NormalizedResult]:
    pools = report.get("pools", {})
    default_threshold = report.get("default_threshold")
    feature_schema = report.get("feature_schema")
    trust: list[NormalizedResult] = []
    for pool_name, pool in pools.items():
        if not isinstance(pool, dict):
            continue
        metrics_at_default = pool.get("metrics_at_default", {})
        if not isinstance(metrics_at_default, dict) or not metrics_at_default:
            continue
        pool = _as_dict(pool)
        evaluator: dict[str, Any] = {}
        if isinstance(feature_schema, dict):
            evaluator["feature_schema"] = feature_schema
        evaluator["default_threshold"] = default_threshold
        trust.append(
            NormalizedResult(
                dataset_id=str(pool_name),
                name=str(pool_name),
                source=SOURCE_BASELINE,
                scope=_scope_for_pool(str(pool_name)),
                pool=str(pool_name),
                samples=int(pool.get("samples", 0)),
                malicious=int(pool.get("malicious", 0)),
                benign=int(pool.get("benign", 0)),
                threshold=_optional_float(default_threshold),
                evaluator=evaluator,
                metrics=_metrics_map(metrics_at_default),
                origin_path=origin_path,
            )
        )
    return trust


def _metrics_map(
    source: dict[str, Any],
) -> dict[str, dict[str, MetricStats]]:
    mapped: dict[str, dict[str, MetricStats]] = {}
    for provider, provider_metrics in source.items():
        if not isinstance(provider_metrics, dict):
            continue
        stats: dict[str, MetricStats] = {}
        for metric, value in provider_metrics.items():
            if metric in _BOOKKEEPING_KEYS:
                continue
            if isinstance(value, dict) and "mean" in value:
                stats[metric] = MetricStats(
                    mean=float(value["mean"]),
                    std=_optional_float(value.get("std")),
                    min=_optional_float(value.get("min")),
                    max=_optional_float(value.get("max")),
                )
            elif _is_real(value):
                stats[metric] = MetricStats.from_scalar(float(value))
        if stats:
            mapped[str(provider)] = stats
    return mapped


def _scalar_metrics(row: dict[str, Any]) -> dict[str, dict[str, MetricStats]]:
    stats: dict[str, MetricStats] = {}
    for row_key, metric in _EVALUATION_METRIC_MAP.items():
        value = row.get(row_key)
        if value is None or not _is_real(value):
            continue
        stats[metric] = MetricStats.from_scalar(float(value))
    if not stats:
        return {}
    return {"fusion": stats}


def _scope_for_pool(pool: str) -> str:
    normalized = pool.lower()
    if normalized in _INTERNAL_POOLS or normalized.startswith("test:"):
        return SCOPE_INTERNAL
    if normalized in _EXTERNAL_POOLS:
        return SCOPE_EXTERNAL
    return SCOPE_UNKNOWN


def _is_real(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
