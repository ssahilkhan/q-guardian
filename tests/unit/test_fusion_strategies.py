"""Unit tests for all fusion strategies."""

from __future__ import annotations

import pytest
import numpy as np

from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.quantum.fusion.strategies.base import FusedPrediction
from q_guardian.quantum.fusion.strategies.weighted_voting import WeightedVotingStrategy
from q_guardian.quantum.fusion.strategies.confidence import ConfidenceFusionStrategy
from q_guardian.quantum.fusion.strategies.adaptive import AdaptiveFusionStrategy
from q_guardian.quantum.fusion.strategies.stacking import StackingFusionStrategy
from q_guardian.quantum.fusion.strategies.bayesian import BayesianFusionStrategy
from q_guardian.quantum.exceptions import FusionError


def _pred(pid: str, label: str, confidence: float, risk: float = 0.0) -> ThreatPrediction:
    return ThreatPrediction(
        provider_id=pid,
        predicted_label=label,
        confidence=confidence,
        risk_score=risk,
        probabilities={label: confidence},
    )


def _invalid_pred(pid: str) -> ThreatPrediction:
    return ThreatPrediction(
        provider_id=pid,
        predicted_label="unknown",
        confidence=0.0,
        is_valid=False,
        error_message="test failure",
    )


# ── WeightedVotingStrategy ─────────────────────────────────────────────


class TestWeightedVotingStrategy:
    def test_name(self):
        s = WeightedVotingStrategy()
        assert s.name == "weighted_voting"
        assert s.display_name == "Weighted Voting"

    def test_basic_unanimous(self):
        s = WeightedVotingStrategy()
        preds = [
            _pred("a", "benign", 0.8),
            _pred("b", "benign", 0.9),
            _pred("c", "benign", 0.7),
        ]
        result = s.fuse(preds)
        assert result.predicted_label == "benign"
        assert result.confidence > 0.9
        assert result.num_providers == 3

    def test_tie_breaking(self):
        s = WeightedVotingStrategy()
        preds = [
            _pred("a", "benign", 0.8),
            _pred("b", "threat", 0.8),
        ]
        result = s.fuse(preds)
        assert result.predicted_label in ("benign", "threat")
        assert result.num_providers == 2

    def test_weighted_override(self):
        s = WeightedVotingStrategy()
        preds = [
            _pred("a", "benign", 0.5),
            _pred("b", "threat", 0.5),
        ]
        result = s.fuse(preds, weights={"a": 10.0, "b": 1.0})
        assert result.predicted_label == "benign"

    def test_empty_predictions(self):
        s = WeightedVotingStrategy()
        result = s.fuse([])
        assert result.predicted_label == "unknown"
        assert result.confidence == 0.0

    def test_all_invalid(self):
        s = WeightedVotingStrategy()
        result = s.fuse([_invalid_pred("a"), _invalid_pred("b")])
        assert result.predicted_label == "unknown"
        assert result.num_failed == 2

    def test_partial_invalid(self):
        s = WeightedVotingStrategy()
        result = s.fuse([
            _pred("a", "benign", 0.8),
            _invalid_pred("b"),
        ])
        assert result.predicted_label == "benign"
        assert result.num_providers == 1
        assert result.num_failed == 1

    def test_contributions_normalized(self):
        s = WeightedVotingStrategy()
        preds = [_pred("a", "x", 0.5), _pred("b", "x", 0.5)]
        result = s.fuse(preds)
        total = sum(result.provider_contributions.values())
        assert abs(total - 1.0) < 0.01

    def test_reasoning_summary(self):
        s = WeightedVotingStrategy()
        preds = [_pred("a", "benign", 0.8)]
        result = s.fuse(preds)
        assert "benign" in result.reasoning_summary

    def test_risk_score_averaged(self):
        s = WeightedVotingStrategy()
        preds = [
            _pred("a", "x", 0.5, risk=0.2),
            _pred("b", "x", 0.5, risk=0.8),
        ]
        result = s.fuse(preds)
        assert abs(result.risk_score - 0.5) < 0.01

    def test_health(self):
        s = WeightedVotingStrategy()
        h = s.health()
        assert h["strategy"] == "weighted_voting"


# ── ConfidenceFusionStrategy ───────────────────────────────────────────


class TestConfidenceFusionStrategy:
    def test_name(self):
        s = ConfidenceFusionStrategy()
        assert s.name == "confidence_fusion"

    def test_high_confidence_wins(self):
        s = ConfidenceFusionStrategy()
        preds = [
            _pred("a", "benign", 0.3),
            _pred("b", "threat", 0.9),
        ]
        result = s.fuse(preds)
        assert result.predicted_label == "threat"

    def test_equal_confidence(self):
        s = ConfidenceFusionStrategy()
        preds = [
            _pred("a", "benign", 0.5),
            _pred("b", "threat", 0.5),
        ]
        result = s.fuse(preds)
        assert result.predicted_label in ("benign", "threat")

    def test_empty(self):
        s = ConfidenceFusionStrategy()
        result = s.fuse([])
        assert result.predicted_label == "unknown"

    def test_single_provider(self):
        s = ConfidenceFusionStrategy()
        result = s.fuse([_pred("a", "threat", 0.9)])
        assert result.predicted_label == "threat"
        assert result.confidence > 0.8

    def test_contributions_sum_to_one(self):
        s = ConfidenceFusionStrategy()
        preds = [_pred("a", "x", 0.3), _pred("b", "y", 0.7)]
        result = s.fuse(preds)
        total = sum(result.provider_contributions.values())
        assert abs(total - 1.0) < 0.01

    def test_weight_override(self):
        s = ConfidenceFusionStrategy()
        preds = [
            _pred("a", "benign", 0.9),
            _pred("b", "threat", 0.9),
        ]
        result = s.fuse(preds, weights={"b": 100.0})
        assert result.predicted_label == "threat"


# ── AdaptiveFusionStrategy ─────────────────────────────────────────────


class TestAdaptiveFusionStrategy:
    def test_name(self):
        s = AdaptiveFusionStrategy()
        assert s.name == "adaptive"

    def test_basic_fusion(self):
        s = AdaptiveFusionStrategy()
        preds = [_pred("a", "benign", 0.8), _pred("b", "threat", 0.6)]
        result = s.fuse(preds)
        assert result.predicted_label in ("benign", "threat")
        assert result.num_providers == 2

    def test_update_outcome(self):
        s = AdaptiveFusionStrategy()
        s.update_outcome("a", "benign", "benign")
        s.update_outcome("a", "benign", "benign")
        s.update_outcome("a", "threat", "benign")
        acc = s._get_accuracy("a")
        assert abs(acc - 2 / 3) < 0.01

    def test_adapts_weights(self):
        s = AdaptiveFusionStrategy()
        for _ in range(10):
            s.update_outcome("reliable", "benign", "benign")
        for _ in range(10):
            s.update_outcome("unreliable", "threat", "benign")

        preds = [_pred("reliable", "benign", 0.6), _pred("unreliable", "threat", 0.6)]
        results = []
        for _ in range(5):
            r = s.fuse(preds)
            results.append(r.predicted_label)
        assert results.count("benign") >= 3

    def test_window_size(self):
        s = AdaptiveFusionStrategy(window_size=5)
        assert s.window_size == 5

    def test_metadata_includes_accuracies(self):
        s = AdaptiveFusionStrategy()
        s.update_outcome("a", "x", "x")
        preds = [_pred("a", "x", 0.8)]
        result = s.fuse(preds)
        assert "provider_accuracies" in result.metadata

    def test_empty(self):
        s = AdaptiveFusionStrategy()
        result = s.fuse([])
        assert result.predicted_label == "unknown"

    def test_health(self):
        s = AdaptiveFusionStrategy()
        h = s.health()
        assert h["strategy"] == "adaptive"


# ── StackingFusionStrategy ─────────────────────────────────────────────


class TestStackingFusionStrategy:
    def test_name(self):
        s = StackingFusionStrategy()
        assert s.name == "stacking"

    def test_untrained_fallback(self):
        s = StackingFusionStrategy()
        preds = [_pred("a", "benign", 0.8), _pred("b", "threat", 0.6)]
        result = s.fuse(preds)
        assert result.predicted_label in ("benign", "threat")
        assert result.num_providers == 2

    def test_train_metalearner(self):
        s = StackingFusionStrategy()
        training_batches = [
            [_pred("a", "benign", 0.9), _pred("b", "benign", 0.8)],
            [_pred("a", "benign", 0.85), _pred("b", "benign", 0.75)],
            [_pred("a", "threat", 0.2), _pred("b", "threat", 0.3)],
            [_pred("a", "threat", 0.15), _pred("b", "threat", 0.25)],
        ]
        labels = ["benign", "benign", "threat", "threat"]
        metrics = s.train_metalearner(training_batches, labels)
        assert s.is_trained
        assert metrics["samples"] == 4

    def test_trained_prediction(self):
        s = StackingFusionStrategy(epochs=200)
        batches = []
        labels = []
        rng = np.random.default_rng(42)
        for _ in range(20):
            conf_a = rng.uniform(0.7, 0.95)
            conf_b = rng.uniform(0.7, 0.95)
            batches.append([_pred("a", "benign", conf_a), _pred("b", "benign", conf_b)])
            labels.append("benign")
        for _ in range(20):
            conf_a = rng.uniform(0.1, 0.4)
            conf_b = rng.uniform(0.1, 0.4)
            batches.append([_pred("a", "threat", conf_a), _pred("b", "threat", conf_b)])
            labels.append("threat")
        s.train_metalearner(batches, labels)

        result = s.fuse([_pred("a", "benign", 0.9), _pred("b", "benign", 0.85)])
        assert result.predicted_label == "benign"
        assert result.calibrated is True

    def test_empty(self):
        s = StackingFusionStrategy()
        result = s.fuse([])
        assert result.predicted_label == "unknown"

    def test_contributions(self):
        s = StackingFusionStrategy()
        preds = [_pred("a", "x", 0.3), _pred("b", "y", 0.7)]
        result = s.fuse(preds)
        total = sum(result.provider_contributions.values())
        assert abs(total - 1.0) < 0.01

    def test_description(self):
        s = StackingFusionStrategy()
        assert "default" in s.description.lower()


# ── BayesianFusionStrategy ─────────────────────────────────────────────


class TestBayesianFusionStrategy:
    def test_name(self):
        s = BayesianFusionStrategy()
        assert s.name == "bayesian"

    def test_fuse_raises(self):
        s = BayesianFusionStrategy()
        preds = [_pred("a", "benign", 0.8)]
        with pytest.raises(FusionError, match="not yet implemented"):
            s.fuse(preds)

    def test_predict_with_uncertainty_raises(self):
        s = BayesianFusionStrategy()
        with pytest.raises(FusionError):
            s.predict_with_uncertainty([])

    def test_update_posterior_raises(self):
        s = BayesianFusionStrategy()
        with pytest.raises(FusionError):
            s.update_posterior("a", True)


# ── Strategy switching ─────────────────────────────────────────────────


class TestStrategySwitching:
    def test_all_strategies_produce_fused_prediction(self):
        strategies = [
            WeightedVotingStrategy(),
            ConfidenceFusionStrategy(),
            AdaptiveFusionStrategy(),
            StackingFusionStrategy(),
        ]
        preds = [
            _pred("a", "benign", 0.8),
            _pred("b", "benign", 0.7),
            _pred("c", "threat", 0.3),
        ]
        for strategy in strategies:
            result = strategy.fuse(preds)
            assert isinstance(result, FusedPrediction)
            assert result.strategy_name == strategy.name
            assert result.num_providers == 3
