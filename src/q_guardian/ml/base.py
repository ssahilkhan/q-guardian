"""Base classes for ML threat models and model registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

from q_guardian.ml.enums import ModelBackend, ModelStatus, ModelType
from q_guardian.ml.data import ModelMetadata
from q_guardian.security.extensibility import DetectionResult
from q_guardian.security.models import PromptFeatures

logger = structlog.get_logger("ml.base")


class BaseThreatModel(ABC):
    """Common interface for all ML threat models.

    Every ML algorithm (Isolation Forest, Random Forest, XGBoost,
    QSVM, etc.) must implement this interface. This ensures that
    Module 6 (Quantum) can add new models without modifying the
    inference pipeline.
    """

    @property
    @abstractmethod
    def metadata(self) -> ModelMetadata:
        """Return model metadata."""

    @abstractmethod
    async def predict(self, features: list[float]) -> dict[str, Any]:
        """Run prediction on a numeric feature vector.

        Args:
            features: Numeric feature vector.

        Returns:
            Dictionary with prediction results (model-specific).
        """

    def health(self) -> dict[str, Any]:
        """Return model health status."""
        return {
            "status": "healthy",
            "model": self.metadata.name,
            "model_status": self.metadata.status.value,
        }


class ModelRegistry:
    """Registry for managing ML model instances.

    Supports registration, lookup, and lifecycle tracking of models.
    """

    def __init__(self) -> None:
        self._models: dict[str, BaseThreatModel] = {}
        self._metadata: dict[str, ModelMetadata] = {}

    def register(self, model: BaseThreatModel) -> None:
        """Register a model instance.

        Args:
            model: The model to register.
        """
        meta = model.metadata
        self._models[meta.name] = model
        self._metadata[meta.name] = meta
        logger.info("model_registered", model_name=meta.name, backend=meta.backend.value)

    def unregister(self, name: str) -> bool:
        """Unregister a model by name.

        Args:
            name: Model name.

        Returns:
            True if the model was found and removed.
        """
        if name in self._models:
            del self._models[name]
            del self._metadata[name]
            logger.info("model_unregistered", model_name=name)
            return True
        return False

    def get(self, name: str) -> BaseThreatModel | None:
        """Get a model by name.

        Args:
            name: Model name.

        Returns:
            The model instance, or None if not found.
        """
        return self._models.get(name)

    def get_metadata(self, name: str) -> ModelMetadata | None:
        """Get metadata for a model by name.

        Args:
            name: Model name.

        Returns:
            The model metadata, or None if not found.
        """
        return self._metadata.get(name)

    def list_models(self) -> list[ModelMetadata]:
        """List all registered model metadata.

        Returns:
            List of ModelMetadata for all registered models.
        """
        return list(self._metadata.values())

    def list_by_type(self, model_type: ModelType) -> list[ModelMetadata]:
        """List models filtered by type.

        Args:
            model_type: Filter to this model type.

        Returns:
            Matching model metadata.
        """
        return [m for m in self._metadata.values() if m.model_type == model_type]

    def list_by_backend(self, backend: ModelBackend) -> list[ModelMetadata]:
        """List models filtered by backend.

        Args:
            backend: Filter to this backend.

        Returns:
            Matching model metadata.
        """
        return [m for m in self._metadata.values() if m.backend == backend]

    def count(self) -> int:
        """Return the number of registered models."""
        return len(self._models)

    def clear(self) -> None:
        """Remove all registered models."""
        self._models.clear()
        self._metadata.clear()
