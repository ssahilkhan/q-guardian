"""AdaptiveFusionStrategy — dynamically adjusts weights based on recent accuracy.

Monitors per-provider accuracy over a sliding window and adjusts
contribution weights accordingly. Providers that have been more
accurate recently get higher weight.
"""

from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np
import structlog

from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.quantum.fusion.strategies.base import FusionStrategy, FusedPrediction

logger = structlog.get_logger("quantum.fusion.adaptive")


class AdaptiveFusionStrategy(FusionStrategy):
    """Adaptive fusion that learns provider reliability from outcomes.

    Maintains a sliding window of recent predictions and their
    correctness (when ground truth is available). Adjusts weights
    so that more reliable providers contribute more.
    """

    @property
    def name(self) -> str:
        return "adaptive"

    @property
    def display_name(self) -> str:
        return "Adaptive Fusion"

    @property
    def description(self) -> str:
        return "Dynamically adjusts weights based on recent provider accuracy"

    def __init__(self, window_size: int = 100, decay: float = 0.95) -> None:
        self._window_size = window_size
        self._decay = decay
        self._provider_history: dict[str, deque[bool]] = {}
        self._provider_weights: dict[str, float] = {}
        self._base_weight = 1.0

    @property
    def window_size(self) -> int:
        return self._window_size

    def fuse(
        self,
        predictions: list[ThreatPrediction],
        weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> FusedPrediction:
        valid = self.validate_predictions(predictions)
        if not valid:
            return self._empty_result(predictions)

        adaptive_weights = self._compute_adaptive_weights(valid)
        external_weights = weights or {}

        combined: dict[str, float] = {}
        for pred in valid:
            adapt_w = adaptive_weights.get(pred.provider_id, self._base_weight)
            ext_w = external_weights.get(pred.provider_id, 1.0)
            combined[pred.provider_id] = adapt_w * ext_w

        total = sum(combined.values())
        if total > 0:
            combined = {k: v / total for k, v in combined.items()}

        votes: dict[str, float] = {}
        for pred in valid:
            label = pred.predicted_label
            votes[label] = votes.get(label, 0.0) + combined[pred.provider_id]

        best_label = max(votes, key=votes.get)  # type: ignore[arg-type]
        confidence = votes[best_label]

        probabilities = {k: round(v, 6) for k, v in votes.items()}
        avg_risk = float(np.mean([p.risk_score for p in valid]))

        return FusedPrediction(
            predicted_label=best_label,
            confidence=round(float(confidence), 6),
            probabilities=probabilities,
            risk_score=round(avg_risk, 6),
            strategy_name="adaptive",
            provider_contributions={k: round(v, 6) for k, v in combined.items()},
            source_predictions=valid,
            num_providers=len(valid),
            num_failed=len(predictions) - len(valid),
            reasoning_summary=(
                f"Adaptive: {best_label} = {confidence:.3f} "
                f"(window={self._window_size})"
            ),
            metadata={
                "window_size": self._window_size,
                "decay": self._decay,
                "provider_accuracies": {
                    pid: self._get_accuracy(pid)
                    for pid in self._provider_history
                },
            },
        )

    def update_outcome(self, provider_id: str, prediction_label: str, ground_truth: str) -> None:
        """Update provider history with a ground-truth outcome.

        Call this after ground truth becomes available to adapt future weights.
        """
        if provider_id not in self._provider_history:
            self._provider_history[provider_id] = deque(maxlen=self._window_size)

        correct = prediction_label == ground_truth
        self._provider_history[provider_id].append(correct)

        if provider_id not in self._provider_weights:
            self._provider_weights[provider_id] = self._base_weight

        acc = self._get_accuracy(provider_id)
        self._provider_weights[provider_id] = max(0.1, acc)

        logger.debug(
            "adaptive_weight_updated",
            provider_id=provider_id,
            correct=correct,
            accuracy=acc,
        )

    def _compute_adaptive_weights(self, predictions: list[ThreatPrediction]) -> dict[str, float]:
        """Get adaptive weights for current providers."""
        result: dict[str, float] = {}
        for pred in predictions:
            if pred.provider_id in self._provider_weights:
                result[pred.provider_id] = self._provider_weights[pred.provider_id]
            else:
                result[pred.provider_id] = self._base_weight
        return result

    def _get_accuracy(self, provider_id: str) -> float:
        """Get rolling accuracy for a provider."""
        history = self._provider_history.get(provider_id)
        if not history or len(history) == 0:
            return 0.5
        return sum(history) / len(history)

    def _empty_result(self, all_predictions: list[ThreatPrediction]) -> FusedPrediction:
        return FusedPrediction(
            predicted_label="unknown",
            confidence=0.0,
            probabilities={},
            risk_score=0.0,
            strategy_name="adaptive",
            source_predictions=all_predictions,
            num_providers=0,
            num_failed=len(all_predictions),
            reasoning_summary="No valid predictions to fuse",
        )
