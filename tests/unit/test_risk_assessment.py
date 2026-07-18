"""Tests for ThreatScorer, TrustEngine, ConfidenceEngine, SeverityEngine."""

import pytest
from q_guardian.risk.assessment.threat_scorer import ThreatScorer
from q_guardian.risk.assessment.trust_engine import TrustEngine
from q_guardian.risk.assessment.confidence_engine import ConfidenceEngine
from q_guardian.risk.assessment.severity_engine import SeverityEngine
from q_guardian.risk.config import ScoringWeights, TrustConfig, ConfidenceConfig, SeverityMapping
from q_guardian.risk.data import NormalizedPrediction
from q_guardian.risk.enums import (
    ThreatLevel, TrustLevel, ConfidenceMethod, Severity,
    TrustAdjustmentReason,
)


def _make_prediction(**kwargs) -> NormalizedPrediction:
    defaults = {"predicted_label": "threat", "confidence": 0.8, "risk_score": 0.7}
    defaults.update(kwargs)
    return NormalizedPrediction(**defaults)


class TestThreatScorer:
    def test_default_weights(self):
        s = ThreatScorer()
        assert s.weights.probability == 0.30

    def test_set_weights(self):
        s = ThreatScorer()
        w = ScoringWeights(probability=0.5, confidence=0.5)
        s.set_weights(w)
        assert s.weights.probability == 0.5

    def test_score_basic(self):
        s = ThreatScorer()
        p = _make_prediction(risk_score=1.0, confidence=1.0)
        ts = s.score(p)
        assert ts.threat_score > 0.0
        assert ts.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)

    def test_score_zero(self):
        s = ThreatScorer()
        p = _make_prediction(risk_score=0.0, confidence=0.0)
        ts = s.score(p, provider_reliability=0.0, model_agreement=0.0, provider_diversity=0.0, severity_value=0.0)
        assert ts.threat_score == 0.0

    def test_score_clamped(self):
        s = ThreatScorer()
        p = _make_prediction(risk_score=1.0, confidence=1.0)
        ts = s.score(p, provider_reliability=1.0, model_agreement=1.0,
                     provider_diversity=1.0, severity_value=1.0)
        assert 0.0 <= ts.threat_score <= 1.0

    def test_score_components(self):
        s = ThreatScorer()
        p = _make_prediction(risk_score=0.5, confidence=0.5)
        ts = s.score(p, provider_reliability=0.5, severity_value=0.5)
        assert ts.probability_component > 0
        assert ts.confidence_component > 0
        assert ts.reliability_component > 0

    def test_score_to_level_none(self):
        assert ThreatScorer._score_to_level(0.0) == ThreatLevel.NONE

    def test_score_to_level_low(self):
        assert ThreatScorer._score_to_level(0.2) == ThreatLevel.LOW

    def test_score_to_level_medium(self):
        assert ThreatScorer._score_to_level(0.5) == ThreatLevel.MEDIUM

    def test_score_to_level_high(self):
        assert ThreatScorer._score_to_level(0.8) == ThreatLevel.HIGH

    def test_score_to_level_critical(self):
        assert ThreatScorer._score_to_level(0.95) == ThreatLevel.CRITICAL

    def test_score_reasoning(self):
        s = ThreatScorer()
        p = _make_prediction()
        ts = s.score(p)
        assert len(ts.reasoning) > 0

    def test_score_batch(self):
        s = ThreatScorer()
        preds = [_make_prediction(risk_score=i * 0.1) for i in range(5)]
        scores = s.score_batch(preds)
        assert len(scores) == 5

    def test_score_batch_agreement(self):
        s = ThreatScorer()
        preds = [_make_prediction(predicted_label="threat") for _ in range(3)]
        scores = s.score_batch(preds)
        assert all(ts.agreement_component > 0 for ts in scores)

    def test_custom_weights(self):
        w = ScoringWeights(probability=1.0, confidence=0.0, reliability=0.0,
                           agreement=0.0, diversity=0.0, severity=0.0)
        s = ThreatScorer(weights=w)
        p = _make_prediction(risk_score=0.8, confidence=0.0)
        ts = s.score(p)
        assert ts.threat_score > 0.5


class TestTrustEngine:
    def test_initial_trust(self):
        te = TrustEngine()
        ts = te.get_trust("provider-1")
        assert ts.trust_score == 0.5
        assert ts.trust_level == TrustLevel.MODERATE

    def test_get_trust_creates_default(self):
        te = TrustEngine()
        ts = te.get_trust("new-provider")
        assert ts.provider_id == "new-provider"
        assert ts.trust_score == 0.5

    def test_adjust_trust_positive(self):
        te = TrustEngine()
        ts = te.adjust_trust("p1", TrustAdjustmentReason.CORRECT_PREDICTION)
        assert ts.trust_score > 0.5

    def test_adjust_trust_negative(self):
        te = TrustEngine()
        ts = te.adjust_trust("p1", TrustAdjustmentReason.INCORRECT_PREDICTION)
        assert ts.trust_score < 0.5

    def test_adjust_trust_false_positive(self):
        te = TrustEngine()
        ts = te.adjust_trust("p1", TrustAdjustmentReason.FALSE_POSITIVE)
        assert ts.trust_score < 0.5

    def test_adjust_trust_false_negative(self):
        te = TrustEngine()
        ts = te.adjust_trust("p1", TrustAdjustmentReason.FALSE_NEGATIVE)
        assert ts.trust_score < 0.5

    def test_trust_clamped_max(self):
        te = TrustEngine(TrustConfig(adjustment_rate=1.0))
        for _ in range(20):
            te.adjust_trust("p1", TrustAdjustmentReason.CORRECT_PREDICTION)
        ts = te.get_trust("p1")
        assert ts.trust_score <= 1.0

    def test_trust_clamped_min(self):
        te = TrustEngine(TrustConfig(adjustment_rate=1.0))
        for _ in range(20):
            te.adjust_trust("p1", TrustAdjustmentReason.INCORRECT_PREDICTION)
        ts = te.get_trust("p1")
        assert ts.trust_score >= 0.0

    def test_record_prediction_correct(self):
        te = TrustEngine()
        ts = te.record_prediction("p1", correct=True)
        assert ts.total_predictions == 1
        assert ts.correct_predictions == 1

    def test_record_prediction_incorrect(self):
        te = TrustEngine()
        ts = te.record_prediction("p1", correct=False, is_false_positive=True)
        assert ts.total_predictions == 1
        assert ts.false_positives == 1

    def test_record_prediction_accuracy(self):
        te = TrustEngine()
        for _ in range(8):
            te.record_prediction("p1", correct=True)
        for _ in range(2):
            te.record_prediction("p1", correct=False)
        ts = te.get_trust("p1")
        assert ts.accuracy == pytest.approx(0.8)

    def test_apply_decay(self):
        te = TrustEngine(TrustConfig(decay_rate=0.1))
        te.get_trust("p1")  # initial 0.5
        updated = te.apply_decay()
        assert updated["p1"].trust_score == pytest.approx(0.4)

    def test_get_all_trust(self):
        te = TrustEngine()
        te.get_trust("p1")
        te.get_trust("p2")
        all_trust = te.get_all_trust()
        assert len(all_trust) == 2

    def test_reset_trust(self):
        te = TrustEngine()
        te.adjust_trust("p1", TrustAdjustmentReason.CORRECT_PREDICTION)
        ts = te.reset_trust("p1")
        assert ts.trust_score == 0.5

    def test_get_provider_reliability(self):
        te = TrustEngine()
        r = te.get_provider_reliability("p1")
        assert r == 0.5

    def test_adjustment_history(self):
        te = TrustEngine()
        te.adjust_trust("p1", TrustAdjustmentReason.CORRECT_PREDICTION)
        te.adjust_trust("p1", TrustAdjustmentReason.INCORRECT_PREDICTION)
        ts = te.get_trust("p1")
        assert len(ts.adjustment_history) == 2

    def test_trust_levels(self):
        te = TrustEngine(TrustConfig(initial_trust=0.0))
        ts = te.get_trust("p1")
        assert ts.trust_level == TrustLevel.UNTRUSTED
        te.adjust_trust("p1", TrustAdjustmentReason.CORRECT_PREDICTION, magnitude=0.5)
        ts = te.get_trust("p1")
        assert ts.trust_level in (TrustLevel.MODERATE, TrustLevel.HIGH)


class TestConfidenceEngine:
    def test_normalize_none(self):
        ce = ConfidenceEngine()
        cs = ce.normalize(0.75)
        assert cs.normalized_confidence == 0.75
        assert cs.method == ConfidenceMethod.NONE

    def test_normalize_temperature(self):
        ce = ConfidenceEngine(ConfidenceConfig(method=ConfidenceMethod.TEMPERATURE, temperature=0.5))
        cs = ce.normalize(0.9)
        assert cs.normalized_confidence != 0.9

    def test_normalize_min_max(self):
        ce = ConfidenceEngine(ConfidenceConfig(method=ConfidenceMethod.MIN_MAX))
        ce.normalize(0.3)
        ce.normalize(0.7)
        cs = ce.normalize(0.5)
        assert 0.0 <= cs.normalized_confidence <= 1.0

    def test_normalize_z_score(self):
        ce = ConfidenceEngine(ConfidenceConfig(method=ConfidenceMethod.Z_SCORE))
        for v in [0.1, 0.3, 0.5, 0.7, 0.9]:
            ce.normalize(v)
        cs = ce.normalize(0.5)
        assert 0.0 <= cs.normalized_confidence <= 1.0

    def test_normalize_clamps(self):
        ce = ConfidenceEngine()
        cs = ce.normalize(1.5)
        assert cs.normalized_confidence <= 1.0
        cs2 = ce.normalize(-0.5)
        assert cs2.normalized_confidence >= 0.0

    def test_aggregate_empty(self):
        ce = ConfidenceEngine()
        cs = ce.aggregate([])
        assert cs.normalized_confidence == 0.0
        assert cs.aggregation_count == 0

    def test_aggregate_basic(self):
        ce = ConfidenceEngine()
        cs = ce.aggregate([0.5, 0.7, 0.9])
        assert cs.aggregation_count == 3
        assert 0.0 <= cs.normalized_confidence <= 1.0

    def test_aggregate_weighted(self):
        ce = ConfidenceEngine()
        cs = ce.aggregate([0.3, 0.9], weights=[0.1, 0.9])
        assert cs.normalized_confidence > 0.3

    def test_aggregate_geometric_mean(self):
        ce = ConfidenceEngine(ConfidenceConfig(aggregation_method="geometric_mean"))
        cs = ce.aggregate([0.5, 0.5])
        assert cs.aggregation_count == 2

    def test_confidence_interval(self):
        ce = ConfidenceEngine()
        ce.normalize(0.5)
        ce.normalize(0.6)
        cs = ce.normalize(0.7)
        assert cs.confidence_interval is not None
        assert cs.confidence_interval[0] <= cs.normalized_confidence
        assert cs.confidence_interval[1] >= cs.normalized_confidence

    def test_reset(self):
        ce = ConfidenceEngine()
        ce.normalize(0.5)
        ce.reset()
        assert ce._running_count == 0


class TestSeverityEngine:
    def test_classify_low(self):
        se = SeverityEngine()
        ss = se.classify(0.05)
        assert ss.severity == Severity.LOW

    def test_classify_medium(self):
        se = SeverityEngine()
        ss = se.classify(0.5)
        assert ss.severity == Severity.MEDIUM

    def test_classify_high(self):
        se = SeverityEngine()
        ss = se.classify(0.8)
        assert ss.severity == Severity.HIGH

    def test_classify_critical(self):
        se = SeverityEngine()
        ss = se.classify(0.95)
        assert ss.severity == Severity.CRITICAL

    def test_classify_clamped(self):
        se = SeverityEngine()
        ss = se.classify(1.5)
        assert ss.severity == Severity.CRITICAL

    def test_classify_negative(self):
        se = SeverityEngine()
        ss = se.classify(-0.5)
        assert ss.severity == Severity.LOW

    def test_custom_mapping(self):
        m = SeverityMapping(critical_threshold=0.5, high_threshold=0.3, medium_threshold=0.1)
        se = SeverityEngine(mapping=m)
        ss = se.classify(0.6)
        assert ss.severity == Severity.CRITICAL

    def test_classify_prediction(self):
        se = SeverityEngine()
        p = NormalizedPrediction(predicted_label="threat", risk_score=0.85)
        ss = se.classify_prediction(p)
        assert ss.severity == Severity.HIGH

    def test_classify_batch(self):
        se = SeverityEngine()
        scores = se.classify_batch([0.1, 0.5, 0.8, 0.95])
        assert len(scores) == 4
        assert scores[0].severity == Severity.LOW
        assert scores[3].severity == Severity.CRITICAL

    def test_set_mapping(self):
        se = SeverityEngine()
        new_m = SeverityMapping(critical_threshold=0.3)
        se.set_mapping(new_m)
        ss = se.classify(0.4)
        assert ss.severity == Severity.CRITICAL

    def test_classify_boundary(self):
        se = SeverityEngine()
        ss = se.classify(0.9)
        assert ss.severity == Severity.CRITICAL
        ss2 = se.classify(0.7)
        assert ss2.severity == Severity.HIGH
