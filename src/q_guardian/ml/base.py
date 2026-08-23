"""Base classes for ML threat models and model registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from q_guardian.ml.data import ModelMetadata
    from q_guardian.ml.enums import ModelBackend, ModelType

logger = structlog.get_logger("ml.base")

# Canonical 12-dim handcrafted feature contract used by every classical model
# at inference time. Training pipelines MUST supply vectors built by the same
# extractor; MLFeatureProvider.extract_vector() serves a different, richer
# 43-dim space intended for research/training experiments only.
CORE_FEATURE_NAMES: list[str] = [
    "length",
    "word_count",
    "line_count",
    "token_estimate",
    "entropy",
    "uppercase_ratio",
    "digit_ratio",
    "special_char_count",
    "code_block_count",
    "url_count",
    "suspicious_keyword_count",
    "repeated_pattern_count",
]


def extract_core_features(features: Any) -> list[float]:
    """Build the canonical 12-dim numeric vector from prompt features.

    This is the single source of truth for the classical-model feature space.
    ``IsolationForestDetector``, ``RandomForestThreatClassifier`` and
    ``XGBoostThreatClassifier`` all consume it via their ``_extract_vector``
    helpers, keeping train/inference dimensions consistent.

    Args:
        features: PromptFeatures instance (typed as Any to avoid a circular
            schema import at module load).

    Returns:
        Numeric vector ordered exactly as ``CORE_FEATURE_NAMES``.
    """
    return [
        float(features.length),
        float(features.word_count),
        float(features.line_count),
        float(features.token_estimate),
        features.entropy,
        features.uppercase_ratio,
        features.digit_ratio,
        float(features.special_char_count),
        float(features.code_block_count),
        float(features.url_count),
        float(len(features.suspicious_keywords)),
        float(len(features.repeated_patterns)),
    ]


def validate_feature_dimension(model_name: str, expected: int, got: int) -> None:
    """Raise an actionable error when a feature vector's width is wrong.

    Args:
        model_name: Human-readable model name for the error message.
        expected: Dimensionality the trained estimator requires.
        got: Dimensionality of the incoming vector.

    Raises:
        ValueError: Always, when called (i.e. when a mismatch was detected).
    """
    raise ValueError(
        f"{model_name}: feature dimension mismatch - estimator expects "
        f"{expected} values but received {got}. Train with vectors produced "
        f"by q_guardian.ml.base.extract_core_features (see CORE_FEATURE_NAMES)."
    )


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

    @property
    def model(self) -> Any:
        """Return the underlying trained estimator, if available.

        Returns:
            The scikit-learn compatible estimator, or None when untrained.
        """
        return None

    def train(self, x: list[list[float]], y: list[int] | None = None) -> None:
        """Train the model on feature vectors.

        Args:
            x: Feature vectors.
            y: Optional class labels; required for supervised models.
        """
        raise NotImplementedError

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
