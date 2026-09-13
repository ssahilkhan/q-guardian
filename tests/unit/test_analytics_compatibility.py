"""Unit tests for cross-dataset compatibility validation."""

from __future__ import annotations

from q_guardian.analytics.compatibility import validate
from q_guardian.analytics.models import MetricStats, NormalizedResult


def _result(
    dataset_id: str,
    *,
    roc: float = 0.8,
    fold_count: int | None = None,
    threshold: float | None = None,
    source: str = "benchmark",
    scope: str = "unknown",
    origin_path: str = "<in-memory>",
    non_finite: bool = False,
) -> NormalizedResult:
    value = float("nan") if non_finite else roc
    return NormalizedResult(
        dataset_id=dataset_id,
        name=dataset_id,
        source=source,
        scope=scope,
        fold_count=fold_count,
        threshold=threshold,
        metrics={"fusion": {"roc_auc": MetricStats.from_scalar(value)}},
        origin_path=origin_path,
    )


class TestCompatibility:
    def test_empty_collection_is_error(self) -> None:
        report = validate([])

        assert report.compatible is False
        assert report.errors == ["No results were provided"]

    def test_duplicate_dataset_ids_are_errors(self) -> None:
        results = [
            _result("ds-a", origin_path="one.json"),
            _result("ds-a", origin_path="two.json"),
        ]

        report = validate(results)
        assert report.compatible is False
        assert any("duplicate dataset id 'ds-a'" in error for error in report.errors)

    def test_non_finite_values_are_errors(self) -> None:
        results = [_result("ds-a"), _result("ds-b", non_finite=True)]

        report = validate(results)
        assert report.compatible is False
        assert any("non-finite metric values" in error for error in report.errors)

    def test_different_thresholds_warn(self) -> None:
        results = [_result("ds-a", threshold=0.5), _result("ds-b", threshold=0.6)]

        report = validate(results)
        assert report.compatible is True
        assert any("decision thresholds" in warning for warning in report.warnings)

    def test_different_fold_counts_warn(self) -> None:
        results = [_result("ds-a", fold_count=3), _result("ds-b", fold_count=5)]

        report = validate(results)
        assert report.compatible is True
        assert any("fold counts" in warning for warning in report.warnings)

    def test_mixed_sources_warn(self) -> None:
        results = [_result("ds-a", source="benchmark"), _result("ds-b", source="baseline")]

        report = validate(results)
        assert report.compatible is True
        assert any("mix measurement protocols" in warning for warning in report.warnings)

    def test_no_external_pool_warns(self) -> None:
        results = [_result("ds-a", scope="internal"), _result("ds-b", scope="internal")]

        report = validate(results)
        assert any("no external datasets" in warning for warning in report.warnings)

    def test_details_record_scope_coverage(self) -> None:
        results = [
            _result("ds-a", scope="internal"),
            _result("ds-b", scope="external"),
        ]

        report = validate(results)
        assert report.details["scope_coverage"]["internal"]["count"] == 1
        assert report.details["scope_coverage"]["external"]["count"] == 1
        assert report.details["internal_datasets"] == 1
        assert report.details["external_datasets"] == 1

    def test_evaluator_contract_difference_warns(self) -> None:
        def _with_evaluator(dataset_id: str, quantum: bool) -> NormalizedResult:
            result = _result(dataset_id)
            result.evaluator = {"quantum": quantum}
            return result

        report = validate([_with_evaluator("ds-a", True), _with_evaluator("ds-b", False)])

        assert len(report.warnings) >= 1
        assert any("'quantum' differs" in warning for warning in report.warnings)

    def test_clean_collection_has_no_warnings_or_errors(self) -> None:
        report = validate([_result("ds-a"), _result("ds-b", scope="external")])

        assert report.compatible is True
        assert not report.errors
        assert not report.warnings
