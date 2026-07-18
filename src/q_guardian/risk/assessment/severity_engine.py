"""SeverityEngine — maps risk scores to severity levels.

Supports configurable threshold mappings and custom severity logic.
"""

from __future__ import annotations

import structlog

from q_guardian.risk.config import SeverityMapping
from q_guardian.risk.data import NormalizedPrediction, SeverityScore
from q_guardian.risk.enums import Severity

logger = structlog.get_logger("risk.severity_engine")


class SeverityEngine:
    """Maps numeric risk scores to severity classifications.

    Uses configurable thresholds to map a score in [0, 1] to one of:
    LOW, MEDIUM, HIGH, CRITICAL.
    """

    def __init__(self, mapping: SeverityMapping | None = None) -> None:
        self._mapping = mapping or SeverityMapping()

    @property
    def mapping(self) -> SeverityMapping:
        return self._mapping

    def set_mapping(self, mapping: SeverityMapping) -> None:
        self._mapping = mapping

    def classify(self, risk_score: float) -> SeverityScore:
        """Classify a risk score into a severity level.

        Args:
            risk_score: Risk score in [0, 1].

        Returns:
            SeverityScore with classified severity.
        """
        m = self._mapping
        clamped = max(0.0, min(1.0, risk_score))

        if clamped >= m.critical_threshold:
            severity = Severity.CRITICAL
            reasoning = f"Score {clamped:.4f} >= critical threshold {m.critical_threshold}"
        elif clamped >= m.high_threshold:
            severity = Severity.HIGH
            reasoning = f"Score {clamped:.4f} >= high threshold {m.high_threshold}"
        elif clamped >= m.medium_threshold:
            severity = Severity.MEDIUM
            reasoning = f"Score {clamped:.4f} >= medium threshold {m.medium_threshold}"
        elif clamped >= m.low_threshold:
            severity = Severity.LOW
            reasoning = f"Score {clamped:.4f} >= low threshold {m.low_threshold}"
        else:
            severity = Severity.LOW
            reasoning = f"Score {clamped:.4f} below all thresholds, defaulting to LOW"

        logger.debug(
            "severity_classified",
            risk_score=clamped,
            severity=severity.value,
        )

        return SeverityScore(
            severity=severity,
            score=clamped,
            reasoning=reasoning,
            mapping_used="default",
        )

    def classify_prediction(self, prediction: NormalizedPrediction) -> SeverityScore:
        """Classify a prediction's risk score into severity.

        Args:
            prediction: The prediction to classify.

        Returns:
            SeverityScore.
        """
        return self.classify(prediction.risk_score)

    def classify_batch(self, risk_scores: list[float]) -> list[SeverityScore]:
        """Classify a batch of risk scores."""
        return [self.classify(s) for s in risk_scores]
