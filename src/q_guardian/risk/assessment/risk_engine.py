"""RiskAssessmentEngine — the top-level orchestrator for risk assessment.

Consumes NormalizedPrediction and produces a complete RiskAssessment
with scoring, trust, confidence, and severity details.
"""

from __future__ import annotations

import structlog

from q_guardian.risk.assessment.confidence_engine import ConfidenceEngine
from q_guardian.risk.assessment.severity_engine import SeverityEngine
from q_guardian.risk.assessment.threat_scorer import ThreatScorer
from q_guardian.risk.assessment.trust_engine import TrustEngine
from q_guardian.risk.config import RiskConfig
from q_guardian.risk.data import NormalizedPrediction, RiskAssessment
from q_guardian.risk.enums import RiskLevel

logger = structlog.get_logger("risk.engine")


class RiskAssessmentEngine:
    """Orchestrates the full risk assessment pipeline.

    Pipeline:
      1. ThreatScorer computes composite threat score
      2. TrustEngine provides provider reliability
      3. ConfidenceEngine normalizes confidence
      4. SeverityEngine maps score to severity
      5. RiskAssessment is assembled with all components
    """

    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()
        self._threat_scorer = ThreatScorer(self._config.scoring_weights)
        self._trust_engine = TrustEngine(self._config.trust)
        self._confidence_engine = ConfidenceEngine(self._config.confidence)
        self._severity_engine = SeverityEngine(self._config.severity_mapping)
        self._assessment_count = 0

    @property
    def config(self) -> RiskConfig:
        return self._config

    @property
    def threat_scorer(self) -> ThreatScorer:
        return self._threat_scorer

    @property
    def trust_engine(self) -> TrustEngine:
        return self._trust_engine

    @property
    def confidence_engine(self) -> ConfidenceEngine:
        return self._confidence_engine

    @property
    def severity_engine(self) -> SeverityEngine:
        return self._severity_engine

    @property
    def assessment_count(self) -> int:
        return self._assessment_count

    def assess(self, prediction: NormalizedPrediction) -> RiskAssessment:
        """Perform a full risk assessment on a single prediction.

        Args:
            prediction: The normalized prediction to assess.

        Returns:
            Complete RiskAssessment.
        """
        self._assessment_count += 1
        reasoning: list[str] = []

        reliability = self._trust_engine.get_provider_reliability(prediction.provider_id)
        reasoning.append(f"Provider reliability: {reliability:.4f}")

        threat_score = self._threat_scorer.score(
            prediction,
            provider_reliability=reliability,
            severity_value=prediction.risk_score,
        )
        reasoning.append(f"Threat score: {threat_score.threat_score:.4f}")

        confidence = self._confidence_engine.normalize(prediction.confidence)
        reasoning.append(f"Confidence: {confidence.normalized_confidence:.4f} (raw: {confidence.raw_confidence:.4f})")

        severity = self._severity_engine.classify(threat_score.threat_score)
        reasoning.append(f"Severity: {severity.severity.value}")

        risk_score = self._compute_risk_score(threat_score.threat_score, confidence.normalized_confidence)
        risk_level = self._score_to_risk_level(risk_score)
        reasoning.append(f"Final risk score: {risk_score:.4f} -> {risk_level.value}")

        trust_score = self._trust_engine.get_trust(prediction.provider_id)

        assessment = RiskAssessment(
            prediction_id=prediction.prediction_id,
            risk_score=risk_score,
            risk_level=risk_level,
            threat_score=threat_score,
            severity=severity,
            confidence=confidence,
            trust_scores={prediction.provider_id: trust_score},
            reasoning=reasoning,
            contributing_sources=[prediction.provider_id],
        )

        logger.info(
            "risk_assessment_completed",
            assessment_id=assessment.assessment_id,
            risk_score=risk_score,
            risk_level=risk_level.value,
            severity=severity.severity.value,
        )

        return assessment

    def assess_batch(self, predictions: list[NormalizedPrediction]) -> list[RiskAssessment]:
        """Assess a batch of predictions.

        Args:
            predictions: List of normalized predictions.

        Returns:
            List of risk assessments.
        """
        return [self.assess(p) for p in predictions]

    def _compute_risk_score(self, threat_score: float, confidence: float) -> float:
        """Combine threat score and confidence into final risk score."""
        risk = threat_score * 0.7 + confidence * 0.3
        risk = max(self._config.min_risk_score, min(self._config.max_risk_score, risk))
        return round(risk, 6)

    @staticmethod
    def _score_to_risk_level(score: float) -> RiskLevel:
        """Map numeric risk score to RiskLevel."""
        if score >= 0.9:
            return RiskLevel.CRITICAL
        elif score >= 0.7:
            return RiskLevel.SEVERE
        elif score >= 0.5:
            return RiskLevel.HIGH
        elif score >= 0.3:
            return RiskLevel.MODERATE
        elif score >= 0.1:
            return RiskLevel.LOW
        return RiskLevel.MINIMAL
