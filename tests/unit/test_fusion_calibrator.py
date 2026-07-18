"""Unit tests for ConfidenceCalibrator."""

from __future__ import annotations

import pytest
import numpy as np

from q_guardian.quantum.fusion.calibrator import ConfidenceCalibrator
from q_guardian.quantum.fusion.prediction import ThreatPrediction


def _pred(provider_id: str, confidence: float, label: str = "benign") -> ThreatPrediction:
    return ThreatPrediction(
        provider_id=provider_id,
        predicted_label=label,
        confidence=confidence,
        probabilities={label: confidence},
    )


class TestCalibratorConstruction:
    def test_default_none(self):
        c = ConfidenceCalibrator()
        assert c.method == "none"
        assert c.temperature == 1.0

    def test_custom_method(self):
        c = ConfidenceCalibrator(method="z_score", temperature=0.5)
        assert c.method == "z_score"
        assert c.temperature == 0.5


class TestCalibratorNone:
    def test_passthrough(self):
        c = ConfidenceCalibrator(method="none")
        preds = [_pred("a", 0.3), _pred("b", 0.9)]
        result = c.calibrate(preds)
        assert len(result) == 2
        assert result[0].confidence == 0.3
        assert result[1].confidence == 0.9

    def test_empty(self):
        c = ConfidenceCalibrator(method="none")
        assert c.calibrate([]) == []


class TestCalibratorTemperature:
    def test_temperature_scales_confidence(self):
        c = ConfidenceCalibrator(method="temperature", temperature=0.5)
        preds = [_pred("a", 0.8), _pred("b", 0.3)]
        result = c.calibrate(preds)
        assert len(result) == 2
        assert result[0].confidence != 0.8

    def test_temperature_extreme_low(self):
        c = ConfidenceCalibrator(method="temperature", temperature=0.1)
        preds = [_pred("a", 0.8)]
        result = c.calibrate(preds)
        assert result[0].confidence > 0.7

    def test_temperature_extreme_high(self):
        c = ConfidenceCalibrator(method="temperature", temperature=10.0)
        preds = [_pred("a", 0.8)]
        result = c.calibrate(preds)
        assert 0.4 < result[0].confidence < 0.6

    def test_temperature_calibrates_probabilities(self):
        c = ConfidenceCalibrator(method="temperature", temperature=0.5)
        preds = [_pred("a", 0.8)]
        result = c.calibrate(preds)
        assert "calibration_method" in result[0].metadata


class TestCalibratorMinMax:
    def test_no_change_with_insufficient_data(self):
        c = ConfidenceCalibrator(method="min_max")
        preds = [_pred("a", 0.8)]
        result = c.calibrate(preds)
        assert result[0].confidence == 0.8

    def test_scales_after_enough_data(self):
        c = ConfidenceCalibrator(method="min_max")
        for val in [0.2, 0.4, 0.6, 0.8]:
            c.calibrate([_pred("a", val)])
        result = c.calibrate([_pred("a", 0.6)])
        assert 0.0 <= result[0].confidence <= 1.0


class TestCalibratorZScore:
    def test_no_change_insufficient(self):
        c = ConfidenceCalibrator(method="z_score")
        preds = [_pred("a", 0.5)]
        result = c.calibrate(preds)
        assert result[0].confidence == 0.5

    def test_z_score_with_enough_data(self):
        c = ConfidenceCalibrator(method="z_score")
        for val in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            c.calibrate([_pred("a", val)])
        result = c.calibrate([_pred("a", 0.5)])
        assert 0.0 <= result[0].confidence <= 1.0


class TestCalibratorStats:
    def test_stats_empty(self):
        c = ConfidenceCalibrator()
        s = c.get_stats()
        assert s["method"] == "none"
        assert s["global_min"] is None
        assert s["global_max"] is None
        assert s["providers"] == {}

    def test_stats_after_calibration(self):
        c = ConfidenceCalibrator(method="temperature")
        c.calibrate([_pred("a", 0.3), _pred("b", 0.7)])
        s = c.get_stats()
        assert "a" in s["providers"]
        assert "b" in s["providers"]
        assert s["global_min"] == 0.3
        assert s["global_max"] == 0.7

    def test_reset(self):
        c = ConfidenceCalibrator()
        c.calibrate([_pred("a", 0.5)])
        c.reset()
        s = c.get_stats()
        assert s["global_min"] is None


class TestCalibratorMultipleProviders:
    def test_per_provider_calibration(self):
        c = ConfidenceCalibrator(method="min_max")
        for val in [0.1, 0.3, 0.5, 0.7, 0.9]:
            c.calibrate([_pred("a", val), _pred("b", 1.0 - val)])
        result = c.calibrate([_pred("a", 0.5), _pred("b", 0.5)])
        assert len(result) == 2
