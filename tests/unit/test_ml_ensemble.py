"""Tests for EnsembleDetector."""

from __future__ import annotations

import pytest

from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import RandomForestThreatClassifier
from q_guardian.ml.models.ensemble import EnsembleDetector
from q_guardian.security.models import PromptFeatures


def _make_features(**overrides) -> PromptFeatures:
    defaults = {
        "length": 100,
        "word_count": 20,
        "line_count": 3,
        "token_estimate": 25,
        "entropy": 3.5,
        "uppercase_ratio": 0.1,
        "digit_ratio": 0.05,
        "special_char_count": 5,
        "code_block_count": 1,
        "url_count": 0,
        "markdown_usage": True,
        "has_unicode_escaped": False,
        "has_html_tags": False,
        "suspicious_keywords": [],
        "repeated_patterns": [],
    }
    defaults.update(overrides)
    return PromptFeatures(**defaults)


def _make_training_data(n: int = 50) -> tuple[list[list[float]], list[int]]:
    import random

    random.seed(42)
    x = [[random.uniform(0, 100) for _ in range(12)] for _ in range(n)]
    y = [random.choice([0, 1, 2]) for _ in range(n)]
    return x, y


class TestEnsembleDetector:
    def setup_method(self) -> None:
        self.detector = IsolationForestDetector()
        self.classifier = RandomForestThreatClassifier()
        x, y = _make_training_data(60)
        self.detector.train(x)
        self.classifier.train(x, y)

    def test_name(self) -> None:
        ensemble = EnsembleDetector()
        assert ensemble.name == "ensemble-detector"

    def test_add_remove_detector(self) -> None:
        ensemble = EnsembleDetector()
        ensemble.add_detector(self.detector, weight=2.0)
        assert ensemble.detector_count == 1
        assert ensemble.remove_detector("isolation-forest") is True
        assert ensemble.detector_count == 0

    def test_remove_nonexistent(self) -> None:
        ensemble = EnsembleDetector()
        assert ensemble.remove_detector("nope") is False

    def test_set_weight(self) -> None:
        ensemble = EnsembleDetector()
        ensemble.add_detector(self.detector)
        ensemble.set_weight("isolation-forest", 3.0)

    def test_init_with_detectors(self) -> None:
        ensemble = EnsembleDetector(detectors=[self.detector, self.classifier])
        assert ensemble.detector_count == 2

    @pytest.mark.asyncio
    async def test_detect_empty(self) -> None:
        ensemble = EnsembleDetector()
        features = _make_features()
        result = await ensemble.detect("test", features)
        assert result.risk_score == 0.0
        assert result.findings == []

    @pytest.mark.asyncio
    async def test_detect_combined(self) -> None:
        ensemble = EnsembleDetector(
            detectors=[self.detector, self.classifier],
            weights={"isolation-forest": 2.0, "random-forest-classifier": 1.0},
        )
        features = _make_features()
        result = await ensemble.detect("test prompt", features)
        assert result.detector_name == "ensemble-detector"
        assert result.metadata["detector_count"] == 2

    @pytest.mark.asyncio
    async def test_predict(self) -> None:
        ensemble = EnsembleDetector(detectors=[self.detector])
        result = await ensemble.predict([50.0] * 12)
        assert "isolation-forest" in result

    def test_health(self) -> None:
        ensemble = EnsembleDetector(detectors=[self.detector])
        h = ensemble.health()
        assert h["detector_count"] == 1
        assert "isolation-forest" in h["detectors"]
