"""Compatibility validation across datasets before aggregation.

Cross-dataset averages are only meaningful when the underlying experiments
are comparable. This module checks for hard inconsistencies (duplicate dataset
ids, empty result sets, non-finite values) and softer divergences (different
fold counts, thresholds, evaluator feature contracts, mixed measurement
protocols) and reports them so nothing is silently averaged together.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from q_guardian.analytics.models import NormalizedResult

_PROTOCOL_KEYS = ("quantum", "quantum_shots", "quantum_feature_count")
_FEATURE_KEYS = (
    "quantum_feature_count",
    "n_estimators",
    "contamination",
    "feature_schema",
)


@dataclass
class CompatibilityReport:
    """Outcome of validating a collection of normalized results."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def compatible(self) -> bool:
        """True when no hard errors were found (warnings are non-fatal)."""
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
        }


def validate(results: list[NormalizedResult]) -> CompatibilityReport:
    """Validate a collection of normalized results for safe aggregation."""
    if not results:
        return CompatibilityReport(errors=["No results were provided"])

    report = CompatibilityReport()
    _check_duplicates(results, report)
    _check_protocols(results, report)
    _check_mixed_sources(results, report)
    _check_non_finite(results, report)
    _check_pool_coverage(results, report)
    report.details["datasets"] = [r.dataset_id for r in results]
    report.details["sources"] = _count_sources(results)
    return report


def _check_duplicates(results: list[NormalizedResult], report: CompatibilityReport) -> None:
    seen: dict[str, list[str]] = {}
    for result in results:
        seen.setdefault(result.dataset_id, []).append(result.origin_path)
    for dataset_id, origins in seen.items():
        if len(origins) > 1:
            report.errors.append(
                f"duplicate dataset id '{dataset_id}' in {len(origins)} artifacts "
                f"({', '.join(origins)})"
            )


def _check_protocols(results: list[NormalizedResult], report: CompatibilityReport) -> None:
    fold_counts: set[int] = set()
    thresholds: set[float] = set()
    for result in results:
        if result.fold_count is not None:
            fold_counts.add(result.fold_count)
        if result.threshold is not None:
            thresholds.add(result.threshold)
    if len(fold_counts) > 1:
        report.warnings.append(
            f"results were produced with different fold counts: {sorted(fold_counts)}"
        )

    if len(thresholds) > 1:
        report.warnings.append(
            "results use different decision thresholds: "
            + ", ".join(f"{value:.4f}" for value in sorted(thresholds))
        )

    evaluators = [result.evaluator for result in results if result.evaluator]
    if len(evaluators) > 1:
        _check_evaluator_contracts(evaluators, report)


def _check_evaluator_contracts(
    evaluators: list[dict[str, Any]], report: CompatibilityReport
) -> None:
    protocol_values: dict[str, set[str]] = {key: set() for key in _PROTOCOL_KEYS}
    feature_values: dict[str, set[str]] = {key: set() for key in _FEATURE_KEYS}
    for evaluator in evaluators:
        for key in _PROTOCOL_KEYS:
            if key in evaluator:
                protocol_values[key].add(_json_safe(evaluator[key]))
        for key in _FEATURE_KEYS:
            value = evaluator.get(key)
            if isinstance(value, dict):
                # feature_schema collapses to a size summary for comparison.
                dims = value.get("total_dims") or value.get("handcrafted_dims")
                if dims is not None:
                    feature_values[key].add(_json_safe(dims))
            elif value is not None:
                feature_values[key].add(_json_safe(value))
    for key, values in protocol_values.items():
        if len(values) > 1:
            report.warnings.append(f"evaluator '{key}' differs across results: {sorted(values)}")
    for key, values in feature_values.items():
        if key == "feature_schema" and len(values) > 1:
            report.warnings.append(
                f"feature contract differs across results: dims {sorted(values)}"
            )


def _check_mixed_sources(results: list[NormalizedResult], report: CompatibilityReport) -> None:
    sources = {result.source for result in results}
    if len(sources) > 1:
        report.warnings.append(
            "results mix measurement protocols: "
            + ", ".join(sorted(sources))
            + " (benchmark = CV fold aggregates, evaluation = single-pass "
            "fusion matrix, baseline = single-pass per-provider scalars)"
        )


def _check_non_finite(results: list[NormalizedResult], report: CompatibilityReport) -> None:
    offenders: list[str] = []
    for result in results:
        for provider, provider_metrics in result.metrics.items():
            for metric, stats in provider_metrics.items():
                values = [v for v in (stats.mean, stats.std, stats.min, stats.max) if v is not None]
                if any(math.isnan(value) or math.isinf(value) for value in values):
                    offenders.append(f"{result.dataset_id}/{provider}/{metric}")
    if offenders:
        report.errors.append(f"non-finite metric values in: {', '.join(sorted(set(offenders)))}")


def _check_pool_coverage(results: list[NormalizedResult], report: CompatibilityReport) -> None:
    by_scope: dict[str, list[str]] = {}
    for result in results:
        scope = result.scope if result.scope is not None else "unknown"
        by_scope.setdefault(scope, []).append(result.dataset_id)
    counts = {scope: len(ids) for scope, ids in by_scope.items()}
    report.details["scope_coverage"] = {
        scope: {
            "datasets": ids,
            "count": len(ids),
        }
        for scope, ids in by_scope.items()
    }
    ids = counts.get("internal", 0)
    if ids:
        report.details["internal_datasets"] = counts["internal"]
        report.details["external_datasets"] = counts.get("external", 0)
    if "external" not in by_scope:
        report.warnings.append(
            "no external datasets in the collection; generalization analysis is not possible"
        )


def _count_sources(results: list[NormalizedResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.source] = counts.get(result.source, 0) + 1
    return dict(sorted(counts.items()))


def _json_safe(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return str(value)
