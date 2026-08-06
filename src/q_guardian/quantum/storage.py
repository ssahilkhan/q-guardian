"""QuantumModelStorage — persistence layer for quantum models.

Handles serialization, versioning, and disk persistence of quantum
model state. Follows the same pattern as
q_guardian.ml.storage.ModelStorage.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import structlog

from q_guardian.quantum.exceptions import QuantumError

logger = structlog.get_logger("quantum.storage")

METADATA_FILENAME = "model_metadata.json"
STATE_FILENAME = "model_state.json"
VERSIONS_DIR = "versions"


class QuantumModelStorage:
    """Handles persistence for quantum models.

    Directory layout:
      storage_root/
        <model_name>/
          model_metadata.json
          model_state.json
          versions/
            <version_1>.json
            <version_2>.json

    Supports:
      - Save / load model state
      - Version management with rollback
      - Metadata-only persistence
      - Bulk listing of stored models
    """

    def __init__(self, storage_root: str | Path) -> None:
        self._root = Path(storage_root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def model_dir(self, model_name: str) -> Path:
        """Get the directory for a specific model."""
        return self._root / model_name

    def save(
        self,
        model_name: str,
        state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        version: str | None = None,
    ) -> Path:
        """Save model state and metadata to disk."""
        model_path = self.model_dir(model_name)
        model_path.mkdir(parents=True, exist_ok=True)

        state_file = model_path / STATE_FILENAME
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)

        if metadata is None:
            metadata = {}
        metadata.setdefault("saved_at", time.time())
        metadata.setdefault("model_name", model_name)
        metadata.setdefault("version", version or "latest")

        meta_file = model_path / METADATA_FILENAME
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)

        if version is not None:
            self._save_version(model_name, version, state, metadata)

        logger.info(
            "quantum_model_saved",
            model_name=model_name,
            version=version,
            path=str(model_path),
        )

        return model_path

    def load(self, model_name: str) -> dict[str, Any]:
        """Load model state from disk."""
        model_path = self.model_dir(model_name)
        state_file = model_path / STATE_FILENAME

        if not state_file.exists():
            raise QuantumError(
                f"Model state not found: {model_name}",
            )

        with open(state_file, encoding="utf-8") as f:
            state: dict[str, Any] = json.load(f)
            return state

    def load_version(self, model_name: str, version: str) -> dict[str, Any]:
        """Load a specific versioned model state."""
        version_file = self.model_dir(model_name) / VERSIONS_DIR / f"{version}.json"
        if not version_file.exists():
            raise QuantumError(
                f"Version {version} not found for model {model_name}",
            )

        with open(version_file, encoding="utf-8") as f:
            state: dict[str, Any] = json.load(f)
            return state

    def load_metadata(self, model_name: str) -> dict[str, Any]:
        """Load model metadata from disk."""
        model_path = self.model_dir(model_name)
        meta_file = model_path / METADATA_FILENAME

        if not meta_file.exists():
            return {}

        with open(meta_file, encoding="utf-8") as f:
            metadata: dict[str, Any] = json.load(f)
            return metadata

    def exists(self, model_name: str) -> bool:
        """Check if a model is stored."""
        state_file = self.model_dir(model_name) / STATE_FILENAME
        return state_file.exists()

    def list_models(self) -> list[dict[str, Any]]:
        """List all stored models with their metadata."""
        models: list[dict[str, Any]] = []

        if not self._root.exists():
            return models

        for entry in sorted(self._root.iterdir()):
            if entry.is_dir():
                meta_file = entry / METADATA_FILENAME
                metadata: dict[str, Any] = {}
                if meta_file.exists():
                    try:
                        with open(meta_file, encoding="utf-8") as f:
                            metadata = json.load(f)
                    except (json.JSONDecodeError, OSError):
                        pass

                versions = self._list_versions(entry.name)

                models.append(
                    {
                        "name": entry.name,
                        "metadata": metadata,
                        "versions": versions,
                        "has_state": (entry / STATE_FILENAME).exists(),
                    }
                )

        return models

    def delete(self, model_name: str) -> bool:
        """Delete a stored model."""
        model_path = self.model_dir(model_name)
        if not model_path.exists():
            return False

        shutil.rmtree(model_path)
        logger.info("quantum_model_deleted", model_name=model_name)
        return True

    def rollback(self, model_name: str, target_version: str) -> bool:
        """Rollback a model to a specific version."""
        version_data = self.load_version(model_name, target_version)
        state = version_data.get("state", version_data)
        metadata = version_data.get("metadata", {})

        metadata["rolled_back_from"] = target_version
        metadata["rollback_time"] = time.time()

        self.save(model_name, state, metadata, version=target_version)
        logger.info(
            "quantum_model_rollback",
            model_name=model_name,
            version=target_version,
        )
        return True

    def get_storage_stats(self) -> dict[str, Any]:
        """Return storage statistics."""
        total_size = 0
        model_count = 0
        total_versions = 0

        if self._root.exists():
            for entry in self._root.iterdir():
                if entry.is_dir():
                    model_count += 1
                    for file in entry.rglob("*"):
                        if file.is_file():
                            total_size += file.stat().st_size
                    versions_dir = entry / VERSIONS_DIR
                    if versions_dir.exists():
                        total_versions += sum(1 for _ in versions_dir.iterdir())

        return {
            "storage_root": str(self._root),
            "model_count": model_count,
            "total_size_bytes": total_size,
            "total_versions": total_versions,
        }

    def _save_version(
        self,
        model_name: str,
        version: str,
        state: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        """Save a versioned snapshot."""
        versions_dir = self.model_dir(model_name) / VERSIONS_DIR
        versions_dir.mkdir(parents=True, exist_ok=True)

        version_data = {
            "state": state,
            "metadata": {**metadata, "version": version, "saved_at": time.time()},
        }

        version_file = versions_dir / f"{version}.json"
        with open(version_file, "w", encoding="utf-8") as f:
            json.dump(version_data, f, indent=2, default=str)

    def _list_versions(self, model_name: str) -> list[str]:
        """List available versions for a model."""
        versions_dir = self.model_dir(model_name) / VERSIONS_DIR
        if not versions_dir.exists():
            return []

        return sorted(f.stem for f in versions_dir.iterdir() if f.is_file() and f.suffix == ".json")
