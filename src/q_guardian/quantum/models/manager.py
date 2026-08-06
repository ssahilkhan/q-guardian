"""QuantumModelManager — lifecycle manager for quantum models.

Manages registration, metadata, versioning, health, and lifecycle
of all quantum models. Follows the same pattern as
q_guardian.ml.models.ModelManager but for quantum models.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from q_guardian.quantum.data import QuantumModelMetadata
    from q_guardian.quantum.enums import QuantumModelType
    from q_guardian.quantum.models.base import BaseQuantumModel

logger = structlog.get_logger("quantum.model_manager")


@dataclass
class ModelRegistration:
    """Internal bookkeeping for a registered quantum model."""

    model: BaseQuantumModel
    registered_at: float
    last_inference_at: float | None = None
    inference_count: int = 0
    error_count: int = 0
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class QuantumModelManager:
    """Manages the lifecycle of all quantum models in the system.

    Responsibilities:
      - Register / unregister models with metadata
      - Version tracking and model listing with filters
      - Inference counting and error tracking
      - Health aggregation across all models
      - Model selection by name, type, or tags
      - Serialization of manager state
    """

    def __init__(self) -> None:
        self._registrations: dict[str, ModelRegistration] = {}
        self._created_at = time.monotonic()

    @property
    def model_count(self) -> int:
        return len(self._registrations)

    @property
    def model_names(self) -> list[str]:
        return list(self._registrations.keys())

    def register(
        self,
        model: BaseQuantumModel,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a quantum model."""
        if model.name in self._registrations:
            logger.warning("model_already_registered", name=model.name)
            return

        self._registrations[model.name] = ModelRegistration(
            model=model,
            registered_at=time.monotonic(),
            tags=tags or [],
            metadata=metadata or {},
        )

        logger.info(
            "quantum_model_registered",
            name=model.name,
            tags=tags or [],
        )

    def unregister(self, model_name: str) -> bool:
        """Unregister a quantum model."""
        if model_name not in self._registrations:
            return False
        del self._registrations[model_name]
        logger.info("quantum_model_unregistered", name=model_name)
        return True

    def get(self, model_name: str) -> BaseQuantumModel | None:
        """Get a model by name."""
        reg = self._registrations.get(model_name)
        return reg.model if reg else None

    def get_metadata(self, model_name: str) -> QuantumModelMetadata | None:
        """Get metadata for a model."""
        reg = self._registrations.get(model_name)
        if reg is None:
            return None
        return reg.model.quantum_metadata

    def get_registration(self, model_name: str) -> ModelRegistration | None:
        """Get the full registration record for a model."""
        return self._registrations.get(model_name)

    def list_models(
        self,
        model_type: QuantumModelType | None = None,
        trained_only: bool = False,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List models with optional filters."""
        results: list[dict[str, Any]] = []
        for name, reg in self._registrations.items():
            if model_type is not None:
                meta = reg.model.quantum_metadata
                if meta.model_type != model_type:
                    continue

            if trained_only and not reg.model.is_trained:
                continue

            if tags and not set(tags).intersection(set(reg.tags)):
                continue

            results.append(
                {
                    "name": name,
                    "model_type": reg.model.quantum_metadata.model_type.value,
                    "is_trained": reg.model.is_trained,
                    "inference_count": reg.inference_count,
                    "error_count": reg.error_count,
                    "tags": list(reg.tags),
                    "registered_at": reg.registered_at,
                    "last_inference_at": reg.last_inference_at,
                }
            )

        return results

    def record_inference(self, model_name: str, success: bool = True) -> None:
        """Record an inference event for a model."""
        reg = self._registrations.get(model_name)
        if reg is None:
            return

        reg.last_inference_at = time.monotonic()
        reg.inference_count += 1
        if not success:
            reg.error_count += 1

    def get_best_model(
        self,
        model_type: QuantumModelType | None = None,
    ) -> BaseQuantumModel | None:
        """Select the best trained model based on fewest errors."""
        best_name: str | None = None
        best_score = float("inf")

        for name, reg in self._registrations.items():
            if not reg.model.is_trained:
                continue
            if model_type is not None:
                meta = reg.model.quantum_metadata
                if meta.model_type != model_type:
                    continue

            error_rate = reg.error_count / max(reg.inference_count, 1)
            if error_rate < best_score:
                best_score = error_rate
                best_name = name

        if best_name is not None:
            return self._registrations[best_name].model
        return None

    def health(self) -> dict[str, Any]:
        """Aggregate health across all registered models."""
        models_health: dict[str, Any] = {}
        total_inferences = 0
        total_errors = 0
        trained_count = 0

        for name, reg in self._registrations.items():
            try:
                model_health = reg.model.health()
                models_health[name] = model_health
            except Exception as exc:
                models_health[name] = {"status": "error", "error": str(exc)}

            total_inferences += reg.inference_count
            total_errors += reg.error_count
            if reg.model.is_trained:
                trained_count += 1

        return {
            "model_count": self.model_count,
            "trained_count": trained_count,
            "total_inferences": total_inferences,
            "total_errors": total_errors,
            "error_rate": round(total_errors / max(total_inferences, 1), 4),
            "models": models_health,
        }

    def save_state(self) -> dict[str, Any]:
        """Serialize manager state (excluding model objects)."""
        models_info = {}
        for name, reg in self._registrations.items():
            models_info[name] = {
                "model_type": reg.model.quantum_metadata.model_type.value,
                "is_trained": reg.model.is_trained,
                "inference_count": reg.inference_count,
                "error_count": reg.error_count,
                "tags": list(reg.tags),
                "metadata": dict(reg.metadata),
            }

        return {
            "model_count": self.model_count,
            "models": models_info,
        }

    def clear(self) -> int:
        """Unregister all models."""
        count = self.model_count
        self._registrations.clear()
        logger.info("quantum_model_manager_cleared", count=count)
        return count
