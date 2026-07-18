"""Tests for ModelStorage."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from q_guardian.ml.data import ModelMetadata
from q_guardian.ml.enums import ModelBackend, ModelStatus, ModelType
from q_guardian.ml.storage import ModelStorage


class DummySklearnModel:
    """Minimal mock sklearn model for serialization testing."""
    def predict(self, X):
        return [0] * len(X)


class TestModelStorage:
    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.storage = ModelStorage(base_path=self.tmpdir)

    def test_base_path(self) -> None:
        assert self.storage.base_path.exists()

    def test_save_and_load(self) -> None:
        meta = ModelMetadata(
            name="test-model",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.SKLEARN,
        )
        model = DummySklearnModel()
        path = self.storage.save(model, meta)
        assert path
        assert meta.artifact_path == path
        assert meta.status == ModelStatus.READY

        loaded = self.storage.load(meta)
        assert loaded is not None
        assert hasattr(loaded, "predict")

    def test_load_no_path(self) -> None:
        meta = ModelMetadata(
            name="no-path",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.SKLEARN,
        )
        with pytest.raises(ValueError):
            self.storage.load(meta)

    def test_load_nonexistent(self) -> None:
        meta = ModelMetadata(
            name="nonexist",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.SKLEARN,
            artifact_path="/fake/path/model.joblib",
        )
        with pytest.raises(FileNotFoundError):
            self.storage.load(meta)

    def test_delete(self) -> None:
        meta = ModelMetadata(
            name="del-model",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.SKLEARN,
        )
        model = DummySklearnModel()
        self.storage.save(model, meta)
        assert self.storage.delete(meta) is True

    def test_delete_no_path(self) -> None:
        meta = ModelMetadata(
            name="del-no-path",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.SKLEARN,
        )
        assert self.storage.delete(meta) is False

    def test_exists(self) -> None:
        meta = ModelMetadata(
            name="exists-model",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.SKLEARN,
        )
        model = DummySklearnModel()
        self.storage.save(model, meta)
        assert self.storage.exists(meta) is True

    def test_exists_no_path(self) -> None:
        meta = ModelMetadata(
            name="nope",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.SKLEARN,
        )
        assert self.storage.exists(meta) is False

    def test_list_artifacts(self) -> None:
        meta = ModelMetadata(
            name="list-model",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.SKLEARN,
        )
        model = DummySklearnModel()
        self.storage.save(model, meta)
        artifacts = self.storage.list_artifacts()
        assert len(artifacts) == 1
