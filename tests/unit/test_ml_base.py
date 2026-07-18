"""Tests for BaseThreatModel and ModelRegistry."""

from __future__ import annotations

from typing import Any

import pytest

from q_guardian.ml.base import BaseThreatModel, ModelRegistry
from q_guardian.ml.data import ModelMetadata
from q_guardian.ml.enums import ModelBackend, ModelStatus, ModelType


class DummyThreatModel(BaseThreatModel):
    """Minimal concrete implementation for testing."""

    def __init__(self, name: str = "dummy") -> None:
        self._metadata = ModelMetadata(
            name=name,
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.CUSTOM,
        )

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    async def predict(self, features: list[float]) -> dict[str, Any]:
        return {"prediction": "benign", "confidence": 0.8}


class TestBaseThreatModel:
    @pytest.mark.asyncio
    async def test_predict(self) -> None:
        model = DummyThreatModel()
        result = await model.predict([1.0, 2.0, 3.0])
        assert result["prediction"] == "benign"

    def test_health(self) -> None:
        model = DummyThreatModel(name="test-health")
        h = model.health()
        assert h["status"] == "healthy"
        assert h["model"] == "test-health"

    def test_metadata(self) -> None:
        model = DummyThreatModel("my-model")
        assert model.metadata.name == "my-model"
        assert model.metadata.model_type == ModelType.CLASSIFICATION


class TestModelRegistry:
    def setup_method(self) -> None:
        self.registry = ModelRegistry()

    def test_register_and_get(self) -> None:
        model = DummyThreatModel("reg-test")
        self.registry.register(model)
        assert self.registry.get("reg-test") is model

    def test_get_metadata(self) -> None:
        model = DummyThreatModel("meta-test")
        self.registry.register(model)
        meta = self.registry.get_metadata("meta-test")
        assert meta is not None
        assert meta.name == "meta-test"

    def test_unregister(self) -> None:
        model = DummyThreatModel("unreg")
        self.registry.register(model)
        assert self.registry.unregister("unreg") is True
        assert self.registry.get("unreg") is None

    def test_unregister_nonexistent(self) -> None:
        assert self.registry.unregister("nope") is False

    def test_list_models(self) -> None:
        self.registry.register(DummyThreatModel("a"))
        self.registry.register(DummyThreatModel("b"))
        models = self.registry.list_models()
        assert len(models) == 2

    def test_list_by_type(self) -> None:
        self.registry.register(DummyThreatModel("cls"))
        models = self.registry.list_by_type(ModelType.CLASSIFICATION)
        assert len(models) == 1

    def test_list_by_backend(self) -> None:
        self.registry.register(DummyThreatModel("cust"))
        models = self.registry.list_by_backend(ModelBackend.CUSTOM)
        assert len(models) == 1

    def test_count(self) -> None:
        assert self.registry.count() == 0
        self.registry.register(DummyThreatModel("c1"))
        assert self.registry.count() == 1

    def test_clear(self) -> None:
        self.registry.register(DummyThreatModel("x"))
        self.registry.register(DummyThreatModel("y"))
        self.registry.clear()
        assert self.registry.count() == 0

    def test_get_nonexistent(self) -> None:
        assert self.registry.get("missing") is None
