"""Tests for ML detectors: IsolationForest, RandomForest, XGBoost."""

from __future__ import annotations

import pytest

from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import (
    THREAT_CATEGORIES,
    RandomForestThreatClassifier,
    XGBoostThreatClassifier,
)
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
    """Generate synthetic training data."""
    import random

    random.seed(42)
    x = [[random.uniform(0, 100) for _ in range(12)] for _ in range(n)]
    y = [random.choice([0, 1, 2]) for _ in range(n)]
    return x, y


class TestIsolationForestDetector:
    def setup_method(self) -> None:
        self.detector = IsolationForestDetector()

    def test_name(self) -> None:
        assert self.detector.name == "isolation-forest"

    def test_not_trained(self) -> None:
        assert self.detector.is_trained is False

    def test_train(self) -> None:
        x, _ = _make_training_data()
        self.detector.train(x)
        assert self.detector.is_trained is True
        assert self.detector.metadata.training_samples == 50

    @pytest.mark.asyncio
    async def test_detect_untrained(self) -> None:
        features = _make_features()
        result = await self.detector.detect("test prompt", features)
        assert result.findings == []
        assert result.risk_score == 0.0

    @pytest.mark.asyncio
    async def test_detect_trained(self) -> None:
        x, _ = _make_training_data(100)
        self.detector.train(x)
        features = _make_features(length=500, word_count=200, entropy=4.9)
        result = await self.detector.detect(
            "extremely long unusual prompt with special chars!!!", features
        )
        assert result.detector_name == "isolation-forest"

    @pytest.mark.asyncio
    async def test_predict_untrained(self) -> None:
        result = await self.detector.predict(
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
        )
        assert result["is_anomaly"] is False

    @pytest.mark.asyncio
    async def test_predict_trained(self) -> None:
        x, _ = _make_training_data(100)
        self.detector.train(x)
        result = await self.detector.predict([50.0] * 12)
        assert "is_anomaly" in result
        assert "anomaly_score" in result

    def test_health(self) -> None:
        h = self.detector.health()
        assert h["status"] == "healthy"
        assert h["is_trained"] is False


class TestRandomForestClassifier:
    def setup_method(self) -> None:
        self.classifier = RandomForestThreatClassifier()

    def test_name(self) -> None:
        assert self.classifier.name == "random-forest-classifier"

    def test_not_trained(self) -> None:
        assert self.classifier.is_trained is False

    def test_train(self) -> None:
        x, y = _make_training_data(60)
        self.classifier.train(x, y)
        assert self.classifier.is_trained is True
        assert self.classifier.metadata.training_samples == 60

    @pytest.mark.asyncio
    async def test_classify_untrained(self) -> None:
        features = _make_features()
        result = await self.classifier.classify("test", features)
        assert all(v == 0.0 for v in result.values())

    @pytest.mark.asyncio
    async def test_classify_trained(self) -> None:
        x, y = _make_training_data(60)
        self.classifier.train(x, y)
        features = _make_features()
        result = await self.classifier.classify("test prompt", features)
        assert len(result) > 0
        assert sum(result.values()) > 0.9  # Probabilities should sum ~1.0

    @pytest.mark.asyncio
    async def test_predict_trained(self) -> None:
        x, y = _make_training_data(60)
        self.classifier.train(x, y)
        result = await self.classifier.predict([50.0] * 12)
        assert "predicted_class" in result
        assert "confidence" in result

    def test_classes(self) -> None:
        assert len(self.classifier.classes) == len(THREAT_CATEGORIES)

    def test_health(self) -> None:
        h = self.classifier.health()
        assert h["is_trained"] is False
        assert h["class_count"] == len(THREAT_CATEGORIES)


class TestXGBoostClassifier:
    def setup_method(self) -> None:
        self.classifier = XGBoostThreatClassifier()

    def test_name(self) -> None:
        assert self.classifier.name == "xgboost-classifier"

    def test_available(self) -> None:
        assert self.classifier.is_available is True  # We installed xgboost

    def test_train(self) -> None:
        x, y = _make_training_data(60)
        self.classifier.train(x, y)
        assert self.classifier.is_trained is True

    @pytest.mark.asyncio
    async def test_classify_trained(self) -> None:
        x, y = _make_training_data(60)
        self.classifier.train(x, y)
        features = _make_features()
        result = await self.classifier.classify("test prompt", features)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_predict_trained(self) -> None:
        x, y = _make_training_data(60)
        self.classifier.train(x, y)
        result = await self.classifier.predict([50.0] * 12)
        assert "predicted_class" in result
        assert "confidence" in result
