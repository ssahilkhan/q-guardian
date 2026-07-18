"""StackingFusionStrategy — meta-learner fusion (default strategy).

Uses provider predictions as features for a simple logistic meta-learner.
When no training data is available, falls back to confidence-weighted
averaging. This is the recommended default strategy.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog

from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.quantum.fusion.strategies.base import FusionStrategy, FusedPrediction

logger = structlog.get_logger("quantum.fusion.stacking")


class StackingFusionStrategy(FusionStrategy):
    """Stacking fusion with a logistic regression meta-learner.

    During training, collects (provider_predictions, ground_truth) pairs
    and fits a simple logistic regression. During inference, passes
    provider outputs through the meta-learner.

    Falls back to confidence-weighted averaging when untrained.
    """

    @property
    def name(self) -> str:
        return "stacking"

    @property
    def display_name(self) -> str:
        return "Stacking Fusion"

    @property
    def description(self) -> str:
        return "Meta-learner fusion with logistic regression (default strategy)"

    def __init__(self, learning_rate: float = 0.01, epochs: int = 100) -> None:
        self._learning_rate = learning_rate
        self._epochs = epochs
        self._is_trained = False
        self._weights: np.ndarray | None = None
        self._bias: float = 0.0
        self._provider_order: list[str] = []
        self._label_to_idx: dict[str, int] = {}
        self._idx_to_label: dict[int, str] = {}
        self._training_data_X: list[list[float]] = []
        self._training_data_y: list[int] = []

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def fuse(
        self,
        predictions: list[ThreatPrediction],
        weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> FusedPrediction:
        all_predictions = list(predictions)
        valid = self.validate_predictions(predictions)
        num_failed = len(all_predictions) - len(valid)

        if self._is_trained and self._weights is not None:
            return self._predict_with_metalearner(valid, num_failed)

        return self._confidence_weighted_fallback(valid, weights, num_failed)

    def train_metalearner(
        self,
        training_samples: list[list[ThreatPrediction]],
        ground_truth_labels: list[str],
    ) -> dict[str, Any]:
        """Train the stacking meta-learner.

        Args:
            training_samples: List of prediction batches (each batch = predictions from all providers for one input).
            ground_truth_labels: True label for each sample.

        Returns:
            Training metrics.
        """
        self._provider_order = self._extract_provider_order(training_samples)
        self._build_label_map(ground_truth_labels)

        X = self._vectorize_batch(training_samples)
        y = np.array([self._label_to_idx.get(label, 0) for label in ground_truth_labels])

        n_classes = max(len(self._label_to_idx), 2)
        n_features = len(self._provider_order)

        if n_classes == 2:
            self._weights = np.zeros(n_features)
            self._bias = 0.0
            self._fit_binary(X, y)
        else:
            self._weights = np.zeros((n_classes, n_features))
            self._bias = 0.0
            self._fit_multiclass(X, y, n_classes)

        self._is_trained = True
        self._training_data_X = X.tolist()
        self._training_data_y = y.tolist()

        logger.info(
            "stacking_trained",
            samples=len(training_samples),
            providers=len(self._provider_order),
            n_classes=n_classes,
        )

        return {
            "samples": len(training_samples),
            "providers": len(self._provider_order),
            "n_classes": n_classes,
            "epochs": self._epochs,
        }

    def _fit_binary(self, X: np.ndarray, y: np.ndarray) -> None:
        """Simple logistic regression for binary classification."""
        for _ in range(self._epochs):
            logits = X @ self._weights + self._bias
            probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -10, 10)))
            gradient_w = X.T @ (probs - y) / len(y)
            gradient_b = float(np.mean(probs - y))
            self._weights -= self._learning_rate * gradient_w
            self._bias -= self._learning_rate * gradient_b

    def _fit_multiclass(self, X: np.ndarray, y: np.ndarray, n_classes: int) -> None:
        """Simple softmax regression for multi-class."""
        n_features = X.shape[1]
        self._weights = np.zeros((n_classes, n_features))
        self._bias = np.zeros(n_classes)

        for _ in range(self._epochs):
            logits = X @ self._weights.T + self._bias
            logits -= logits.max(axis=1, keepdims=True)
            exp_logits = np.exp(logits)
            probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)

            y_onehot = np.zeros_like(probs)
            for i, label in enumerate(y):
                if label < n_classes:
                    y_onehot[i, label] = 1.0

            gradient_w = (probs - y_onehot).T @ X / len(y)
            gradient_b = np.mean(probs - y_onehot, axis=0)
            self._weights -= self._learning_rate * gradient_w
            self._bias -= self._learning_rate * gradient_b

    def _predict_with_metalearner(
        self, predictions: list[ThreatPrediction], num_failed: int = 0
    ) -> FusedPrediction:
        """Use trained meta-learner to fuse."""
        x = self._vectorize_single(predictions)
        n_classes = len(self._label_to_idx) if self._label_to_idx else 2

        if self._weights is not None and self._weights.ndim == 1:
            logit = float(x @ self._weights + self._bias)
            prob = 1.0 / (1.0 + np.exp(-np.clip(logit, -10, 10)))
            class_probs = {
                self._idx_to_label.get(0, "benign"): round(1 - prob, 6),
                self._idx_to_label.get(1, "threat"): round(prob, 6),
            }
            best_label = max(class_probs, key=class_probs.get)  # type: ignore[arg-type]
            confidence = class_probs[best_label]
        elif self._weights is not None and self._weights.ndim == 2:
            logits = x @ self._weights.T + self._bias
            logits -= logits.max()
            exp_l = np.exp(logits)
            probs = exp_l / exp_l.sum()
            class_probs = {
                self._idx_to_label.get(i, f"class_{i}"): round(float(p), 6)
                for i, p in enumerate(probs)
            }
            best_idx = int(np.argmax(probs))
            best_label = self._idx_to_label.get(best_idx, "unknown")
            confidence = float(probs[best_idx])
        else:
            return self._confidence_weighted_fallback(predictions, None)

        contributions = self._compute_contributions(predictions)
        avg_risk = float(np.mean([p.risk_score for p in predictions]))

        return FusedPrediction(
            predicted_label=best_label,
            confidence=round(float(confidence), 6),
            probabilities=class_probs,
            risk_score=round(avg_risk, 6),
            strategy_name="stacking",
            provider_contributions=contributions,
            source_predictions=predictions,
            calibrated=True,
            num_providers=len(predictions),
            num_failed=num_failed,
            reasoning_summary=f"Stacking meta-learner: {best_label} = {confidence:.3f}",
        )

    def _confidence_weighted_fallback(
        self,
        predictions: list[ThreatPrediction],
        weights: dict[str, float] | None = None,
        num_failed: int = 0,
    ) -> FusedPrediction:
        """Fallback: confidence-weighted averaging."""
        weights = weights or {}
        votes: dict[str, float] = {}
        contributions: dict[str, float] = {}
        total = 0.0

        for pred in predictions:
            w = weights.get(pred.provider_id, pred.confidence)
            votes[pred.predicted_label] = votes.get(pred.predicted_label, 0.0) + w
            contributions[pred.provider_id] = w
            total += w

        if total > 0:
            contributions = {k: v / total for k, v in contributions.items()}

        best_label = max(votes, key=votes.get) if votes else "unknown"  # type: ignore[arg-type]
        confidence = votes.get(best_label, 0.0) / total if total > 0 else 0.0
        probabilities = {k: round(v / total, 6) if total > 0 else 0.0 for k, v in votes.items()}
        avg_risk = float(np.mean([p.risk_score for p in predictions])) if predictions else 0.0

        return FusedPrediction(
            predicted_label=best_label,
            confidence=round(confidence, 6),
            probabilities=probabilities,
            risk_score=round(avg_risk, 6),
            strategy_name="stacking",
            provider_contributions=contributions,
            source_predictions=predictions,
            num_providers=len(predictions),
            num_failed=num_failed,
            reasoning_summary=f"Stacking fallback (untrained): {best_label} = {confidence:.3f}",
        )

    def _extract_provider_order(
        self, batches: list[list[ThreatPrediction]]
    ) -> list[str]:
        """Extract deterministic provider ordering from training data."""
        seen: dict[str, int] = {}
        for batch in batches:
            for pred in batch:
                if pred.provider_id not in seen:
                    seen[pred.provider_id] = len(seen)
        return sorted(seen.keys())

    def _build_label_map(self, labels: list[str]) -> None:
        """Build label <-> index mapping."""
        unique = sorted(set(labels))
        self._label_to_idx = {label: i for i, label in enumerate(unique)}
        self._idx_to_label = {i: label for label, i in self._label_to_idx.items()}

    def _vectorize_batch(self, batches: list[list[ThreatPrediction]]) -> np.ndarray:
        """Convert prediction batches to feature vectors."""
        return np.array([self._vectorize_single(batch) for batch in batches])

    def _vectorize_single(self, predictions: list[ThreatPrediction]) -> np.ndarray:
        """Convert one prediction batch to a feature vector.

        Feature = [confidence * (1 if provider matches) for each provider].
        """
        pred_map = {p.provider_id: p.confidence for p in predictions}
        return np.array([
            pred_map.get(pid, 0.0) for pid in self._provider_order
        ])

    def _compute_contributions(self, predictions: list[ThreatPrediction]) -> dict[str, float]:
        """Compute per-provider contribution weights."""
        total_conf = sum(p.confidence for p in predictions)
        if total_conf <= 0:
            n = len(predictions)
            return {p.provider_id: 1.0 / n for p in predictions} if n > 0 else {}
        return {p.provider_id: p.confidence / total_conf for p in predictions}

    def _empty_result(self, all_predictions: list[ThreatPrediction]) -> FusedPrediction:
        return FusedPrediction(
            predicted_label="unknown",
            confidence=0.0,
            probabilities={},
            risk_score=0.0,
            strategy_name="stacking",
            source_predictions=all_predictions,
            num_providers=0,
            num_failed=len(all_predictions),
            reasoning_summary="No valid predictions to fuse",
        )
