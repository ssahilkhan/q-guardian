"""Unit tests for ThreatPrediction and PredictionProvider abstractions."""

from __future__ import annotations

import pytest
from typing import Any

from q_guardian.quantum.fusion.prediction import ThreatPrediction, ReasoningTrace
from q_guardian.quantum.fusion.providers import PredictionProvider


class TestThreatPredictionConstruction:
    def test_minimal(self):
        p = ThreatPrediction(provider_id="test", predicted_label="benign")
        assert p.provider_id == "test"
        assert p.predicted_label == "benign"
        assert p.confidence == 0.0
        assert p.is_valid is True

    def test_full(self):
        p = ThreatPrediction(
            provider_id="qsvm",
            predicted_label="injection",
            confidence=0.92,
            probabilities={"benign": 0.08, "injection": 0.92},
            risk_score=0.85,
            latency_ms=12.5,
            backend="simulator",
            model_name="qsvm-v1",
            model_version="1.0.0",
        )
        assert p.confidence == 0.92
        assert p.risk_score == 0.85
        assert p.backend == "simulator"
        assert p.model_name == "qsvm-v1"

    def test_default_values(self):
        p = ThreatPrediction(provider_id="x", predicted_label="y")
        assert p.prediction_id is not None
        assert len(p.prediction_id) > 0
        assert p.latency_ms == 0.0
        assert p.backend == ""
        assert p.reasoning is None
        assert p.metadata == {}
        assert p.error_message == ""

    def test_with_reasoning(self):
        r = ReasoningTrace(
            steps=["step1", "step2"],
            evidence=["evidence1"],
            rules_triggered=["rule-1"],
            feature_importances={"length": 0.5},
        )
        p = ThreatPrediction(
            provider_id="rule",
            predicted_label="benign",
            reasoning=r,
        )
        assert p.reasoning is not None
        assert len(p.reasoning.steps) == 2
        assert p.reasoning.rules_triggered == ["rule-1"]

    def test_invalid_prediction(self):
        p = ThreatPrediction(
            provider_id="failing",
            predicted_label="unknown",
            is_valid=False,
            error_message="Connection timeout",
        )
        assert p.is_valid is False
        assert p.error_message == "Connection timeout"

    def test_probabilities(self):
        p = ThreatPrediction(
            provider_id="test",
            predicted_label="benign",
            probabilities={"benign": 0.7, "threat": 0.3},
        )
        assert p.probabilities["benign"] == 0.7
        assert p.probabilities["threat"] == 0.3

    def test_timestamp_auto_set(self):
        p = ThreatPrediction(provider_id="t", predicted_label="x")
        assert p.timestamp is not None

    def test_serialization(self):
        p = ThreatPrediction(
            provider_id="test",
            predicted_label="benign",
            confidence=0.8,
            probabilities={"benign": 0.8, "threat": 0.2},
        )
        d = p.model_dump()
        assert d["provider_id"] == "test"
        assert d["confidence"] == 0.8
        assert isinstance(d, dict)


class TestReasoningTrace:
    def test_empty(self):
        r = ReasoningTrace()
        assert r.steps == []
        assert r.evidence == []
        assert r.rules_triggered == []
        assert r.feature_importances == {}

    def test_full(self):
        r = ReasoningTrace(
            steps=["analyze keywords", "check patterns"],
            evidence=["found 'ignore' keyword"],
            rules_triggered=["rule-001", "rule-003"],
            feature_importances={"entropy": 0.8, "length": 0.2},
            metadata={"source": "rule-engine"},
        )
        assert len(r.steps) == 2
        assert len(r.rules_triggered) == 2


class TestPredictionProviderContract:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            PredictionProvider()  # type: ignore

    def test_concrete_implementation(self):
        class DummyProvider(PredictionProvider):
            @property
            def provider_id(self) -> str:
                return "dummy"

            @property
            def provider_type(self) -> str:
                return "external"

            async def predict(self, prompt: str, features: dict[str, Any] | None = None) -> ThreatPrediction:
                return ThreatPrediction(
                    provider_id="dummy",
                    predicted_label="benign",
                    confidence=0.5,
                )

        p = DummyProvider()
        assert p.provider_id == "dummy"
        assert p.provider_type == "external"
        assert p.display_name == "dummy"
        assert p.version == "1.0.0"
        h = p.health()
        assert h["status"] == "healthy"

    def test_custom_display_name(self):
        class NamedProvider(PredictionProvider):
            @property
            def provider_id(self) -> str:
                return "np"

            @property
            def provider_type(self) -> str:
                return "external"

            @property
            def display_name(self) -> str:
                return "My Custom Provider"

            async def predict(self, prompt: str, features: dict[str, Any] | None = None) -> ThreatPrediction:
                return ThreatPrediction(provider_id="np", predicted_label="x", confidence=0.5)

        p = NamedProvider()
        assert p.display_name == "My Custom Provider"

    def test_train_default_noop(self):
        class SimpleProvider(PredictionProvider):
            @property
            def provider_id(self) -> str:
                return "simple"

            @property
            def provider_type(self) -> str:
                return "external"

            async def predict(self, prompt: str, features: dict[str, Any] | None = None) -> ThreatPrediction:
                return ThreatPrediction(provider_id="simple", predicted_label="x", confidence=0.5)

        p = SimpleProvider()
        import asyncio
        asyncio.run(p.train([{"prompt": "test", "label": "benign"}]))
