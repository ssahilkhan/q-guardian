"""Tests for BenchmarkMetrics and ResearchMetrics."""

from __future__ import annotations

from q_guardian.ml.evaluation.metrics import BenchmarkMetrics, ResearchMetrics


class TestBenchmarkMetrics:
    def setup_method(self) -> None:
        self.metrics = BenchmarkMetrics()

    def test_perfect_classification(self) -> None:
        y_true = [0, 1, 0, 1, 1]
        y_pred = [0, 1, 0, 1, 1]
        result = self.metrics.compute_classification_metrics(y_true, y_pred)
        assert result.accuracy == 1.0
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1_score == 1.0

    def test_imperfect_classification(self) -> None:
        y_true = [0, 1, 1, 0, 1]
        y_pred = [0, 1, 0, 0, 1]
        result = self.metrics.compute_classification_metrics(y_true, y_pred)
        assert 0.0 < result.accuracy <= 1.0
        assert result.true_positives == 2
        assert result.false_negatives == 1

    def test_empty(self) -> None:
        result = self.metrics.compute_classification_metrics([], [])
        assert result.accuracy == 0.0

    def test_confusion_matrix(self) -> None:
        y_true = [0, 0, 1, 1]
        y_pred = [0, 1, 1, 0]
        result = self.metrics.compute_classification_metrics(y_true, y_pred)
        assert len(result.confusion_matrix) > 0

    def test_per_class_metrics(self) -> None:
        y_true = [0, 1, 0, 1, 2, 2]
        y_pred = [0, 1, 1, 1, 2, 0]
        result = self.metrics.compute_classification_metrics(
            y_true, y_pred, class_names=["benign", "injection", "jailbreak"]
        )
        assert "benign" in result.per_class_metrics
        assert "injection" in result.per_class_metrics

    def test_anomaly_metrics(self) -> None:
        y_true = [True, False, True, False, True]
        y_pred = [True, False, False, False, True]
        result = self.metrics.compute_anomaly_metrics(y_true, y_pred)
        assert "detection_rate" in result
        assert "false_positive_rate" in result
        assert result["accuracy"] > 0.0

    def test_anomaly_empty(self) -> None:
        result = self.metrics.compute_anomaly_metrics([], [])
        assert result == {}


class TestResearchMetrics:
    def setup_method(self) -> None:
        self.metrics = ResearchMetrics()

    def test_prompt_security_metrics(self) -> None:
        y_true = ["benign", "injection", "benign", "jailbreak"]
        y_pred = ["benign", "injection", "injection", "jailbreak"]
        result = self.metrics.compute_prompt_security_metrics(y_true, y_pred)
        assert "accuracy" in result
        assert "f1_score" in result

    def test_severity_weighted(self) -> None:
        y_true = ["benign", "injection"]
        y_pred = ["benign", "injection"]
        severity = ["low", "critical"]
        result = self.metrics.compute_prompt_security_metrics(
            y_true, y_pred, y_true_severity=severity, y_pred_severity=severity
        )
        assert "severity_weighted_accuracy" in result
        assert result["severity_weighted_accuracy"] == 1.0
