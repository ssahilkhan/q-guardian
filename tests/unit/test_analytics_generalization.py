"""Unit tests for internal vs external generalization analysis."""

from __future__ import annotations

import pytest

from q_guardian.analytics.generalization import analyze_generalization
from q_guardian.analytics.models import (
    SCOPE_EXTERNAL,
    SCOPE_INTERNAL,
    MetricStats,
    NormalizedResult,
)


def _result(
    dataset_id: str,
    *,
    scope: str,
    samples: int = 100,
    f1: float = 0.8,
    roc_auc: float = 0.9,
    accuracy: float = 0.7,
    provider: str = "fusion",
) -> NormalizedResult:
    metrics: dict[str, MetricStats] = {
        "f1_score": MetricStats.from_scalar(f1),
        "roc_auc": MetricStats.from_scalar(roc_auc),
        "accuracy": MetricStats.from_scalar(accuracy),
    }
    return NormalizedResult(
        dataset_id=dataset_id,
        name=dataset_id,
        source="benchmark",
        scope=scope,
        samples=samples,
        metrics={provider: metrics},
    )


class TestGeneralization:
    def test_gap_computed_with_single_external_note(self) -> None:
        results = [
            _result("ds-a", scope=SCOPE_INTERNAL, f1=0.7),
            _result("ds-b", scope=SCOPE_INTERNAL, f1=0.6),
            _result("ds-c", scope=SCOPE_EXTERNAL, f1=0.3, samples=200),
        ]

        report = analyze_generalization(results)
        assert report.gaps
        f1_gap = next(gap for gap in report.gaps if gap.metric == "f1_score")
        assert f1_gap.external_mean == pytest.approx(0.3)
        assert f1_gap.internal_mean == pytest.approx(0.65)
        assert f1_gap.note == "single external dataset; gap is not conclusive evidence of a trend"
        assert "single external dataset" in report.conclusion

    def test_gap_conclusion_with_two_external_datasets(self) -> None:
        results = [
            _result("ds-a", scope=SCOPE_INTERNAL, f1=0.8),
            _result("ds-b", scope=SCOPE_EXTERNAL, f1=0.3, samples=200),
            _result("ds-c", scope=SCOPE_EXTERNAL, f1=0.4, samples=200),
        ]

        report = analyze_generalization(results)
        f1_gap = next(gap for gap in report.gaps if gap.metric == "f1_score")
        assert f1_gap.external_mean == pytest.approx(0.35)
        assert f1_gap.note == ""
        assert "single external dataset" not in report.conclusion

    def test_external_summary_has_min_max(self) -> None:
        results = [
            _result("ds-a", scope=SCOPE_INTERNAL, f1=0.8, roc_auc=0.9),
            _result("ds-b", scope=SCOPE_EXTERNAL, f1=0.3, roc_auc=0.6, samples=200),
            _result("ds-c", scope=SCOPE_EXTERNAL, f1=0.4, roc_auc=0.7, samples=200),
        ]

        report = analyze_generalization(results)
        f1_summary = report.external_summary["f1_score"]
        assert f1_summary["min"] == pytest.approx(0.3)
        assert f1_summary["max"] == pytest.approx(0.4)
        assert f1_summary["datasets"] == 2
        assert f1_summary["std"] is not None

    def test_no_internal_returns_honest_message(self) -> None:
        results = [_result("ds-a", scope=SCOPE_EXTERNAL)]

        report = analyze_generalization(results)
        assert "No internal (hold-out)" in report.conclusion
        assert not report.gaps

    def test_no_external_returns_honest_message(self) -> None:
        results = [_result("ds-a", scope=SCOPE_INTERNAL)]

        report = analyze_generalization(results)
        assert "No external dataset" in report.conclusion
        assert not report.gaps

    def test_no_overlapping_metrics_returns_message(self) -> None:
        internal = NormalizedResult(
            dataset_id="ds-a",
            name="ds-a",
            source="benchmark",
            scope=SCOPE_INTERNAL,
            metrics={"fusion": {"mcc": MetricStats.from_scalar(0.5)}},
        )
        external = NormalizedResult(
            dataset_id="ds-b",
            name="ds-b",
            source="benchmark",
            scope=SCOPE_EXTERNAL,
            samples=100,
            metrics={"fusion": {"mcc": MetricStats.from_scalar(0.4)}},
        )

        report = analyze_generalization([internal, external])
        assert "No overlapping metrics" in report.conclusion
