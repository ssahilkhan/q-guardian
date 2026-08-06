"""QuantumTrainer — abstract training pipeline for quantum models."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from q_guardian.quantum.config import QuantumTrainingConfig
from q_guardian.quantum.data import QuantumTrainingResult

if TYPE_CHECKING:
    from q_guardian.quantum.models.base import BaseQuantumModel

logger = structlog.get_logger("quantum.trainer")


class QuantumTrainer:
    """Training pipeline for quantum models.

    Manages the training lifecycle: data preparation, optimization,
    convergence checking, and result reporting.
    """

    def __init__(self, config: QuantumTrainingConfig | None = None) -> None:
        self._config = config or QuantumTrainingConfig()

    @property
    def config(self) -> QuantumTrainingConfig:
        return self._config

    def train(
        self,
        model: BaseQuantumModel,
        x: list[list[float]],
        y: list[int] | None = None,
        x_val: list[list[float]] | None = None,
        y_val: list[int] | None = None,
    ) -> QuantumTrainingResult:
        """Train a quantum model.

        Args:
            model: The quantum model to train.
            x: Training feature vectors.
            y: Training labels (None for unsupervised).
            x_val: Validation features.
            y_val: Validation labels.

        Returns:
            QuantumTrainingResult with training metrics.
        """
        start = time.monotonic()

        try:
            if hasattr(model, "train"):
                if y is not None:
                    model.train(x, y)
                else:
                    model.train(x)

            elapsed = time.monotonic() - start

            accuracy = 0.0
            if x_val and y_val and hasattr(model, "predict"):
                correct = 0
                for xi, yi in zip(x_val, y_val, strict=False):
                    import asyncio

                    result = asyncio.run(model.predict(xi))
                    predicted = result.get("predicted_class", "")
                    if str(yi) == str(predicted):
                        correct += 1
                accuracy = correct / len(y_val) if y_val else 0.0

            return QuantumTrainingResult(
                model_name=model.name,
                status="completed",
                accuracy=accuracy,
                training_time_s=round(elapsed, 3),
                metrics={"optimizer": self._config.optimizer.value},
            )
        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error("quantum_training_error", model=model.name, error=str(e))
            return QuantumTrainingResult(
                model_name=model.name,
                status="failed",
                error_message=str(e),
                training_time_s=round(elapsed, 3),
            )

    def cross_validate(
        self,
        model: BaseQuantumModel,
        x: list[list[float]],
        y: list[int],
        n_folds: int = 5,
    ) -> QuantumTrainingResult:
        """Perform k-fold cross-validation.

        Args:
            model: The quantum model to evaluate.
            x: Feature vectors.
            y: Labels.
            n_folds: Number of folds.

        Returns:
            QuantumTrainingResult with CV scores.
        """
        n = len(x)
        fold_size = max(1, n // n_folds)
        scores: list[float] = []

        for fold in range(n_folds):
            val_start = fold * fold_size
            val_end = min(val_start + fold_size, n)

            x_train = x[:val_start] + x[val_end:]
            y_train = y[:val_start] + y[val_end:]
            x_val = x[val_start:val_end]
            y_val = y[val_start:val_end]

            if not x_train or not x_val:
                continue

            result = self.train(model, x_train, y_train, x_val, y_val)
            scores.append(result.accuracy)

        mean_score = sum(scores) / len(scores) if scores else 0.0
        std_score = (
            (sum((s - mean_score) ** 2 for s in scores) / len(scores)) ** 0.5 if scores else 0.0
        )

        return QuantumTrainingResult(
            model_name=model.name,
            status="completed",
            accuracy=mean_score,
            cv_scores=scores,
            cv_mean=round(mean_score, 4),
            cv_std=round(std_score, 4),
            metrics={"n_folds": n_folds, "optimizer": self._config.optimizer.value},
        )
