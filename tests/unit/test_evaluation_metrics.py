"""Unit tests for the probability-based detection metrics."""

from __future__ import annotations

import pytest

from q_guardian.evaluation.metrics import (
    DetectionMetrics,
    brier_score,
    detection_metrics,
    expected_calibration_error,
    pr_auc,
    roc_auc,
)


class TestRocAuc:
    def test_perfect_separation(self):
        assert roc_auc([1, 1, 1, 0, 0, 0], [0.9, 0.7, 0.5, 0.4, 0.2, 0.1]) == pytest.approx(1.0)

    def test_inverted_perfect_separation(self):
        assert roc_auc([1, 1, 1, 0, 0, 0], [0.1, 0.2, 0.3, 0.8, 0.9, 1.0]) == pytest.approx(0.0)

    def test_half_separation(self):
        y = [1, 0, 1, 0]
        s = [0.8, 0.3, 0.6, 0.4]
        assert roc_auc(y, s) == pytest.approx(1.0)

    def test_random_ordering(self):
        y = [1, 1, 0, 0]
        s = [0.6, 0.3, 0.5, 0.2]
        # pos scores 0.6, 0.3; neg 0.5, 0.2
        # 0.6 > both neg (2); 0.3 > 0.2 (1) = 3/4
        assert roc_auc(y, s) == pytest.approx(0.75)

    def test_single_class(self):
        assert roc_auc([1, 1, 1], [0.9, 0.5, 0.1]) == pytest.approx(0.5)
        assert roc_auc([0, 0, 0], [0.9, 0.5, 0.1]) == pytest.approx(0.5)

    def test_empty(self):
        assert roc_auc([], []) == 0.5

    def test_ties(self):
        # scores with ties: 0.8, 0.7, 0.7, 0.3, 0.2, 0.1
        y = [1, 1, 0, 0, 0, 0]
        s = [0.8, 0.7, 0.7, 0.3, 0.2, 0.1]
        # pos 0.8 beats 4 neg; 0.7 ties neg 0.7 (0.5) and beats 3 → 3.5
        assert roc_auc(y, s) == pytest.approx((4 + 3.5) / 8.0)


class TestPrAuc:
    def test_perfect(self):
        assert pr_auc([1, 1, 1, 0], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)

    def test_all_positive(self):
        assert pr_auc([1, 1, 1], [0.9, 0.5, 0.1]) == pytest.approx(1.0)

    def test_all_negative(self):
        assert pr_auc([0, 0, 0], [0.9, 0.5, 0.1]) == pytest.approx(1.0)

    def test_empty(self):
        assert pr_auc([], []) == 0.0


class TestCalibration:
    def test_ece_perfect(self):
        assert expected_calibration_error([1, 0, 0], [1.0, 0.0, 0.0]) == pytest.approx(0.0)

    def test_ece_fully_miscalibrated(self):
        assert expected_calibration_error([1, 0], [0.0, 1.0]) == pytest.approx(1.0)

    def test_ece_empty(self):
        assert expected_calibration_error([], []) == 0.0

    def test_brier_perfect(self):
        assert brier_score([1, 0], [1.0, 0.0]) == pytest.approx(0.0)

    def test_brier_half_confidence(self):
        assert brier_score([1, 1], [0.5, 0.5]) == pytest.approx(0.25)

    def test_brier_empty(self):
        assert brier_score([], []) == 0.0


class TestBinaryMetrics:
    def test_confusion(self):
        result = detection_metrics([1, 1, 0, 0], [0.8, 0.3, 0.2, 0.1], threshold=0.5)
        assert result["confusion_matrix"] == (1, 0, 1, 2)
        assert result["accuracy"] == pytest.approx(0.75)
        assert result["precision"] == pytest.approx(1.0)
        assert result["recall"] == pytest.approx(0.5)
        assert result["f1_score"] == pytest.approx(2 / 3)
        # MCC = (tp*tn - fp*fn) / sqrt((tp+fp)(tp+fn)(tn+fp)(tn+fn))
        #     = (1*2 - 0) / sqrt(1*2*2*3) = 2/sqrt(12)
        assert result["matthews_corrcoef"] == pytest.approx(2 / 12**0.5)

    def test_contains_threshold_free_metrics(self):
        result = detection_metrics([1, 1, 0, 0], [0.8, 0.7, 0.2, 0.1])
        assert "roc_auc" in result
        assert "pr_auc" in result
        assert "expected_calibration_error" in result
        assert "brier_score" in result

    def test_length_mismatch(self):
        with pytest.raises(ValueError):
            detection_metrics([1, 0], [0.9])

    def test_namespace(self):
        assert DetectionMetrics.roc_auc([1, 0], [0.9, 0.1]) == roc_auc([1, 0], [0.9, 0.1])
        assert DetectionMetrics.compute([1, 0], [0.9, 0.1])["roc_auc"] == pytest.approx(1.0)
