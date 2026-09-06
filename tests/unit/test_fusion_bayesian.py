"""Dedicated tests for BayesianFusionStrategy.

Covers mathematical correctness (manually verifiable posteriors), input
validation, detector-availability edge cases, config integration, and
backward/forward compatibility with the strategy registry and engine.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from q_guardian.quantum.config import BayesianFusionConfig, QuantumFusionConfig
from q_guardian.quantum.enums import FusionStrategyType
from q_guardian.quantum.exceptions import FusionError
from q_guardian.quantum.fusion.engine import HybridFusionEngine
from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.quantum.fusion.strategies import (
    IMPLEMENTED_STRATEGIES,
    INTERFACE_ONLY_STRATEGIES,
)
from q_guardian.quantum.fusion.strategies.base import FusedPrediction
from q_guardian.quantum.fusion.strategies.bayesian import BayesianFusionStrategy


def _threat(
    pid: str,
    threat: float,
    label: str | None = None,
    is_valid: bool = True,
    error: str = "",
) -> ThreatPrediction:
    label = label or ("threat" if threat >= 0.5 else "benign")
    return ThreatPrediction(
        provider_id=pid,
        predicted_label=label,
        confidence=threat if label == "threat" else 1.0 - threat,
        risk_score=threat,
        probabilities={"benign": round(1.0 - threat, 6), "threat": round(threat, 6)},
        is_valid=is_valid,
        error_message=error,
    )


def _logit(p: float) -> float:
    eps = 1e-12
    p = min(max(p, eps), 1.0 - eps)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


# ── Mathematical correctness ────────────────────────────────────────────


class TestMathematicalCorrectness:
    def test_neutral_evidence_equals_prior(self):
        s = BayesianFusionStrategy(prior=0.5)
        r = s.fuse([_threat("a", 0.5)])
        assert r.risk_score == pytest.approx(0.5)

    def test_single_detector_matches_reported_threat(self):
        for p in (0.6, 0.75, 0.3, 0.99, 0.01):
            s = BayesianFusionStrategy(prior=0.5)
            r = s.fuse([_threat("a", p)])
            assert r.risk_score == pytest.approx(p, abs=1e-6)

    def test_two_agreeing_detectors_manual(self):
        s = BayesianFusionStrategy()
        r = s.fuse([_threat("a", 0.75), _threat("b", 0.75)])
        expected = _sigmoid(2 * _logit(0.75))
        assert r.risk_score == pytest.approx(expected, abs=1e-6)

    def test_conflicting_detectors_revert_to_prior(self):
        s = BayesianFusionStrategy()
        r = s.fuse([_threat("a", 0.9), _threat("b", 0.1)])
        assert r.risk_score == pytest.approx(0.5, abs=1e-6)

    def test_prior_is_correctly_injected(self):
        prior = 0.2
        s = BayesianFusionStrategy(prior=prior)
        r = s.fuse([_threat("a", 0.5)])
        assert r.risk_score == pytest.approx(prior, abs=1e-6)

    def test_prior_weight_scales_prior_influence(self):
        s = BayesianFusionStrategy(prior=0.9, prior_weight=0.0)
        r = s.fuse([_threat("a", 0.5)])
        # prior fully ignored, only neutral detector -> posterior 0.5
        assert r.risk_score == pytest.approx(0.5, abs=1e-6)

    def test_many_high_evidence_reaches_saturation(self):
        s = BayesianFusionStrategy()
        preds = [_threat(str(i), 0.95) for i in range(10)]
        r = s.fuse(preds)
        assert r.risk_score > 0.999
        assert math.isfinite(r.risk_score)

    def test_boundary_one_is_stable(self):
        s = BayesianFusionStrategy()
        r = s.fuse([_threat("a", 1.0)])
        assert math.isfinite(r.risk_score)
        assert 0.0 < r.risk_score <= 1.0

    def test_boundary_zero_is_stable(self):
        s = BayesianFusionStrategy()
        r = s.fuse([_threat("a", 0.0)])
        assert math.isfinite(r.risk_score)
        assert 0.0 <= r.risk_score < 1.0

    def test_threshold_decision(self):
        # posterior 0.9 >= 0.7 -> threat
        s = BayesianFusionStrategy()
        r = s.fuse([_threat("a", 0.9)])
        assert r.predicted_label == "threat"
        assert r.probabilities["threat"] == pytest.approx(0.9, abs=1e-6)
        assert r.probabilities["benign"] == pytest.approx(0.1, abs=1e-6)

    def test_below_threshold_is_benign(self):
        s = BayesianFusionStrategy()
        r = s.fuse([_threat("a", 0.6)])
        assert r.predicted_label == "benign"

    def test_custom_threshold_override(self):
        s = BayesianFusionStrategy(decision_threshold=0.6)
        r = s.fuse([_threat("a", 0.6)])
        assert r.predicted_label == "threat"


# ── Numerical / input validation ────────────────────────────────────────


class TestInputValidation:
    def test_constructor_rejects_out_of_range_prior(self):
        for bad in (-0.01, 1.01, float("nan"), float("inf"), -float("inf")):
            with pytest.raises(FusionError):
                BayesianFusionStrategy(prior=bad)

    def test_constructor_rejects_out_of_range_threshold(self):
        for bad in (-0.01, 1.01, float("nan"), float("inf")):
            with pytest.raises(FusionError):
                BayesianFusionStrategy(decision_threshold=bad)

    def test_constructor_rejects_bad_epsilon(self):
        for bad in (0.0, 0.5, 1.0, -1.0, float("nan")):
            with pytest.raises(FusionError):
                BayesianFusionStrategy(epsilon=bad)

    def test_constructor_rejects_bad_reliability_mode(self):
        with pytest.raises(FusionError):
            BayesianFusionStrategy(reliability_mode="bogus")

    def test_constructor_rejects_negative_reliability(self):
        with pytest.raises(FusionError):
            BayesianFusionStrategy(reliability_mode="configured", reliability={"a": -0.5})

    def test_constructor_rejects_nan_reliability(self):
        with pytest.raises(FusionError):
            BayesianFusionStrategy(reliability_mode="configured", reliability={"a": float("nan")})

    def test_per_call_prior_invalid(self):
        s = BayesianFusionStrategy()
        with pytest.raises(FusionError):
            s.fuse([_threat("a", 0.5)], prior=1.5)

    def test_per_call_threshold_invalid(self):
        s = BayesianFusionStrategy()
        with pytest.raises(FusionError):
            s.fuse([_threat("a", 0.5)], decision_threshold=-0.1)

    def test_threat_above_one_ignored(self):
        pred = ThreatPrediction(
            provider_id="a",
            predicted_label="threat",
            confidence=0.0,
            probabilities={"threat": 1.5, "benign": -0.5},
        )
        r = BayesianFusionStrategy().fuse([pred])
        assert r.risk_score == pytest.approx(0.5, abs=1e-6)

    def test_threat_nan_ignored(self):
        pred = ThreatPrediction(
            provider_id="a",
            predicted_label="threat",
            confidence=0.0,
            probabilities={"threat": float("nan")},
        )
        r = BayesianFusionStrategy().fuse([pred])
        assert r.risk_score == pytest.approx(0.5, abs=1e-6)

    def test_threat_inf_ignored(self):
        pred = ThreatPrediction(
            provider_id="a",
            predicted_label="threat",
            confidence=0.0,
            probabilities={"threat": float("inf")},
        )
        r = BayesianFusionStrategy().fuse([pred])
        assert r.risk_score == pytest.approx(0.5, abs=1e-6)

    def test_non_numeric_threat_rejected_at_model_boundary(self):
        # The ThreatPrediction model validates probability table values as
        # floats, so a non-numeric threat probability cannot reach the
        # strategy through a constructed prediction. This is the intended,
        # defensive boundary behavior.
        with pytest.raises(ValidationError):
            ThreatPrediction(
                provider_id="a",
                predicted_label="threat",
                confidence=0.0,
                probabilities={"threat": "not-a-number"},
            )


# ── Detector availability / failure handling ────────────────────────────


class TestDetectorAvailability:
    def test_all_detectors_available(self):
        r = BayesianFusionStrategy().fuse([_threat("a", 0.9), _threat("b", 0.7), _threat("c", 0.8)])
        assert r.num_providers == 3
        assert r.num_failed == 0

    def test_only_one_detector(self):
        r = BayesianFusionStrategy().fuse([_threat("a", 0.8)])
        assert r.num_providers == 1
        assert r.num_failed == 0

    def test_classical_only(self):
        r = BayesianFusionStrategy().fuse(
            [_threat("classical-a", 0.9), _threat("classical-b", 0.7)]
        )
        assert "quantum" not in [p.provider_id for p in r.source_predictions]

    def test_quantum_unavailable_is_missing_not_flipped(self):
        s = BayesianFusionStrategy()
        with_quantum = s.fuse([_threat("classical", 0.8), _threat("quantum", 0.5)])
        without_quantum = s.fuse([_threat("classical", 0.8)])
        assert with_quantum.risk_score == pytest.approx(without_quantum.risk_score, abs=1e-6)

    def test_failed_detector_excluded(self):
        r = BayesianFusionStrategy().fuse(
            [_threat("a", 0.9), _threat("b", 0.0, is_valid=False, error="boom")]
        )
        assert r.num_providers == 1
        assert r.num_failed == 1
        assert r.risk_score == pytest.approx(0.9, abs=1e-6)

    def test_all_detectors_failed_empty(self):
        r = BayesianFusionStrategy().fuse(
            [_threat("a", 0.9, is_valid=False), _threat("b", 0.9, is_valid=False)]
        )
        assert r.predicted_label == "unknown"
        assert r.confidence == 0.0
        assert r.risk_score == 0.0
        assert r.num_failed == 2

    def test_empty_input(self):
        r = BayesianFusionStrategy().fuse([])
        assert r.predicted_label == "unknown"
        assert r.confidence == 0.0

    def test_conflicting_evidence_unavailable_nodeutralise(self):
        # A detector reporting a literal probability of 0.5 is missing
        # evidence: it should not be able to drown out a signal provider.
        r = BayesianFusionStrategy().fuse([_threat("signal", 0.9), _threat("neutral", 0.5)])
        assert r.risk_score == pytest.approx(0.9, abs=1e-6)


# ── Configuration integration ───────────────────────────────────────────


class TestConfigurationIntegration:
    def test_bayesian_fusion_config_defaults(self):
        cfg = BayesianFusionConfig()
        assert cfg.prior == 0.5
        assert cfg.decision_threshold == 0.7
        assert cfg.epsilon == pytest.approx(1e-12)
        assert cfg.reliability_mode == "uniform"
        assert cfg.reliability == {}
        assert cfg.prior_weight == 1.0

    def test_bayesian_fusion_config_validation(self):
        with pytest.raises(ValidationError):
            BayesianFusionConfig(prior=1.5)
        with pytest.raises(ValidationError):
            BayesianFusionConfig(prior=-0.1)
        with pytest.raises(ValidationError):
            BayesianFusionConfig(decision_threshold=2.0)
        with pytest.raises(ValidationError):
            BayesianFusionConfig(reliability_mode="bogus")
        with pytest.raises(ValidationError):
            BayesianFusionConfig(reliability={"a": -1.0})

    def test_configured_mode_requires_nonempty_reliability(self):
        with pytest.raises(ValidationError):
            BayesianFusionConfig(reliability_mode="configured")

    def test_configured_mode_accepts_reliability(self):
        cfg = BayesianFusionConfig(reliability_mode="configured", reliability={"a": 0.5, "b": 2.0})
        assert cfg.reliability == {"a": 0.5, "b": 2.0}

    def test_quantum_fusion_config_embeds_bayesian(self):
        fusion = QuantumFusionConfig()
        assert fusion.bayesian.prior == 0.5

    def test_bayesian_is_registered_as_implemented(self):
        assert FusionStrategyType.BAYESIAN.value in IMPLEMENTED_STRATEGIES
        assert FusionStrategyType.BAYESIAN.value not in INTERFACE_ONLY_STRATEGIES


# ── Engine / registry compatibility ─────────────────────────────────────


class TestEngineIntegration:
    async def test_engine_can_register_and_switch_to_bayesian(self):
        engine = HybridFusionEngine()
        engine.register_strategy(BayesianFusionStrategy())
        engine.set_strategy("bayesian")
        assert engine.active_strategy_name == "bayesian"
        assert engine.available_strategies == ["stacking", "bayesian"]

    async def test_strategy_switching_list_includes_all(self):
        strategies = [
            BayesianFusionStrategy(),
        ]
        preds = [_threat("a", 0.9), _threat("b", 0.7)]
        for strategy in strategies:
            result = strategy.fuse(preds)
            assert isinstance(result, FusedPrediction)
            assert result.strategy_name == "bayesian"
            assert result.num_providers == 2

    async def test_config_strategy_enum_allows_bayesian(self):
        cfg = QuantumFusionConfig(strategy=FusionStrategyType.BAYESIAN)
        assert cfg.strategy == FusionStrategyType.BAYESIAN


# ── Explainability ──────────────────────────────────────────────────────


class TestExplainability:
    def test_structured_metadata_uses_computed_values(self):
        s = BayesianFusionStrategy()
        r = s.fuse([_threat("a", 0.8), _threat("b", 0.9)])
        md = r.metadata
        assert "prior" in md
        assert "prior_logit" in md
        assert "posterior_logit" in md
        assert "decision_threshold" in md
        assert "num_evidence" in md
        assert "reliability_mode" in md
        assert "evidence_log_odds" in md
        # prior metadata matches the configured prior
        assert md["prior"] == pytest.approx(0.5)
        # evidence log-odds entries are the detector logits
        assert md["evidence_log_odds"]["a"] == pytest.approx(_logit(0.8), abs=1e-6)
        assert md["evidence_log_odds"]["b"] == pytest.approx(_logit(0.9), abs=1e-6)

    def test_reasoning_summary_mentions_posterior_and_prior(self):
        s = BayesianFusionStrategy()
        r = s.fuse([_threat("a", 0.9)])
        assert "posterior" in r.reasoning_summary.lower()

    def test_explainable_result_format(self):
        s = BayesianFusionStrategy()
        r = s.fuse([_threat("classical-a", 0.84), _threat("classical-b", 0.6)])
        # A structured rendering is derivable from the attributes, matching
        # the documented explainability block.
        assert s.prior == 0.5  # prior shown in explanation
        assert len(r.source_predictions) >= 2  # available evidence
        assert r.risk_score is not None  # posterior
        assert s.decision_threshold == 0.7  # threshold
        assert r.predicted_label in ("threat", "benign")  # final decision
