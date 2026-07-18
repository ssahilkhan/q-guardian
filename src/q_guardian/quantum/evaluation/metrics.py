"""Quantum model evaluation metrics."""

from __future__ import annotations

import time
from typing import Any

import structlog

from q_guardian.quantum.data import QuantumEvaluationMetrics
from q_guardian.quantum.models.base import BaseQuantumModel

logger = structlog.get_logger("quantum.evaluation")


class QuantumEvaluator:
    """Evaluates quantum models with comprehensive metrics.

    Provides classification metrics, circuit analysis, and
    quantum-specific evaluation for research benchmarks.
    """

    def __init__(self) -> None:
        pass

    def evaluate(
        self,
        model: BaseQuantumModel,
        X_test: list[list[float]],
        y_test: list[int],
        class_names: list[str] | None = None,
    ) -> QuantumEvaluationMetrics:
        """Evaluate a quantum model on test data.

        Args:
            model: The trained quantum model.
            X_test: Test feature vectors.
            y_test: Test labels.
            class_names: Optional class name mapping.

        Returns:
            QuantumEvaluationMetrics with full evaluation results.
        """
        import asyncio

        predictions: list[int] = []
        confidences: list[float] = []
        start = time.monotonic()

        for x in X_test:
            try:
                result = asyncio.run(model.predict(x))
                pred_class = result.get("predicted_class", "")
                confidence = result.get("confidence", 0.0)
                if class_names:
                    pred_idx = class_names.index(pred_class) if pred_class in class_names else -1
                else:
                    try:
                        pred_idx = int(pred_class)
                    except (ValueError, TypeError):
                        pred_idx = -1
                predictions.append(pred_idx)
                confidences.append(float(confidence))
            except Exception:
                predictions.append(-1)
                confidences.append(0.0)

        elapsed = time.monotonic() - start

        tp = tn = fp = fn = 0
        for pred, true in zip(predictions, y_test):
            if pred == true:
                tp += 1
            elif pred >= 0:
                fp += 1
            else:
                fn += 1

        total = len(y_test)
        accuracy = tp / total if total > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        avg_time_ms = (elapsed * 1000) / max(len(X_test), 1)

        qmeta = model.quantum_metadata
        return QuantumEvaluationMetrics(
            accuracy=round(accuracy, 4),
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1_score=round(f1, 4),
            false_positive_rate=round(fpr, 4),
            false_negative_rate=round(fnr, 4),
            circuit_width=qmeta.num_qubits,
            inference_time_ms=round(avg_time_ms, 3),
            backend_used=qmeta.backend_type.value,
            metadata={
                "model_name": model.name,
                "num_samples": len(X_test),
                "avg_confidence": round(avg_confidence, 4),
            },
        )

    def compare_models(
        self,
        models: list[BaseQuantumModel],
        X_test: list[list[float]],
        y_test: list[int],
        class_names: list[str] | None = None,
    ) -> dict[str, QuantumEvaluationMetrics]:
        """Evaluate and compare multiple models.

        Args:
            models: List of trained quantum models.
            X_test: Test feature vectors.
            y_test: Test labels.
            class_names: Optional class name mapping.

        Returns:
            Dictionary mapping model names to their evaluation metrics.
        """
        results: dict[str, QuantumEvaluationMetrics] = {}
        for model in models:
            try:
                metrics = self.evaluate(model, X_test, y_test, class_names)
                results[model.name] = metrics
            except Exception as e:
                logger.error("model_evaluation_error", model=model.name, error=str(e))
        return results
