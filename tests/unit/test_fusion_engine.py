"""Unit tests for HybridFusionEngine."""

from __future__ import annotations

from typing import Any

import pytest

from q_guardian.quantum.exceptions import ConfigurationError, FusionError
from q_guardian.quantum.fusion.calibrator import ConfidenceCalibrator
from q_guardian.quantum.fusion.engine import HybridFusionEngine
from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.quantum.fusion.providers import PredictionProvider
from q_guardian.quantum.fusion.strategies.base import FusedPrediction
from q_guardian.quantum.fusion.strategies.confidence import ConfidenceFusionStrategy
from q_guardian.quantum.fusion.strategies.weighted_voting import WeightedVotingStrategy


class SimpleProvider(PredictionProvider):
    def __init__(self, pid: str, label: str = "benign", conf: float = 0.8):
        self._pid = pid
        self._label = label
        self._conf = conf

    @property
    def provider_id(self) -> str:
        return self._pid

    @property
    def provider_type(self) -> str:
        return "test"

    async def predict(
        self, prompt: str, features: dict[str, Any] | None = None
    ) -> ThreatPrediction:
        return ThreatPrediction(
            provider_id=self._pid,
            predicted_label=self._label,
            confidence=self._conf,
        )


class FailingProvider(PredictionProvider):
    @property
    def provider_id(self) -> str:
        return "failing"

    @property
    def provider_type(self) -> str:
        return "test"

    async def predict(
        self, prompt: str, features: dict[str, Any] | None = None
    ) -> ThreatPrediction:
        raise RuntimeError("Provider crashed")


class TestEngineConstruction:
    def test_default_strategy(self):
        e = HybridFusionEngine()
        assert e.active_strategy_name == "stacking"

    def test_custom_strategy(self):
        s = WeightedVotingStrategy()
        e = HybridFusionEngine(strategy=s)
        assert e.active_strategy_name == "weighted_voting"

    def test_initial_state(self):
        e = HybridFusionEngine()
        assert e.provider_count == 0
        assert e.total_fusions == 0
        assert e.total_provider_failures == 0


class TestEngineProviderRegistration:
    def test_register(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a"))
        assert e.provider_count == 1
        assert "a" in e.provider_ids

    def test_register_with_weight(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a"), weight=2.0)
        assert e.provider_count == 1

    def test_unregister(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a"))
        assert e.unregister_provider("a") is True
        assert e.provider_count == 0

    def test_unregister_nonexistent(self):
        e = HybridFusionEngine()
        assert e.unregister_provider("x") is False

    def test_get_provider(self):
        p = SimpleProvider("a")
        e = HybridFusionEngine()
        e.register_provider(p)
        assert e.get_provider("a") is p

    def test_get_nonexistent(self):
        e = HybridFusionEngine()
        assert e.get_provider("x") is None


class TestEngineStrategyRegistration:
    def test_register_strategy(self):
        e = HybridFusionEngine()
        e.register_strategy(ConfidenceFusionStrategy())
        assert e.strategy_count >= 2

    def test_switch_strategy(self):
        e = HybridFusionEngine()
        e.register_strategy(ConfidenceFusionStrategy())
        e.set_strategy("confidence_fusion")
        assert e.active_strategy_name == "confidence_fusion"

    def test_switch_nonexistent_raises(self):
        e = HybridFusionEngine()
        with pytest.raises(ConfigurationError):
            e.set_strategy("nonexistent")

    def test_unregister_active_raises(self):
        e = HybridFusionEngine()
        with pytest.raises(FusionError):
            e.unregister_strategy("stacking")

    def test_unregister_inactive(self):
        e = HybridFusionEngine()
        e.register_strategy(ConfidenceFusionStrategy())
        assert e.unregister_strategy("confidence_fusion") is True

    def test_available_strategies(self):
        e = HybridFusionEngine()
        e.register_strategy(ConfidenceFusionStrategy())
        strategies = e.available_strategies
        assert "stacking" in strategies
        assert "confidence_fusion" in strategies


class TestEngineFusion:
    async def test_basic_fusion(self):
        e = HybridFusionEngine(strategy=WeightedVotingStrategy())
        e.register_provider(SimpleProvider("a", "benign", 0.9))
        e.register_provider(SimpleProvider("b", "benign", 0.8))
        result = await e.fuse("test prompt")
        assert isinstance(result, FusedPrediction)
        assert result.predicted_label == "benign"
        assert result.num_providers == 2

    async def test_fusion_with_strategy_override(self):
        e = HybridFusionEngine(strategy=WeightedVotingStrategy())
        e.register_provider(SimpleProvider("a", "benign", 0.9))
        e.register_provider(SimpleProvider("b", "threat", 0.9))
        result = await e.fuse("test", strategy_name="weighted_voting")
        assert result.strategy_name == "weighted_voting"

    async def test_fusion_strategy_override_nonexistent(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a"))
        with pytest.raises(ConfigurationError):
            await e.fuse("test", strategy_name="nonexistent")

    async def test_fusion_increments_count(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a"))
        await e.fuse("test")
        assert e.total_fusions == 1

    async def test_fusion_with_provider_failure(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a", "benign", 0.9))
        e.register_provider(FailingProvider())
        result = await e.fuse("test")
        assert result.num_providers == 1
        assert result.num_failed == 1
        assert e.total_provider_failures == 1

    async def test_fusion_all_providers_fail(self):
        e = HybridFusionEngine()
        e.register_provider(FailingProvider())
        result = await e.fuse("test")
        assert result.num_failed == 1
        assert result.predicted_label == "unknown"

    async def test_fusion_no_providers(self):
        e = HybridFusionEngine()
        result = await e.fuse("test")
        assert result.num_providers == 0

    async def test_fusion_with_calibration(self):
        cal = ConfidenceCalibrator(method="none")
        e = HybridFusionEngine(calibrator=cal)
        e.register_provider(SimpleProvider("a", "benign", 0.8))
        result = await e.fuse("test", calibrate=True)
        assert result.calibrated is False

    async def test_fusion_without_calibration(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a"))
        result = await e.fuse("test", calibrate=False)
        assert isinstance(result, FusedPrediction)

    async def test_fusion_with_weight_override(self):
        e = HybridFusionEngine(strategy=WeightedVotingStrategy())
        e.register_provider(SimpleProvider("a", "benign", 0.5))
        e.register_provider(SimpleProvider("b", "threat", 0.5))
        result = await e.fuse("test", weights={"a": 100.0})
        assert result.predicted_label == "benign"

    async def test_fusion_latency_recorded(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a"))
        result = await e.fuse("test")
        assert "fusion_latency_ms" in result.metadata


class TestEnginePerformanceStats:
    async def test_empty_stats(self):
        e = HybridFusionEngine()
        stats = e.get_performance_stats()
        assert stats["total_fusions"] == 0

    async def test_stats_after_fusion(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a"))
        await e.fuse("test")
        stats = e.get_performance_stats()
        assert stats["total_fusions"] == 1
        assert stats["avg_latency_ms"] >= 0

    def test_clear_history(self):
        e = HybridFusionEngine()
        e.clear_history()
        stats = e.get_performance_stats()
        assert stats["history_size"] == 0


class TestEngineHealth:
    def test_health_empty(self):
        e = HybridFusionEngine()
        h = e.health()
        assert h["provider_count"] == 0
        assert h["active_strategy"] == "stacking"
        assert "calibration" in h

    def test_health_with_providers(self):
        e = HybridFusionEngine()
        e.register_provider(SimpleProvider("a"))
        h = e.health()
        assert h["provider_count"] == 1
        assert "a" in h["providers"]

    def test_health_with_strategy(self):
        e = HybridFusionEngine()
        e.register_strategy(ConfidenceFusionStrategy())
        h = e.health()
        assert "strategies" in h
        assert "confidence_fusion" in h["strategies"]
