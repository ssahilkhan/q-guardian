"""ConfidenceFusionStrategy — fusion weighted by provider confidence.

Each provider's prediction is weighted by its own confidence score.
Higher-confidence predictions have more influence on the fused result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from q_guardian.quantum.fusion.strategies.base import FusedPrediction, FusionStrategy

if TYPE_CHECKING:
    from q_guardian.quantum.fusion.prediction import ThreatPrediction


class ConfidenceFusionStrategy(FusionStrategy):
    """Fuse predictions weighted by each provider's confidence.

    Instead of fixed weights, this strategy uses each prediction's own
    confidence score as its vote weight. This naturally favours
    high-confidence predictions.
    """

    @property
    def name(self) -> str:
        return "confidence_fusion"

    @property
    def display_name(self) -> str:
        return "Confidence Fusion"

    @property
    def description(self) -> str:
        return "Fusion weighted by each provider's confidence score"

    def fuse(
        self,
        predictions: list[ThreatPrediction],
        weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> FusedPrediction:
        valid = self.validate_predictions(predictions)
        if not valid:
            return self._empty_result(predictions)

        external_weights = weights or {}
        confidences = np.array([p.confidence for p in valid])
        conf_sum = confidences.sum()
        if conf_sum < 1e-10:
            conf_weights = np.ones(len(valid)) / len(valid)
        else:
            conf_weights = confidences / conf_sum

        final_weights: dict[str, float] = {}
        for i, pred in enumerate(valid):
            ext_w = external_weights.get(pred.provider_id, 1.0)
            final_weights[pred.provider_id] = float(conf_weights[i] * ext_w)

        total = sum(final_weights.values())
        if total > 0:
            final_weights = {k: v / total for k, v in final_weights.items()}

        votes: dict[str, float] = {}
        for pred in valid:
            label = pred.predicted_label
            votes[label] = votes.get(label, 0.0) + final_weights[pred.provider_id]

        best_label = max(votes, key=votes.get)  # type: ignore[arg-type]
        confidence = votes[best_label]

        probabilities: dict[str, float] = {}
        for label, weight in votes.items():
            probabilities[label] = round(weight, 6)

        avg_risk = float(np.mean([p.risk_score for p in valid]))

        return FusedPrediction(
            predicted_label=best_label,
            confidence=round(float(confidence), 6),
            probabilities=probabilities,
            risk_score=round(avg_risk, 6),
            strategy_name="confidence_fusion",
            provider_contributions={k: round(v, 6) for k, v in final_weights.items()},
            source_predictions=valid,
            num_providers=len(valid),
            num_failed=len(predictions) - len(valid),
            reasoning_summary=(
                f"Confidence-weighted: {best_label} = {confidence:.3f} "
                f"(from {len(valid)} providers)"
            ),
        )

    def _empty_result(self, all_predictions: list[ThreatPrediction]) -> FusedPrediction:
        return FusedPrediction(
            predicted_label="unknown",
            confidence=0.0,
            probabilities={},
            risk_score=0.0,
            strategy_name="confidence_fusion",
            source_predictions=all_predictions,
            num_providers=0,
            num_failed=len(all_predictions),
            reasoning_summary="No valid predictions to fuse",
        )
