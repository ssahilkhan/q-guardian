"""Tests for InferenceEngine."""

from __future__ import annotations

import pytest

from q_guardian.ml.inference.engine import InferenceEngine
from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import RandomForestThreatClassifier
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


def _make_training_data(n: int = 60) -> tuple[list[list[float]], list[int]]:
    import random

    random.seed(42)
    x = [[random.uniform(0, 100) for _ in range(12)] for _ in range(n)]
    y = [random.choice([0, 1, 2]) for _ in range(n)]
    return x, y


class TestInferenceEngine:
    def setup_method(self) -> None:
        self.engine = InferenceEngine()
        self.detector = IsolationForestDetector()
        self.classifier = RandomForestThreatClassifier()
        x, y = _make_training_data(60)
        self.detector.train(x)
        self.classifier.train(x, y)

    def test_register_detector(self) -> None:
        self.engine.register_detector(self.detector)
        assert self.engine.detector_count == 1

    def test_register_classifier(self) -> None:
        self.engine.register_classifier(self.classifier)
        assert self.engine.classifier_count == 1

    def test_unregister_detector(self) -> None:
        self.engine.register_detector(self.detector)
        assert self.engine.unregister_detector("isolation-forest") is True
        assert self.engine.detector_count == 0

    def test_unregister_classifier(self) -> None:
        self.engine.register_classifier(self.classifier)
        assert self.engine.unregister_classifier("random-forest-classifier") is True
        assert self.engine.classifier_count == 0

    @pytest.mark.asyncio
    async def test_run_empty(self) -> None:
        features = _make_features()
        result = await self.engine.run("test", features)
        assert result.risk_score == 0.0
        assert result.findings == []

    @pytest.mark.asyncio
    async def test_run_with_models(self) -> None:
        self.engine.register_detector(self.detector)
        self.engine.register_classifier(self.classifier)
        features = _make_features()
        result = await self.engine.run("test prompt", features)
        assert result.model_name == "inference-engine"
        assert result.processing_time_ms > 0
        assert result.metadata["detector_count"] == 1
        assert result.metadata["classifier_count"] == 1

    @pytest.mark.asyncio
    async def test_run_predictions(self) -> None:
        self.engine.register_classifier(self.classifier)
        features = _make_features()
        result = await self.engine.run("test", features)
        assert len(result.predictions) > 0
