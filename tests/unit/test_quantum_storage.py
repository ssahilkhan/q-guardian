"""Unit tests for QuantumModelStorage — Phase 2 persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from q_guardian.quantum.storage import QuantumModelStorage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_storage(tmp_path: Path) -> QuantumModelStorage:
    return QuantumModelStorage(tmp_path / "quantum_models")


@pytest.fixture
def sample_state() -> dict:
    return {
        "train_X": [[1.0, 2.0], [3.0, 4.0]],
        "train_y": [0, 1],
        "bias": 0.123,
        "classes": [0, 1],
        "trained": True,
    }


@pytest.fixture
def sample_metadata() -> dict:
    return {
        "model_name": "test-model",
        "version": "1.0.0",
        "created_by": "test",
    }


class TestStorageConstruction:
    def test_root_created(self, tmp_path: Path):
        storage = QuantumModelStorage(tmp_path / "new_dir")
        assert storage.root.exists()
        assert storage.root.is_dir()

    def test_root_property(self, tmp_storage: QuantumModelStorage, tmp_path: Path):
        assert tmp_storage.root == tmp_path / "quantum_models"

    def test_model_dir(self, tmp_storage: QuantumModelStorage):
        d = tmp_storage.model_dir("my-model")
        assert d.name == "my-model"


class TestStorageSaveLoad:
    def test_save_creates_files(
        self, tmp_storage: QuantumModelStorage, sample_state: dict, sample_metadata: dict
    ):
        tmp_storage.save("test-model", sample_state, sample_metadata)
        assert (tmp_storage.model_dir("test-model") / "model_state.json").exists()
        assert (tmp_storage.model_dir("test-model") / "model_metadata.json").exists()

    def test_save_with_version(
        self, tmp_storage: QuantumModelStorage, sample_state: dict, sample_metadata: dict
    ):
        path = tmp_storage.save("test-model", sample_state, sample_metadata, version="1.0.0")
        assert path.exists()
        versions_dir = tmp_storage.model_dir("test-model") / "versions"
        assert versions_dir.exists()
        assert (versions_dir / "1.0.0.json").exists()

    def test_load_state(self, tmp_storage: QuantumModelStorage, sample_state: dict):
        tmp_storage.save("test-model", sample_state)
        loaded = tmp_storage.load("test-model")
        assert loaded["bias"] == 0.123
        assert loaded["trained"] is True

    def test_load_nonexistent_raises(self, tmp_storage: QuantumModelStorage):
        from q_guardian.quantum.exceptions import QuantumError

        with pytest.raises(QuantumError, match="not found"):
            tmp_storage.load("nonexistent")

    def test_load_version(
        self, tmp_storage: QuantumModelStorage, sample_state: dict, sample_metadata: dict
    ):
        tmp_storage.save("test-model", sample_state, sample_metadata, version="1.0.0")
        version_data = tmp_storage.load_version("test-model", "1.0.0")
        assert "state" in version_data
        assert "metadata" in version_data

    def test_load_version_nonexistent(self, tmp_storage: QuantumModelStorage):
        from q_guardian.quantum.exceptions import QuantumError

        with pytest.raises(QuantumError, match="not found"):
            tmp_storage.load_version("test-model", "9.9.9")

    def test_load_metadata(
        self, tmp_storage: QuantumModelStorage, sample_state: dict, sample_metadata: dict
    ):
        tmp_storage.save("test-model", sample_state, sample_metadata)
        meta = tmp_storage.load_metadata("test-model")
        assert meta["model_name"] == "test-model"
        assert meta["version"] == "1.0.0"

    def test_load_metadata_nonexistent(self, tmp_storage: QuantumModelStorage):
        meta = tmp_storage.load_metadata("nonexistent")
        assert meta == {}


class TestStorageExists:
    def test_exists_true(self, tmp_storage: QuantumModelStorage, sample_state: dict):
        tmp_storage.save("test-model", sample_state)
        assert tmp_storage.exists("test-model") is True

    def test_exists_false(self, tmp_storage: QuantumModelStorage):
        assert tmp_storage.exists("nonexistent") is False


class TestStorageListModels:
    def test_list_empty(self, tmp_storage: QuantumModelStorage):
        models = tmp_storage.list_models()
        assert models == []

    def test_list_one(
        self, tmp_storage: QuantumModelStorage, sample_state: dict, sample_metadata: dict
    ):
        tmp_storage.save("model-a", sample_state, sample_metadata, version="1.0.0")
        models = tmp_storage.list_models()
        assert len(models) == 1
        assert models[0]["name"] == "model-a"
        assert models[0]["has_state"] is True
        assert "1.0.0" in models[0]["versions"]

    def test_list_multiple(self, tmp_storage: QuantumModelStorage, sample_state: dict):
        tmp_storage.save("model-a", sample_state)
        tmp_storage.save("model-b", sample_state)
        models = tmp_storage.list_models()
        assert len(models) == 2
        names = {m["name"] for m in models}
        assert "model-a" in names
        assert "model-b" in names


class TestStorageDelete:
    def test_delete(self, tmp_storage: QuantumModelStorage, sample_state: dict):
        tmp_storage.save("test-model", sample_state)
        assert tmp_storage.delete("test-model") is True
        assert tmp_storage.exists("test-model") is False

    def test_delete_nonexistent(self, tmp_storage: QuantumModelStorage):
        assert tmp_storage.delete("nonexistent") is False


class TestStorageRollback:
    def test_rollback(
        self, tmp_storage: QuantumModelStorage, sample_state: dict, sample_metadata: dict
    ):
        tmp_storage.save("test-model", sample_state, sample_metadata, version="1.0.0")

        new_state = {**sample_state, "bias": 0.999}
        tmp_storage.save("test-model", new_state, sample_metadata, version="2.0.0")

        loaded_v1 = tmp_storage.load("test-model")
        assert loaded_v1["bias"] == 0.999

        result = tmp_storage.rollback("test-model", "1.0.0")
        assert result is True

        loaded_after = tmp_storage.load("test-model")
        assert loaded_after["bias"] == 0.123


class TestStorageStats:
    def test_stats_empty(self, tmp_storage: QuantumModelStorage):
        stats = tmp_storage.get_storage_stats()
        assert stats["model_count"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["total_versions"] == 0

    def test_stats_with_models(
        self, tmp_storage: QuantumModelStorage, sample_state: dict, sample_metadata: dict
    ):
        tmp_storage.save("model-a", sample_state, sample_metadata, version="1.0.0")
        tmp_storage.save("model-b", sample_state, sample_metadata, version="1.0.0")
        stats = tmp_storage.get_storage_stats()
        assert stats["model_count"] == 2
        assert stats["total_size_bytes"] > 0
        assert stats["total_versions"] == 2
