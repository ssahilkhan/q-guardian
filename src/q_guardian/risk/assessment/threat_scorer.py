"""ThreatScorer — calculates composite threat scores.

Consumes NormalizedPrediction and produces ThreatScore. Uses configurable
weighting across probability, confidence, reliability, agreement, diversity,
and severity components.
"""

from __future__ import annotations

import structlog

from q_guardian.risk.config import ScoringWeights
from q_guardian.risk.data import NormalizedPrediction, ThreatScore
from q_guardian.risk.enums import ThreatLevel

logger = structlog.get_logger("risk.threat_scorer")


class ThreatScorer:
    """Calculates composite threat scores from normalized predictions.

    Scoring formula:
        threat_score = w_prob * probability + w_conf * confidence
                     + w_rel * reliability + w_agr * agreement
                     + w_div * diversity + w_sev * severity

    All weights are configurable via ScoringWeights.
    """

    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self._weights = weights or ScoringWeights()

    @property
    def weights(self) -> ScoringWeights:
        return self._weights

    def set_weights(self, weights: ScoringWeights) -> None:
        self._weights = weights

    def score(
        self,
        prediction: NormalizedPrediction,
        provider_reliability: float = 0.5,
        model_agreement: float = 1.0,
        provider_diversity: float = 1.0,
        severity_value: float = 0.0,
    ) -> ThreatScore:
        """Calculate the composite threat score for a single prediction.

        Args:
            prediction: The normalized prediction to score.
            provider_reliability: Provider's historical reliability 0-1.
            model_agreement: Agreement among models 0-1 (1 = full agreement).
            provider_diversity: Diversity of provider types 0-1.
            severity_value: Pre-computed severity value 0-1.

        Returns:
            ThreatScore with detailed component breakdown.
        """
        w = self._weights

        prob_component = prediction.risk_score * w.probability
        conf_component = prediction.confidence * w.confidence
        rel_component = provider_reliability * w.reliability
        agr_component = model_agreement * w.agreement
        div_component = provider_diversity * w.diversity
        sev_component = severity_value * w.severity

        raw_score = (
            prob_component
            + conf_component
            + rel_component
            + agr_component
            + div_component
            + sev_component
        )

        clamped = max(0.0, min(1.0, raw_score))
        threat_level = self._score_to_level(clamped)

        reasoning = [
            f"Probability component: {prob_component:.4f} (weight={w.probability})",
            f"Confidence component: {conf_component:.4f} (weight={w.confidence})",
            f"Reliability component: {rel_component:.4f} (weight={w.reliability})",
            f"Agreement component: {agr_component:.4f} (weight={w.agreement})",
            f"Diversity component: {div_component:.4f} (weight={w.diversity})",
            f"Severity component: {sev_component:.4f} (weight={w.severity})",
            f"Composite score: {clamped:.4f} -> {threat_level.value}",
        ]

        logger.debug(
            "threat_scored",
            prediction_id=prediction.prediction_id,
            score=clamped,
            threat_level=threat_level.value,
        )

        return ThreatScore(
            threat_score=clamped,
            probability_component=prob_component,
            confidence_component=conf_component,
            reliability_component=rel_component,
            agreement_component=agr_component,
            diversity_component=div_component,
            severity_component=sev_component,
            threat_level=threat_level,
            reasoning=reasoning,
        )

    def score_batch(
        self,
        predictions: list[NormalizedPrediction],
        provider_reliabilities: dict[str, float] | None = None,
        severity_value: float = 0.0,
    ) -> list[ThreatScore]:
        """Score a batch of predictions.

        Computes model agreement and provider diversity from the batch
        automatically.
        """
        provider_reliabilities = provider_reliabilities or {}

        labels = [p.predicted_label for p in predictions]
        unique_labels = set(labels)
        agreement = 1.0 - (len(unique_labels) - 1) / max(len(unique_labels), 1) if labels else 0.0

        providers = {p.provider_id for p in predictions}
        diversity = min(len(providers) / 3.0, 1.0)

        return [
            self.score(
                pred,
                provider_reliability=provider_reliabilities.get(pred.provider_id, 0.5),
                model_agreement=agreement,
                provider_diversity=diversity,
                severity_value=severity_value,
            )
            for pred in predictions
        ]

    @staticmethod
    def _score_to_level(score: float) -> ThreatLevel:
        """Map a numeric score to a ThreatLevel."""
        if score >= 0.9:
            return ThreatLevel.CRITICAL
        elif score >= 0.7:
            return ThreatLevel.HIGH
        elif score >= 0.4:
            return ThreatLevel.MEDIUM
        elif score >= 0.1:
            return ThreatLevel.LOW
        return ThreatLevel.NONE
