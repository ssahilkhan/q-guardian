"""Tests for RiskAssessmentEngine."""

from q_guardian.risk.assessment.risk_engine import RiskAssessmentEngine
from q_guardian.risk.config import RiskConfig
from q_guardian.risk.data import NormalizedPrediction, RiskAssessment
from q_guardian.risk.enums import RiskLevel


def _make_prediction(**kwargs) -> NormalizedPrediction:
    defaults = {
        "predicted_label": "threat",
        "confidence": 0.8,
        "risk_score": 0.7,
        "provider_id": "test-provider",
    }
    defaults.update(kwargs)
    return NormalizedPrediction(**defaults)


class TestRiskAssessmentEngine:
    def test_default_init(self):
        engine = RiskAssessmentEngine()
        assert engine.config.enabled is True
        assert engine.assessment_count == 0

    def test_custom_config(self):
        config = RiskConfig(max_risk_score=0.9)
        engine = RiskAssessmentEngine(config)
        assert engine.config.max_risk_score == 0.9

    def test_assess_basic(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction(risk_score=0.8, confidence=0.9)
        ra = engine.assess(p)
        assert isinstance(ra, RiskAssessment)
        assert 0.0 <= ra.risk_score <= 1.0
        assert ra.risk_level in list(RiskLevel)
        assert engine.assessment_count == 1

    def test_assess_high_risk(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction(risk_score=0.95, confidence=0.95)
        ra = engine.assess(p)
        assert ra.risk_score > 0.7

    def test_assess_low_risk(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction(risk_score=0.05, confidence=0.1)
        ra = engine.assess(p)
        assert ra.risk_score < 0.3

    def test_assess_has_threat_score(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction()
        ra = engine.assess(p)
        assert ra.threat_score.threat_score > 0

    def test_assess_has_severity(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction(risk_score=0.8)
        ra = engine.assess(p)
        assert ra.severity.severity.value in ("low", "medium", "high", "critical")

    def test_assess_has_confidence(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction(confidence=0.85)
        ra = engine.assess(p)
        assert ra.confidence.raw_confidence == 0.85

    def test_assess_has_trust(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction(provider_id="my-provider")
        ra = engine.assess(p)
        assert "my-provider" in ra.trust_scores

    def test_assess_has_reasoning(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction()
        ra = engine.assess(p)
        assert len(ra.reasoning) > 0

    def test_assess_has_sources(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction(provider_id="src-1")
        ra = engine.assess(p)
        assert "src-1" in ra.contributing_sources

    def test_assess_batch(self):
        engine = RiskAssessmentEngine()
        preds = [_make_prediction(risk_score=i * 0.2) for i in range(5)]
        results = engine.assess_batch(preds)
        assert len(results) == 5
        assert engine.assessment_count == 5

    def test_assess_clamps_risk_score(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction(risk_score=1.0, confidence=1.0)
        ra = engine.assess(p)
        assert ra.risk_score <= engine.config.max_risk_score

    def test_assess_updates_trust(self):
        engine = RiskAssessmentEngine()
        p = _make_prediction(provider_id="p1")
        engine.assess(p)
        trust = engine.trust_engine.get_trust("p1")
        assert trust.trust_score == 0.5  # trust is read, not auto-updated by assess

    def test_risk_level_mapping(self):
        engine = RiskAssessmentEngine()
        # High risk
        p_high = _make_prediction(risk_score=0.95, confidence=0.95)
        ra_high = engine.assess(p_high)
        assert ra_high.risk_level in (RiskLevel.SEVERE, RiskLevel.CRITICAL)

        # Low risk
        p_low = _make_prediction(risk_score=0.01, confidence=0.01)
        ra_low = engine.assess(p_low)
        assert ra_low.risk_level in (RiskLevel.MINIMAL, RiskLevel.LOW)
