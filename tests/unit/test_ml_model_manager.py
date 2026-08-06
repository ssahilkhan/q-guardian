"""Tests for ModelManager."""

from __future__ import annotations

import tempfile
from typing import Any

from q_guardian.ml.base import BaseThreatModel
from q_guardian.ml.data import ModelMetadata
from q_guardian.ml.enums import ModelBackend, ModelType
from q_guardian.ml.models.model_manager import ModelManager
from q_guardian.ml.storage import ModelStorage


class DummyModel(BaseThreatModel):
    def __init__(self, name: str = "dummy") -> None:
        self._metadata = ModelMetadata(
            name=name,
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.CUSTOM,
        )
        self._model = None

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    async def predict(self, features: list[float]) -> dict[str, Any]:
        return {}


class TestModelManager:
    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.storage = ModelStorage(base_path=self.tmpdir)
        self.manager = ModelManager(storage=self.storage)

    def test_register_model(self) -> None:
        model = DummyModel("mgr-test")
        self.manager.register_model(model)
        assert self.manager.registry.count() == 1

    def test_unregister_model(self) -> None:
        model = DummyModel("mgr-unreg")
        self.manager.register_model(model)
        assert self.manager.unregister_model("mgr-unreg") is True
        assert self.manager.registry.count() == 0

    def test_get_model(self) -> None:
        model = DummyModel("mgr-get")
        self.manager.register_model(model)
        got = self.manager.get_model("mgr-get")
        assert got is model

    def test_get_nonexistent(self) -> None:
        assert self.manager.get_model("missing") is None

    def test_list_models(self) -> None:
        self.manager.register_model(DummyModel("a"))
        self.manager.register_model(DummyModel("b"))
        models = self.manager.list_models()
        assert len(models) == 2

    def test_list_by_type(self) -> None:
        self.manager.register_model(DummyModel("t"))
        models = self.manager.list_models(model_type=ModelType.CLASSIFICATION)
        assert len(models) == 1

    def test_health(self) -> None:
        self.manager.register_model(DummyModel("h1"))
        h = self.manager.health()
        assert h["total_models"] == 1

    def test_version_info(self) -> None:
        self.manager.register_model(DummyModel("vi"))
        info = self.manager.version_info("vi")
        assert info is not None
        assert info["name"] == "vi"

    def test_version_info_nonexistent(self) -> None:
        assert self.manager.version_info("missing") is None

    def test_unload_model(self) -> None:
        model = DummyModel("ul")
        self.manager.register_model(model)
        self.manager._loaded_models["ul"] = model
        assert self.manager.unload_model("ul") is True
        assert "ul" not in self.manager._loaded_models

    def test_unload_nonexistent(self) -> None:
        assert self.manager.unload_model("nope") is False
