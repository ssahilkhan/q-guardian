"""Training pipeline for ML models."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog
from sklearn.model_selection import cross_val_score, train_test_split

from q_guardian.ml.config import MLConfig
from q_guardian.ml.data import TrainingResult
from q_guardian.ml.enums import TrainingStatus
from q_guardian.ml.evaluation.metrics import BenchmarkMetrics

if TYPE_CHECKING:
    from q_guardian.ml.base import BaseThreatModel
    from q_guardian.ml.storage import ModelStorage

logger = structlog.get_logger("ml.training")


class ModelTrainer:
    """Trains ML models using scikit-learn compatible interfaces.

    Supports:
    - Train/test split with configurable ratios
    - Cross-validation
    - Feature importance extraction
    - Automatic model saving after training
    """

    def __init__(
        self,
        config: MLConfig | None = None,
        storage: ModelStorage | None = None,
    ) -> None:
        self._config = config or MLConfig()
        self._storage = storage
        self._metrics = BenchmarkMetrics()

    async def train(
        self,
        model: BaseThreatModel,
        x: list[list[float]],
        y: list[int],
        feature_names: list[str] | None = None,
        test_size: float | None = None,
        cv_folds: int | None = None,
    ) -> TrainingResult:
        """Train a model and return training results.

        Args:
            model: The model to train (must have a .train() method).
            x: Feature vectors.
            y: Labels.
            feature_names: Optional feature names for importance.
            test_size: Test split ratio (default from config).
            cv_folds: CV fold count (default from config).

        Returns:
            TrainingResult with metrics and metadata.
        """
        start = time.monotonic()
        test_size = test_size if test_size is not None else self._config.default_test_size
        cv_folds = cv_folds if cv_folds is not None else self._config.default_cv_folds

        try:
            x_arr = np.array(x, dtype=np.float64)
            y_arr = np.array(y, dtype=np.int32)

            x_train, x_test, y_train, y_test = train_test_split(
                x_arr,
                y_arr,
                test_size=test_size,
                random_state=self._config.random_state,
            )

            # Train the model
            model.train(x_train.tolist(), y_train.tolist())

            # Cross-validation on training set
            cv_scores: list[float] = []
            cv_mean = 0.0
            cv_std = 0.0

            if hasattr(model, "model") and model.model is not None and len(x_train) >= cv_folds:
                try:
                    cv_scores = cross_val_score(
                        model.model,
                        x_train,
                        y_train,
                        cv=min(cv_folds, len(x_train)),
                        scoring="accuracy",
                    ).tolist()
                    cv_mean = float(np.mean(cv_scores))
                    cv_std = float(np.std(cv_scores))
                except Exception:
                    logger.warning("cv_failed", exc_info=True)

            # Evaluate on test set
            y_pred = model.model.predict(x_test).tolist()

            eval_metrics = self._metrics.compute_classification_metrics(y_test.tolist(), y_pred)

            # Feature importance
            feature_importance: dict[str, float] = {}
            if (
                hasattr(model, "model")
                and model.model is not None
                and hasattr(model.model, "feature_importances_")
                and feature_names
            ):
                importances = model.model.feature_importances_
                for i, name in enumerate(feature_names):
                    if i < len(importances):
                        feature_importance[name] = float(importances[i])

            elapsed = time.monotonic() - start

            result = TrainingResult(
                model_name=model.metadata.name,
                status=TrainingStatus.COMPLETED,
                metrics=eval_metrics.model_dump(),
                feature_importance=feature_importance,
                training_samples=len(x_train),
                validation_samples=len(x_test),
                training_time_s=round(elapsed, 3),
                cv_scores=cv_scores,
                cv_mean=cv_mean,
                cv_std=cv_std,
            )

            # Auto-save
            if self._storage and self._config.auto_save:
                artifact_path = self._storage.save(model.model, model.metadata)
                result.artifact_path = artifact_path

            logger.info(
                "model_training_completed",
                model_name=model.metadata.name,
                accuracy=eval_metrics.accuracy,
                cv_mean=cv_mean,
            )

            return result

        except Exception as e:
            elapsed = time.monotonic() - start
            return TrainingResult(
                model_name=model.metadata.name,
                status=TrainingStatus.FAILED,
                training_time_s=round(elapsed, 3),
                error_message=str(e),
            )

    async def train_anomaly_detector(
        self,
        model: BaseThreatModel,
        x: list[list[float]],
    ) -> TrainingResult:
        """Train an anomaly detector (unsupervised, no labels).

        Args:
            model: Anomaly detection model (e.g. IsolationForestDetector).
            x: Feature vectors (no labels needed).

        Returns:
            TrainingResult.
        """
        start = time.monotonic()

        try:
            model.train(x)

            elapsed = time.monotonic() - start
            result = TrainingResult(
                model_name=model.metadata.name,
                status=TrainingStatus.COMPLETED,
                training_samples=len(x),
                training_time_s=round(elapsed, 3),
            )

            if self._storage and self._config.auto_save:
                artifact_path = self._storage.save(model.model, model.metadata)
                result.artifact_path = artifact_path

            logger.info(
                "anomaly_detector_trained",
                model_name=model.metadata.name,
                samples=len(x),
            )

            return result

        except Exception as e:
            elapsed = time.monotonic() - start
            return TrainingResult(
                model_name=model.metadata.name,
                status=TrainingStatus.FAILED,
                training_time_s=round(elapsed, 3),
                error_message=str(e),
            )


class CrossValidator:
    """Cross-validation utilities for model evaluation."""

    def __init__(self, config: MLConfig | None = None) -> None:
        self._config = config or MLConfig()

    async def cross_validate(
        self,
        model: BaseThreatModel,
        x: list[list[float]],
        y: list[int],
        folds: int | None = None,
        scoring: str = "accuracy",
    ) -> dict[str, Any]:
        """Run cross-validation on a model.

        Args:
            model: The model to validate.
            x: Feature vectors.
            y: Labels.
            folds: Number of CV folds.
            scoring: Scoring metric.

        Returns:
            Dictionary with CV results.
        """
        folds = folds or self._config.default_cv_folds
        x_arr = np.array(x, dtype=np.float64)
        y_arr = np.array(y, dtype=np.int32)

        if not hasattr(model, "model") or model.model is None:
            return {"error": "Model not trained", "scores": [], "mean": 0.0, "std": 0.0}

        try:
            scores = cross_val_score(
                model.model,
                x_arr,
                y_arr,
                cv=min(folds, len(x_arr)),
                scoring=scoring,
            )
            return {
                "scores": scores.tolist(),
                "mean": float(np.mean(scores)),
                "std": float(np.std(scores)),
                "folds": len(scores),
                "scoring": scoring,
            }
        except Exception as e:
            return {"error": str(e), "scores": [], "mean": 0.0, "std": 0.0}
