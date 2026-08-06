"""WeightedVotingStrategy — fusion via weighted voting.

Each provider votes for a class. Votes are weighted by the provider's
configured weight (default 1.0). Probabilities are combined as a
weighted average across providers (soft voting) so that near-threshold
predictions keep their continuous signal instead of being reduced to a
hard one-vote-per-provider count.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from q_guardian.quantum.fusion.strategies.base import FusedPrediction, FusionStrategy

if TYPE_CHECKING:
    from q_guardian.quantum.fusion.prediction import ThreatPrediction


class WeightedVotingStrategy(FusionStrategy):
    """Fuse predictions via weighted voting.

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
        return "Weighted voting over provider probabilities (soft vote)"

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
        # The class set must be the union of every provider's probability
        # table, not just the labels they predicted. Otherwise, when all
        # providers happen to predict the same label, the minority class
        # probabilities (e.g. 40% threat from each provider) are dropped and
        # the fused risk reads zero even though the evidence is split.
        classes: set[str] = set()
        for pred in valid:
            probs = pred.probabilities or {}
            if probs:
                classes.update(probs.keys())
            else:
                classes.add(pred.predicted_label)
        class_names = sorted(classes)
        weighted_prob: dict[str, float] = dict.fromkeys(class_names, 0.0)
        contributions: dict[str, float] = {}
        total_weight = 0.0

        for pred in valid:
            w = weights.get(pred.provider_id, 1.0)
            total_weight += w
            contributions[pred.provider_id] = w
            probs = pred.probabilities or {}
            if probs:
                for c in class_names:
                    weighted_prob[c] += w * float(probs.get(c, 0.0))
            else:
                # No probability table: place the provider's confidence on
                # its label and spread the remainder across the others.
                weighted_prob[pred.predicted_label] += w * float(pred.confidence)
                if len(classes) > 1:
                    rest = (1.0 - float(pred.confidence)) / (len(classes) - 1)
                    for c in classes:
                        if c != pred.predicted_label:
                            weighted_prob[c] += w * rest

        if total_weight > 0:
            weighted_prob = {k: v / total_weight for k, v in weighted_prob.items()}
            contributions = {k: v / total_weight for k, v in contributions.items()}

        best_label = max(weighted_prob, key=weighted_prob.get)  # type: ignore[arg-type]
        confidence = weighted_prob[best_label]

        # The fused risk is the threat probability from the weighted soft
        # vote, NOT the average of provider risk scores (averaging lets a
        # noisy/neutral provider inflate every prompt's risk).
        threat_prob = weighted_prob.get("threat", 0.0)

        return FusedPrediction(
            predicted_label=best_label,
            confidence=round(confidence, 6),
            probabilities=weighted_prob,
            risk_score=round(threat_prob, 6),
            strategy_name="weighted_voting",
            provider_contributions=contributions,
            source_predictions=valid,
            num_providers=len(valid),
            num_failed=len(predictions) - len(valid),
            reasoning_summary=(
                f"Weighted soft-vote: {best_label} wins at "
                f"{confidence:.2f} (threat probability {threat_prob:.2f})"
            ),
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
