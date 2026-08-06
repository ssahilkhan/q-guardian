"""TrustEngine — tracks and adjusts provider trust over time.

Maintains per-provider trust scores based on prediction accuracy,
failure rates, and configurable adjustment parameters.
"""

from __future__ import annotations

import structlog

from q_guardian.risk.config import TrustConfig
from q_guardian.risk.data import TrustScore
from q_guardian.risk.enums import TrustAdjustmentReason, TrustLevel

logger = structlog.get_logger("risk.trust_engine")


class TrustEngine:
    """Tracks and dynamically adjusts trust for prediction providers.

    Trust is a float in [0, 1] that represents the framework's
    confidence in a provider's predictions. Trust increases with
    correct predictions and decreases with errors, timeouts, and
    manual overrides.
    """

    def __init__(self, config: TrustConfig | None = None) -> None:
        self._config = config or TrustConfig()
        self._scores: dict[str, TrustScore] = {}

    @property
    def config(self) -> TrustConfig:
        return self._config

    def get_trust(self, provider_id: str) -> TrustScore:
        """Get the current trust score for a provider.

        Creates a new TrustScore with initial trust if the provider
        has not been seen before.
        """
        if provider_id not in self._scores:
            self._scores[provider_id] = TrustScore(
                provider_id=provider_id,
                trust_score=self._config.initial_trust,
                trust_level=self._score_to_level(self._config.initial_trust),
            )
        return self._scores[provider_id]

    def adjust_trust(
        self,
        provider_id: str,
        reason: TrustAdjustmentReason,
        magnitude: float = 0.0,
    ) -> TrustScore:
        """Adjust a provider's trust score.

        Args:
            provider_id: The provider to adjust.
            reason: Why the adjustment is being made.
            magnitude: Optional magnitude override (0 uses default adjustment_rate).

        Returns:
            Updated TrustScore.
        """
        score = self.get_trust(provider_id)
        delta = self._compute_delta(reason, magnitude, score)

        new_trust = max(
            self._config.min_trust,
            min(self._config.max_trust, score.trust_score + delta),
        )

        record = {
            "reason": reason.value,
            "delta": round(delta, 4),
            "previous": round(score.trust_score, 4),
            "new": round(new_trust, 4),
        }

        score.trust_score = new_trust
        score.trust_level = self._score_to_level(new_trust)
        score.adjustment_history.append(record)
        if len(score.adjustment_history) > self._config.history_window:
            score.adjustment_history = score.adjustment_history[-self._config.history_window :]

        logger.debug(
            "trust_adjusted",
            provider_id=provider_id,
            reason=reason.value,
            delta=delta,
            new_trust=new_trust,
        )

        return score

    def record_prediction(
        self,
        provider_id: str,
        correct: bool,
        is_false_positive: bool = False,
        is_false_negative: bool = False,
    ) -> TrustScore:
        """Record a prediction outcome and adjust trust accordingly.

        Args:
            provider_id: The provider that made the prediction.
            correct: Whether the prediction was correct.
            is_false_positive: Whether this was a false positive.
            is_false_negative: Whether this was a false negative.

        Returns:
            Updated TrustScore.
        """
        score = self.get_trust(provider_id)
        score.total_predictions += 1

        if correct:
            score.correct_predictions += 1
            self.adjust_trust(provider_id, TrustAdjustmentReason.CORRECT_PREDICTION)
        else:
            score.incorrect_predictions += 1
            if is_false_positive:
                score.false_positives += 1
                self.adjust_trust(provider_id, TrustAdjustmentReason.FALSE_POSITIVE)
            elif is_false_negative:
                score.false_negatives += 1
                self.adjust_trust(provider_id, TrustAdjustmentReason.FALSE_NEGATIVE)
            else:
                self.adjust_trust(provider_id, TrustAdjustmentReason.INCORRECT_PREDICTION)

        if score.total_predictions > 0:
            score.accuracy = score.correct_predictions / score.total_predictions

        return score

    def apply_decay(self) -> dict[str, TrustScore]:
        """Apply time-based decay to all provider trust scores.

        Returns:
            Dict of provider_id -> updated TrustScore.
        """
        updated: dict[str, TrustScore] = {}
        for pid, score in self._scores.items():
            old_trust = score.trust_score
            new_trust = max(
                self._config.min_trust,
                old_trust - self._config.decay_rate,
            )
            score.trust_score = new_trust
            score.trust_level = self._score_to_level(new_trust)
            updated[pid] = score
        return updated

    def get_all_trust(self) -> dict[str, TrustScore]:
        """Get trust scores for all known providers."""
        return dict(self._scores)

    def reset_trust(self, provider_id: str) -> TrustScore:
        """Reset a provider's trust to the initial value."""
        score = TrustScore(
            provider_id=provider_id,
            trust_score=self._config.initial_trust,
            trust_level=self._score_to_level(self._config.initial_trust),
        )
        self._scores[provider_id] = score
        return score

    def get_provider_reliability(self, provider_id: str) -> float:
        """Get the trust score as a simple reliability float."""
        return self.get_trust(provider_id).trust_score

    def _compute_delta(
        self,
        reason: TrustAdjustmentReason,
        magnitude: float,
        score: TrustScore,
    ) -> float:
        """Compute the trust delta for a given reason."""
        rate = self._config.adjustment_rate
        if magnitude > 0:
            base = magnitude
        elif reason == TrustAdjustmentReason.CORRECT_PREDICTION:
            base = rate
        elif reason == TrustAdjustmentReason.INCORRECT_PREDICTION:
            base = -rate
        elif reason == TrustAdjustmentReason.FALSE_POSITIVE:
            base = -rate * 1.2
        elif reason == TrustAdjustmentReason.FALSE_NEGATIVE:
            base = -rate * 1.5
        elif reason == TrustAdjustmentReason.TIMEOUT:
            base = -rate * 0.5
        elif reason == TrustAdjustmentReason.MANUAL_OVERRIDE:
            base = magnitude if magnitude != 0 else rate
        elif reason == TrustAdjustmentReason.DECAY:
            base = -self._config.decay_rate
        else:
            base = 0.0
        return base

    @staticmethod
    def _score_to_level(trust: float) -> TrustLevel:
        """Map numeric trust to TrustLevel."""
        if trust >= 0.9:
            return TrustLevel.VERIFIED
        elif trust >= 0.7:
            return TrustLevel.HIGH
        elif trust >= 0.4:
            return TrustLevel.MODERATE
        elif trust >= 0.2:
            return TrustLevel.LOW
        return TrustLevel.UNTRUSTED
