"""Unit tests for all fusion strategies."""

from __future__ import annotations

import math

import numpy as np
import pytest

from q_guardian.quantum.exceptions import FusionError
from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.quantum.fusion.strategies.adaptive import AdaptiveFusionStrategy
from q_guardian.quantum.fusion.strategies.base import FusedPrediction
from q_guardian.quantum.fusion.strategies.bayesian import BayesianFusionStrategy
from q_guardian.quantum.fusion.strategies.confidence import ConfidenceFusionStrategy
from q_guardian.quantum.fusion.strategies.stacking import StackingFusionStrategy
from q_guardian.quantum.fusion.strategies.weighted_voting import WeightedVotingStrategy


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
        # Soft vote: the fused confidence is the weighted average of the
        # providers' per-class probabilities, not a hard vote count.
        assert abs(result.confidence - 0.8) < 0.01
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
        result = s.fuse(
            [
                _pred("a", "benign", 0.8),
                _invalid_pred("b"),
            ]
        )
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

    def test_risk_score_is_threat_probability(self):
        s = WeightedVotingStrategy()
        preds = [
            _pred("a", "threat", 0.8),
            _pred("b", "benign", 0.9),
        ]
        result = s.fuse(preds)
        # The fused risk is the threat probability from the soft vote, not
        # the average of the providers' raw risk scores.
        assert abs(result.risk_score - 0.4) < 0.01

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


def _bayes_threat_pred(pid: str, threat: float, label: str | None = None) -> ThreatPrediction:
    """Build a prediction with an explicit {benign, threat} probability table."""
    label = "threat" if threat >= 0.5 else "benign" if label is None else label
    return ThreatPrediction(
        provider_id=pid,
        predicted_label=label,
        confidence=threat if label == "threat" else 1.0 - threat,
        risk_score=threat,
        probabilities={"benign": round(1.0 - threat, 6), "threat": round(threat, 6)},
    )


class TestBayesianFusionStrategy:
    def test_name(self):
        s = BayesianFusionStrategy()
        assert s.name == "bayesian"
        assert s.display_name == "Bayesian Fusion"

    def test_defaults(self):
        s = BayesianFusionStrategy()
        assert s.prior == 0.5
        assert s.decision_threshold == 0.7
        assert s.reliability_mode == "uniform"

    def test_neutral_prior_agreement(self):
        # With a neutral prior (0.5), a single detector reporting
        # threat=0.5 contributes zero log-odds, so posterior stays at 0.5.
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 0.5)])
        assert abs(result.risk_score - 0.5) < 1e-6
        assert result.num_providers == 1

    def test_single_detector_posterior_math(self):
        # posterior = sigmoid(logit(0.5) + logit(p)). For p=0.9 and
        # neutral prior, posterior == 0.9.
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 0.9)])
        assert abs(result.risk_score - 0.9) < 1e-6

    def test_two_detectors_agree_raises_posterior(self):
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 0.75), _bayes_threat_pred("b", 0.75)])
        # logit(0.75) = 1.0986; posterior = sigmoid(2 * 1.0986) = 0.9
        assert abs(result.risk_score - 0.9) < 1e-6

    def test_conflicting_detectors_neutralize(self):
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 0.9), _bayes_threat_pred("b", 0.1)])
        # logit(0.9)+logit(0.1) = 0 -> posterior = prior = 0.5
        assert abs(result.risk_score - 0.5) < 1e-6

    def test_aggressive_evidence_crosses_conservative_threshold(self):
        # 0.9 and 0.8 -> posterior well above the 0.7 threshold.
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 0.9), _bayes_threat_pred("b", 0.8)])
        assert result.predicted_label == "threat"
        assert result.risk_score > 0.7

    def test_benign_evidence_stays_benign(self):
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 0.1)])
        assert result.predicted_label == "benign"

    def test_custom_prior(self):
        s = BayesianFusionStrategy(prior=0.1)
        assert s.prior == 0.1
        result = s.fuse([_bayes_threat_pred("a", 0.5)])
        # neutral evidence leaves posterior == prior
        assert abs(result.risk_score - 0.1) < 1e-6

    def test_empty_predictions(self):
        s = BayesianFusionStrategy()
        result = s.fuse([])
        assert result.predicted_label == "unknown"
        assert result.confidence == 0.0

    def test_all_invalid(self):
        s = BayesianFusionStrategy()
        result = s.fuse([_invalid_pred("a"), _invalid_pred("b")])
        assert result.predicted_label == "unknown"
        assert result.num_failed == 2

    def test_partial_invalid(self):
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 0.9), _invalid_pred("b")])
        assert result.predicted_label == "threat"
        assert result.num_providers == 1
        assert result.num_failed == 1

    def test_missing_threat_key_uses_label_confidence(self):
        # A prediction with no "threat" key but predicted_label/confidence.
        pred = ThreatPrediction(
            provider_id="a",
            predicted_label="threat",
            confidence=0.8,
            probabilities={},
        )
        s = BayesianFusionStrategy()
        result = s.fuse([pred])
        assert abs(result.risk_score - 0.8) < 1e-6

    def test_invalid_probability_ignored_as_missing(self):
        # Threat probability outside [0,1] is treated as missing evidence,
        # not fabricated. Since prior is neutral, posterior stays 0.5.
        pred = ThreatPrediction(
            provider_id="a",
            predicted_label="unknown",
            confidence=0.0,
            probabilities={"threat": 1.5, "benign": -0.5},
        )
        s = BayesianFusionStrategy()
        result = s.fuse([pred])
        assert result.num_providers == 1
        assert abs(result.risk_score - 0.5) < 1e-6

    def test_nan_probability_ignored(self):
        pred = ThreatPrediction(
            provider_id="a",
            predicted_label="threat",
            confidence=0.0,
            probabilities={"threat": float("nan"), "benign": float("nan")},
        )
        s = BayesianFusionStrategy()
        result = s.fuse([pred])
        assert abs(result.risk_score - 0.5) < 1e-6

    def test_constant_probability_adds_no_evidence(self):
        # A detector fixed at threat=0.5 must not shift the posterior.
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 0.5), _bayes_threat_pred("b", 0.9)])
        assert abs(result.risk_score - 0.9) < 1e-6

    def test_configured_reliability_downweights(self):
        s = BayesianFusionStrategy(
            reliability_mode="configured",
            reliability={"a": 0.0, "b": 1.0},
        )
        result = s.fuse([_bayes_threat_pred("a", 0.999), _bayes_threat_pred("b", 0.5)])
        # a is fully neutralized; b is neutral -> posterior == prior
        assert abs(result.risk_score - 0.5) < 1e-6

    def test_health(self):
        s = BayesianFusionStrategy()
        h = s.health()
        assert h["strategy"] == "bayesian"

    def test_explainability_metadata(self):
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 0.8), _bayes_threat_pred("b", 0.9)])
        md = result.metadata
        assert "prior" in md
        assert "evidence_log_odds" in md
        assert "posterior_logit" in md
        assert "decision_threshold" in md
        assert md["prior"] == 0.5
        assert "a" in md["evidence_log_odds"]
        assert "b" in md["evidence_log_odds"]

    def test_update_posterior_records_outcome(self):
        s = BayesianFusionStrategy()
        s.update_posterior("a", True)
        assert s.posterior_recorded_count("a") == 1
        with pytest.raises(FusionError):
            s.update_posterior("a", "not-a-bool")

    def test_predict_with_uncertainty(self):
        s = BayesianFusionStrategy()
        out = s.predict_with_uncertainty([_bayes_threat_pred("a", 0.8)])
        assert isinstance(out["fused_prediction"], FusedPrediction)
        assert abs(out["posterior"] - 0.8) < 1e-6
        assert "a" in out["evidence"]

    def test_invalid_constructor_prior(self):
        with pytest.raises(FusionError):
            BayesianFusionStrategy(prior=-0.1)
        with pytest.raises(FusionError):
            BayesianFusionStrategy(prior=1.5)

    def test_invalid_threshold(self):
        with pytest.raises(FusionError):
            BayesianFusionStrategy(decision_threshold=1.5)
        with pytest.raises(FusionError):
            BayesianFusionStrategy(decision_threshold=-0.1)

    def test_invalid_reliability_mode(self):
        with pytest.raises(FusionError):
            BayesianFusionStrategy(reliability_mode="bogus")

    def test_invalid_reliability_weight(self):
        with pytest.raises(FusionError):
            BayesianFusionStrategy(reliability_mode="configured", reliability={"a": -1.0})

    def test_boundary_probabilities_are_stable(self):
        s = BayesianFusionStrategy()
        result = s.fuse([_bayes_threat_pred("a", 1.0)])
        assert math.isfinite(result.risk_score)
        assert 0.0 < result.risk_score <= 1.0

    def test_extreme_evidence_no_overflow(self):
        s = BayesianFusionStrategy()
        result = s.fuse(
            [
                _bayes_threat_pred("a", 0.999999),
                _bayes_threat_pred("b", 0.999999),
                _bayes_threat_pred("c", 0.999999),
            ]
        )
        assert math.isfinite(result.risk_score)
        assert result.predicted_label == "threat"

    def test_quantum_median_when_unavailable_handled(self):
        # Quantum absence is just another missing provider: removing the
        # quantum detector must not change the posterior of the remaining
        # providers. This guards against artificially favouring quantum.
        s = BayesianFusionStrategy()
        both = s.fuse([_bayes_threat_pred("classical", 0.8), _bayes_threat_pred("quantum", 0.5)])
        classical_only = s.fuse([_bayes_threat_pred("classical", 0.8)])
        assert abs(both.risk_score - classical_only.risk_score) < 1e-6


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
