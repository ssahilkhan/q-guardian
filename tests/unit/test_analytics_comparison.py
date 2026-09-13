"""Unit tests for classical vs quantum comparison."""

from __future__ import annotations

from q_guardian.analytics.comparison import compare_classical_quantum
from q_guardian.analytics.models import MetricStats, NormalizedResult


def _result(
    dataset_id: str,
    *,
    cls_metrics: dict[str, MetricStats] | None = None,
    quantum_metrics: dict[str, MetricStats] | None = None,
    source: str = "benchmark",
) -> NormalizedResult:
    metrics: dict[str, dict[str, MetricStats]] = {}
    if cls_metrics:
        metrics["isolation-forest"] = cls_metrics
    if quantum_metrics:
        metrics["qsvm"] = quantum_metrics
    return NormalizedResult(
        dataset_id=dataset_id,
        name=dataset_id,
        source=source,
        samples=100,
        metrics=metrics,
    )


class TestComparison:
    def test_no_quantum_provider_reports_not_possible(self) -> None:
        results = [
            _result("ds-a", cls_metrics={"roc_auc": MetricStats.from_scalar(0.8)}),
        ]

        report = compare_classical_quantum(results)
        assert not report.deltas
        assert "No quantum provider results present; comparison not possible." in report.conclusions

    def test_single_dataset_does_not_claim_advantage(self) -> None:
        results = [
            _result(
                "ds-a",
                cls_metrics={"roc_auc": MetricStats(mean=0.9, std=0.05)},
                quantum_metrics={"roc_auc": MetricStats(mean=0.5, std=0.05)},
            ),
        ]

        report = compare_classical_quantum(results)
        assert any("single-dataset evidence only" in d.conclusion for d in report.deltas.values())

    def test_beyond_combined_uncertainty_classical_advantage(self) -> None:
        results = [
            _result(
                "ds-a",
                cls_metrics={"roc_auc": MetricStats(mean=0.85, std=0.02)},
                quantum_metrics={"roc_auc": MetricStats(mean=0.5, std=0.02)},
            ),
            _result(
                "ds-b",
                cls_metrics={"roc_auc": MetricStats(mean=0.80, std=0.02)},
                quantum_metrics={"roc_auc": MetricStats(mean=0.5, std=0.02)},
            ),
        ]

        report = compare_classical_quantum(results)
        delta = report.deltas["roc_auc"]
        assert "classical roc_auc exceeds quantum beyond combined uncertainty" in delta.conclusion
        assert any(
            "Differences beyond combined uncertainty were observed" in conclusion
            for conclusion in report.conclusions
        )

    def test_within_uncertainty_no_clear_advantage(self) -> None:
        results = [
            _result(
                "ds-a",
                cls_metrics={"roc_auc": MetricStats(mean=0.70, std=0.1)},
                quantum_metrics={"roc_auc": MetricStats(mean=0.68, std=0.1)},
            ),
            _result(
                "ds-b",
                cls_metrics={"roc_auc": MetricStats(mean=0.66, std=0.1)},
                quantum_metrics={"roc_auc": MetricStats(mean=0.68, std=0.1)},
            ),
        ]

        report = compare_classical_quantum(results)
        conclusions = {d.conclusion for d in report.deltas.values()}
        assert any("within cross-dataset uncertainty" in c for c in conclusions)

    def test_summary_datasets_collected_correctly(self) -> None:
        results = [
            _result("ds-a", cls_metrics={"roc_auc": MetricStats.from_scalar(0.8)}),
            _result("ds-b", cls_metrics={"roc_auc": MetricStats.from_scalar(0.8)}),
        ]

        report = compare_classical_quantum(results)
        assert report.classes["classical"].datasets == ["ds-a", "ds-b"]
        assert report.classes["quantum"].providers == []

    def test_conclusion_when_no_classical(self) -> None:
        results = [_result("ds-a", quantum_metrics={"roc_auc": MetricStats.from_scalar(0.8)})]

        report = compare_classical_quantum(results)
        assert "No classical providers present; comparison not possible." in report.conclusions
