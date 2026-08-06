"""ModelManager — responsible for model lifecycle, lazy loading, versioning, and health."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.ml.base import BaseThreatModel, ModelRegistry
from q_guardian.ml.enums import ModelStatus, ModelType
from q_guardian.ml.storage import ModelStorage

if TYPE_CHECKING:
    from q_guardian.ml.data import ModelMetadata

logger = structlog.get_logger("ml.model_manager")


class ModelManager:
    """Manages the full lifecycle of ML models.

    Responsibilities:
    - Registration and unregistration of models
    - Lazy loading from disk (load on first use)
    - Version tracking and upgrade paths
    - Health monitoring of loaded models
    - Coordinated save/load via ModelStorage
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        storage: ModelStorage | None = None,
    ) -> None:
        self._registry = registry or ModelRegistry()
        self._storage = storage or ModelStorage()
        self._loaded_models: dict[str, BaseThreatModel] = {}

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    @property
    def storage(self) -> ModelStorage:
        return self._storage

    def register_model(self, model: BaseThreatModel) -> None:
        """Register a model and track its metadata.

        Args:
            model: The model instance to register.
        """
        self._registry.register(model)
        meta = model.metadata
        if meta.status == ModelStatus.UNLOADED and meta.artifact_path:
            logger.info(
                "model_registered_lazy",
                model_name=meta.name,
                artifact=meta.artifact_path,
            )
        else:
            self._loaded_models[meta.name] = model

    def unregister_model(self, name: str) -> bool:
        """Unregister and optionally unload a model.

        Args:
            name: Model name.

        Returns:
            True if the model was found and removed.
        """
        self._loaded_models.pop(name, None)
        return self._registry.unregister(name)

    def get_model(self, name: str) -> BaseThreatModel | None:
        """Get a model by name, loading from disk if needed.

        Args:
            name: Model name.

        Returns:
            The model instance, or None if not found.
        """
        if name in self._loaded_models:
            return self._loaded_models[name]

        meta = self._registry.get_metadata(name)
        if meta is None:
            return None

        # Lazy load
        return self._lazy_load(name)

    def _lazy_load(self, name: str) -> BaseThreatModel | None:
        """Load a model from disk on first access.

        Args:
            name: Model name.

        Returns:
            The loaded model, or None if load fails.
        """
        model = self._registry.get(name)
        meta = self._registry.get_metadata(name)
        if model is None or meta is None:
            return None

        if meta.status == ModelStatus.READY and name in self._loaded_models:
            return self._loaded_models[name]

        try:
            meta.status = ModelStatus.LOADING
            artifact = self._storage.load(meta)
            # For sklearn/xgboost models, the artifact is the raw model object.
            # We store it in the model's internal attribute if it has one.
            if hasattr(model, "_model"):
                model._model = artifact
            meta.status = ModelStatus.READY
            self._loaded_models[name] = model
            logger.info("model_lazy_loaded", model_name=name)
            return model
        except Exception:
            meta.status = ModelStatus.ERROR
            logger.error("model_lazy_load_failed", model_name=name, exc_info=True)
            return None

    def load_model(self, name: str) -> BaseThreatModel | None:
        """Explicitly load a model from disk.

        Args:
            name: Model name.

        Returns:
            The loaded model, or None if not found/load fails.
        """
        return self._lazy_load(name)

    def unload_model(self, name: str) -> bool:
        """Unload a model from memory.

        Args:
            name: Model name.

        Returns:
            True if the model was loaded and is now unloaded.
        """
        if name in self._loaded_models:
            meta = self._registry.get_metadata(name)
            if meta:
                meta.status = ModelStatus.UNLOADED
            del self._loaded_models[name]
            logger.info("model_unloaded", model_name=name)
            return True
        return False

    def save_model(self, name: str) -> str | None:
        """Save a model to disk.

        Args:
            name: Model name.

        Returns:
            Path to saved artifact, or None if model not found.
        """
        model = self._loaded_models.get(name)
        meta = self._registry.get_metadata(name)
        if model is None or meta is None:
            return None

        # For sklearn/xgboost models, get the internal model object
        artifact = getattr(model, "_model", None)
        if artifact is None:
            logger.warning("no_artifact_to_save", model_name=name)
            return None

        return self._storage.save(artifact, meta)

    def save_all(self) -> dict[str, str]:
        """Save all loaded models.

        Returns:
            Dictionary mapping model names to artifact paths.
        """
        results: dict[str, str] = {}
        for name in self._loaded_models:
            path = self.save_model(name)
            if path:
                results[name] = path
        return results

    def health(self) -> dict[str, Any]:
        """Return health status for all registered models.

        Returns:
            Dictionary with per-model health info.
        """
        models_health: dict[str, Any] = {}
        for meta in self._registry.list_models():
            model = self._registry.get(meta.name)
            if model:
                models_health[meta.name] = model.health()
            else:
                models_health[meta.name] = {
                    "status": "unavailable",
                    "model": meta.name,
                }
        return {
            "total_models": self._registry.count(),
            "loaded_models": len(self._loaded_models),
            "models": models_health,
        }

    def list_models(self, model_type: ModelType | None = None) -> list[ModelMetadata]:
        """List registered models, optionally filtered by type.

        Args:
            model_type: Filter to this type, or None for all.

        Returns:
            List of ModelMetadata.
        """
        if model_type:
            return self._registry.list_by_type(model_type)
        return self._registry.list_models()

    def version_info(self, name: str) -> dict[str, Any] | None:
        """Get version information for a model.

        Args:
            name: Model name.

        Returns:
            Version info dict, or None if not found.
        """
        meta = self._registry.get_metadata(name)
        if meta is None:
            return None
        return {
            "name": meta.name,
            "version": meta.version,
            "status": meta.status.value,
            "created_at": meta.created_at.isoformat(),
            "updated_at": meta.updated_at.isoformat(),
            "artifact_path": meta.artifact_path,
        }
