"""WeightedVotingStrategy — fusion via weighted majority vote.

Each provider votes for a class. Votes are weighted by the provider's
configured weight (default 1.0). The class with the highest weighted
vote count wins.
"""

from __future__ import annotations

from typing import Any

from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.quantum.fusion.strategies.base import FusionStrategy, FusedPrediction


class WeightedVotingStrategy(FusionStrategy):
    """Fuse predictions via weighted majority voting.

    Each valid provider casts a weighted vote for its predicted_label.
    The class with the highest total weight wins.
    """

    @property
    def name(self) -> str:
        return "weighted_voting"

    @property
    def display_name(self) -> str:
        return "Weighted Voting"

    @property
    def description(self) -> str:
        return "Majority voting with configurable per-provider weights"

    def fuse(
        self,
        predictions: list[ThreatPrediction],
        weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> FusedPrediction:
        valid = self.validate_predictions(predictions)
        if not valid:
            return self._empty_result("weighted_voting", predictions)

        weights = weights or {}
        votes: dict[str, float] = {}
        contributions: dict[str, float] = {}
        total_weight = 0.0

        for pred in valid:
            w = weights.get(pred.provider_id, 1.0)
            votes[pred.predicted_label] = votes.get(pred.predicted_label, 0.0) + w
            contributions[pred.provider_id] = w
            total_weight += w

        if total_weight > 0:
            contributions = {k: v / total_weight for k, v in contributions.items()}

        best_label = max(votes, key=votes.get)  # type: ignore[arg-type]
        confidence = votes[best_label] / total_weight if total_weight > 0 else 0.0

        probabilities = {
            label: weight / total_weight if total_weight > 0 else 0.0
            for label, weight in votes.items()
        }

        avg_risk = sum(p.risk_score for p in valid) / len(valid)

        return FusedPrediction(
            predicted_label=best_label,
            confidence=round(confidence, 6),
            probabilities=probabilities,
            risk_score=round(avg_risk, 6),
            strategy_name="weighted_voting",
            provider_contributions=contributions,
            source_predictions=valid,
            num_providers=len(valid),
            num_failed=len(predictions) - len(valid),
            reasoning_summary=f"Weighted vote: {best_label} received {votes[best_label]:.2f}/{total_weight:.2f} total weight",
        )

    def _empty_result(
        self, strategy: str, all_predictions: list[ThreatPrediction]
    ) -> FusedPrediction:
        return FusedPrediction(
            predicted_label="unknown",
            confidence=0.0,
            probabilities={},
            risk_score=0.0,
            strategy_name=strategy,
            source_predictions=all_predictions,
            num_providers=0,
            num_failed=len(all_predictions),
            reasoning_summary="No valid predictions to fuse",
        )
