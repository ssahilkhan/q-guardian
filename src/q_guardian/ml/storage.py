"""Model storage using joblib for persistence."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

from q_guardian.ml.enums import ModelStatus
from q_guardian.ml.data import ModelMetadata

logger = structlog.get_logger("ml.storage")


class ModelStorage:
    """Handles saving and loading ML model artifacts.

    Uses joblib for serialization. Supports versioned storage
    with automatic artifact path management.
    """

    def __init__(self, base_path: str | Path = "models/ml") -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._base_path

    def save(
        self,
        model: Any,
        metadata: ModelMetadata,
    ) -> str:
        """Save a model artifact and update metadata.

        Args:
            model: The trained model object (sklearn/xgboost/etc.).
            metadata: Model metadata to update with artifact path.

        Returns:
            Path to the saved artifact.
        """
        import joblib

        model_dir = self._base_path / metadata.name
        model_dir.mkdir(parents=True, exist_ok=True)

        artifact_path = model_dir / f"{metadata.name}_v{metadata.version}.joblib"
        joblib.dump(model, artifact_path)

        metadata.artifact_path = str(artifact_path)
        metadata.status = ModelStatus.READY
        metadata.updated_at = metadata.updated_at.__class__.now(
            metadata.updated_at.tzinfo
        )

        logger.info(
            "model_saved",
            model_name=metadata.name,
            version=metadata.version,
            path=str(artifact_path),
        )
        return str(artifact_path)

    def load(self, metadata: ModelMetadata) -> Any:
        """Load a model artifact from disk.

        Args:
            metadata: Model metadata with artifact_path set.

        Returns:
            The deserialized model object.

        Raises:
            FileNotFoundError: If the artifact doesn't exist.
            ValueError: If artifact_path is empty.
        """
        import joblib

        if not metadata.artifact_path:
            msg = f"Model '{metadata.name}' has no artifact_path"
            raise ValueError(msg)

        artifact_path = Path(metadata.artifact_path)
        if not artifact_path.exists():
            msg = f"Model artifact not found: {artifact_path}"
            raise FileNotFoundError(msg)

        model = joblib.load(artifact_path)
        metadata.status = ModelStatus.READY

        logger.info("model_loaded", model_name=metadata.name, path=str(artifact_path))
        return model

    def delete(self, metadata: ModelMetadata) -> bool:
        """Delete a model artifact from disk.

        Args:
            metadata: Model metadata.

        Returns:
            True if the artifact was found and deleted.
        """
        if not metadata.artifact_path:
            return False

        artifact_path = Path(metadata.artifact_path)
        if artifact_path.exists():
            artifact_path.unlink()
            logger.info("model_deleted", model_name=metadata.name, path=str(artifact_path))
            return True
        return False

    def exists(self, metadata: ModelMetadata) -> bool:
        """Check if a model artifact exists on disk."""
        if not metadata.artifact_path:
            return False
        return Path(metadata.artifact_path).exists()

    def list_artifacts(self) -> list[str]:
        """List all saved model artifact paths.

        Returns:
            List of artifact file paths.
        """
        artifacts: list[str] = []
        if self._base_path.exists():
            for joblib_file in self._base_path.rglob("*.joblib"):
                artifacts.append(str(joblib_file))
        return artifacts
