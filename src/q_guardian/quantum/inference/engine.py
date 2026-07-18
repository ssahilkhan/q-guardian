"""QuantumInferenceEngine — inference orchestrator for quantum models.

Routes features to the correct quantum model, manages batch inference,
and produces standardized QuantumInferenceResult objects.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import structlog

from q_guardian.quantum.data import QuantumInferenceResult
from q_guardian.quantum.enums import QuantumModelType
from q_guardian.quantum.exceptions import (
    ConfigurationError,
    ModelNotTrainedError,
    QuantumInferenceError,
)
from q_guardian.quantum.models.base import BaseQuantumModel

logger = structlog.get_logger("quantum.inference_engine")


class QuantumInferenceEngine:
    """Orchestrates inference across multiple registered quantum models.

    Features:
      - Route by model name or auto-select by model type
      - Batch inference with per-item and aggregate metrics
      - Fallback to next model on inference failure
      - Performance tracking (latency, throughput)
    """

    def __init__(self) -> None:
        self._models: dict[str, BaseQuantumModel] = {}
        self._fallback_order: list[str] = []
        self._inference_history: list[dict[str, Any]] = []
        self._total_inferences = 0
        self._total_errors = 0
        self._total_latency_ms = 0.0

    @property
    def model_count(self) -> int:
        return len(self._models)

    @property
    def total_inferences(self) -> int:
        return self._total_inferences

    @property
    def total_errors(self) -> int:
        return self._total_errors

    @property
    def average_latency_ms(self) -> float:
        if self._total_inferences == 0:
            return 0.0
        return self._total_latency_ms / self._total_inferences

    @property
    def model_names(self) -> list[str]:
        return list(self._models.keys())

    @property
    def fallback_order(self) -> list[str]:
        return list(self._fallback_order)

    def register_model(self, model: BaseQuantumModel, fallback_priority: int | None = None) -> None:
        """Register a quantum model for inference."""
        if model.name in self._models:
            logger.warning("model_already_registered", name=model.name)

        self._models[model.name] = model
        if fallback_priority is not None:
            while len(self._fallback_order) <= fallback_priority:
                self._fallback_order.append(model.name)
            self._fallback_order[fallback_priority] = model.name
        elif model.name not in self._fallback_order:
            self._fallback_order.append(model.name)

        logger.info(
            "quantum_model_registered_inference",
            name=model.name,
            priority=fallback_priority,
        )

    def unregister_model(self, model_name: str) -> bool:
        """Remove a model from the inference engine."""
        if model_name not in self._models:
            return False

        del self._models[model_name]
        if model_name in self._fallback_order:
            self._fallback_order.remove(model_name)

        logger.info("quantum_model_unregistered", name=model_name)
        return True

    def get_model(self, model_name: str) -> BaseQuantumModel | None:
        """Retrieve a model by name."""
        return self._models.get(model_name)

    def select_model(self, model_name: str | None = None) -> BaseQuantumModel | None:
        """Select model by name, or auto-select best available."""
        if model_name is not None:
            return self._models.get(model_name)

        for name in self._fallback_order:
            model = self._models.get(name)
            if model is not None and model.is_trained:
                return model

        for model in self._models.values():
            if model.is_trained:
                return model

        return None

    async def infer(
        self,
        features: list[float],
        model_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QuantumInferenceResult:
        """Run inference on a single feature vector."""
        model = self.select_model(model_name)
        if model is None:
            raise QuantumInferenceError(
                detail="No model available for inference",
                model_name=model_name or "auto",
            )

        start = time.monotonic()
        try:
            result = await model.predict_quantum(features)
        except Exception as exc:
            logger.error(
                "quantum_inference_error",
                model=model.name,
                error=str(exc),
            )
            return await self._fallback_infer(features, model_name, exc)

        elapsed_ms = (time.monotonic() - start) * 1000
        self._total_inferences += 1
        self._total_latency_ms += elapsed_ms

        self._record_inference(model.name, features, result, elapsed_ms, metadata)

        return result

    async def infer_batch(
        self,
        batch_features: list[list[float]],
        model_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[QuantumInferenceResult]:
        """Run inference on a batch of feature vectors."""
        if not batch_features:
            return []

        results: list[QuantumInferenceResult] = []
        batch_start = time.monotonic()

        for features in batch_features:
            result = await self.infer(features, model_name, metadata)
            results.append(result)

        batch_elapsed_ms = (time.monotonic() - batch_start) * 1000

        logger.info(
            "quantum_batch_inference_complete",
            batch_size=len(batch_features),
            batch_time_ms=round(batch_elapsed_ms, 2),
            avg_per_item_ms=round(batch_elapsed_ms / len(batch_features), 2),
        )

        return results

    async def _fallback_infer(
        self,
        features: list[float],
        failed_model: str | None,
        original_error: Exception,
    ) -> QuantumInferenceResult:
        """Attempt inference with fallback models."""
        attempted = {failed_model} if failed_model else set()

        for name in self._fallback_order:
            if name in attempted:
                continue
            model = self._models.get(name)
            if model is None or not model.is_trained:
                continue

            try:
                result = await model.predict_quantum(features)
                self._total_inferences += 1
                logger.info(
                    "fallback_inference_success",
                    failed_model=failed_model,
                    fallback_model=name,
                )
                return result
            except Exception:
                attempted.add(name)
                continue

        self._total_errors += 1
        logger.error(
            "all_fallbacks_failed",
            failed_model=failed_model,
            attempted=list(attempted),
        )
        return QuantumInferenceResult(
            model_name=failed_model or "unknown",
            predictions={},
            predicted_class="unknown",
            confidence=0.0,
            risk_score=0.0,
            metadata={
                "error": str(original_error),
                "fallback_exhausted": True,
            },
        )

    def _record_inference(
        self,
        model_name: str,
        features: list[float],
        result: QuantumInferenceResult,
        latency_ms: float,
        metadata: dict[str, Any] | None,
    ) -> None:
        record = {
            "model": model_name,
            "predicted_class": result.predicted_class,
            "confidence": result.confidence,
            "risk_score": result.risk_score,
            "latency_ms": round(latency_ms, 3),
            "feature_dim": len(features),
            "metadata": metadata or {},
        }
        self._inference_history.append(record)

        if len(self._inference_history) > 1000:
            self._inference_history = self._inference_history[-1000:]

    def get_performance_stats(self) -> dict[str, Any]:
        """Return aggregate performance statistics."""
        if not self._inference_history:
            return {
                "total_inferences": 0,
                "total_errors": 0,
                "average_latency_ms": 0.0,
                "error_rate": 0.0,
            }

        latencies = [r["latency_ms"] for r in self._inference_history]
        return {
            "total_inferences": self._total_inferences,
            "total_errors": self._total_errors,
            "average_latency_ms": round(self.average_latency_ms, 3),
            "min_latency_ms": round(min(latencies), 3),
            "max_latency_ms": round(max(latencies), 3),
            "error_rate": round(self._total_errors / max(self._total_inferences + self._total_errors, 1), 4),
            "model_usage": self._get_model_usage(),
            "history_size": len(self._inference_history),
        }

    def _get_model_usage(self) -> dict[str, int]:
        usage: dict[str, int] = {}
        for record in self._inference_history:
            model = record.get("model", "unknown")
            usage[model] = usage.get(model, 0) + 1
        return usage

    def clear_history(self) -> int:
        """Clear inference history."""
        count = len(self._inference_history)
        self._inference_history.clear()
        return count

    def health(self) -> dict[str, Any]:
        """Return engine health status."""
        models_health = {}
        for name, model in self._models.items():
            try:
                models_health[name] = model.health()
            except Exception as exc:
                models_health[name] = {"status": "error", "error": str(exc)}

        return {
            "model_count": self._models.__len__(),
            "trained_models": sum(1 for m in self._models.values() if m.is_trained),
            "fallback_order": self._fallback_order,
            "performance": self.get_performance_stats(),
            "models": models_health,
        }
