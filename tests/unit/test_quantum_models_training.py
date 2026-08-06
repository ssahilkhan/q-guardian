"""Tests for BaseQuantumModel, QuantumTrainer, QuantumEvaluator."""

from __future__ import annotations

from typing import Any

import pytest

from q_guardian.quantum.config import QuantumTrainingConfig
from q_guardian.quantum.data import QuantumInferenceResult, QuantumModelMetadata
from q_guardian.quantum.enums import QuantumBackendType, QuantumModelType
from q_guardian.quantum.evaluation.metrics import QuantumEvaluator
from q_guardian.quantum.models.base import BaseQuantumModel
from q_guardian.quantum.training.trainer import QuantumTrainer


class SimpleQuantumModel(BaseQuantumModel):
    """Concrete quantum model for testing."""

    def __init__(self, name: str = "simple-qm") -> None:
        self._name = name
        self._trained = False
        self._weights: list[float] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def metadata(self) -> Any:
        from q_guardian.ml.data import ModelMetadata

        return ModelMetadata(name=self._name, model_type="classification", backend="custom")

    @property
    def quantum_metadata(self) -> QuantumModelMetadata:
        return QuantumModelMetadata(
            name=self._name,
            model_type=QuantumModelType.VQC,
            backend_type=QuantumBackendType.LOCAL,
            num_qubits=4,
        )

    @property
    def is_trained(self) -> bool:
        return self._trained

    def train(self, x: list[list[float]], y: list[int] | None = None) -> None:
        self._trained = True
        if x:
            self._weights = [sum(row) / len(row) for row in zip(*x, strict=False)]

    async def predict(self, features: list[float]) -> dict[str, Any]:
        if not self._trained:
            return {"predicted_class": "unknown", "confidence": 0.0}
        score = (
            sum(f * w for f, w in zip(features, self._weights, strict=False))
            if self._weights
            else 0.0
        )
        return {
            "predicted_class": "benign" if score > 0 else "injection",
            "confidence": min(abs(score), 1.0),
        }

    async def predict_quantum(self, features: list[float]) -> QuantumInferenceResult:
        result = await self.predict(features)
        return QuantumInferenceResult(
            model_name=self._name,
            predictions={result["predicted_class"]: result.get("confidence", 0.0)},
            predicted_class=result["predicted_class"],
            confidence=result.get("confidence", 0.0),
        )

    async def classify_quantum(self, prompt: str, features: Any) -> Any:
        from q_guardian.security.extensibility import DetectionResult

        return DetectionResult(detector_name=self._name)


class TestBaseQuantumModel:
    def test_interface_contract(self) -> None:
        model = SimpleQuantumModel("test-model")
        assert model.name == "test-model"
        assert model.is_trained is False

    def test_quantum_metadata(self) -> None:
        model = SimpleQuantumModel("qm-test")
        qm = model.quantum_metadata
        assert qm.model_type == QuantumModelType.VQC
        assert qm.num_qubits == 4

    @pytest.mark.asyncio
    async def test_predict_before_training(self) -> None:
        model = SimpleQuantumModel()
        result = await model.predict([1.0, 2.0])
        assert result["predicted_class"] == "unknown"

    @pytest.mark.asyncio
    async def test_predict_after_training(self) -> None:
        model = SimpleQuantumModel()
        model.train([[1.0, 2.0], [3.0, 4.0]], [0, 1])
        assert model.is_trained is True
        result = await model.predict([1.0, 2.0])
        assert "predicted_class" in result
        assert result["confidence"] >= 0.0

    @pytest.mark.asyncio
    async def test_predict_quantum(self) -> None:
        model = SimpleQuantumModel()
        model.train([[1.0, 2.0], [3.0, 4.0]], [0, 1])
        result = await model.predict_quantum([1.0, 2.0])
        assert isinstance(result, QuantumInferenceResult)
        assert result.model_name == "simple-qm"

    @pytest.mark.asyncio
    async def test_classify_quantum(self) -> None:
        model = SimpleQuantumModel()
        result = await model.classify_quantum("test prompt", None)
        assert result.detector_name == "simple-qm"

    def test_health(self) -> None:
        model = SimpleQuantumModel("health-test")
        h = model.health()
        assert h["status"] == "healthy"
        assert h["quantum_model_type"] == "vqc"
        assert h["num_qubits"] == 4
        assert h["is_trained"] is False

    def test_metadata_property(self) -> None:
        model = SimpleQuantumModel("meta-test")
        m = model.metadata
        assert m.name == "meta-test"


class TestQuantumTrainer:
    def setup_method(self) -> None:
        self.trainer = QuantumTrainer()

    def test_default_config(self) -> None:
        assert self.trainer.config.optimizer.value == "cobyla"
        assert self.trainer.config.max_iterations == 100

    def test_train_supervised(self) -> None:
        model = SimpleQuantumModel()
        x = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
        y = [0, 1, 1]
        result = self.trainer.train(model, x, y)
        assert result.status == "completed"
        assert model.is_trained is True

    def test_train_with_validation(self) -> None:
        model = SimpleQuantumModel()
        x_train = [[1.0, 2.0], [3.0, 4.0]]
        y_train = [0, 1]
        x_val = [[1.0, 2.0], [3.0, 4.0]]
        y_val = [0, 1]
        result = self.trainer.train(model, x_train, y_train, x_val, y_val)
        assert result.status == "completed"

    def test_cross_validate(self) -> None:
        model = SimpleQuantumModel()
        x = [[float(i), float(i + 1)] for i in range(10)]
        y = [0, 1] * 5
        result = self.trainer.cross_validate(model, x, y, n_folds=3)
        assert result.status == "completed"
        assert len(result.cv_scores) > 0
        assert result.cv_mean >= 0.0

    def test_custom_config(self) -> None:
        config = QuantumTrainingConfig(max_iterations=50)
        trainer = QuantumTrainer(config)
        assert trainer.config.max_iterations == 50


class TestQuantumEvaluator:
    def setup_method(self) -> None:
        self.evaluator = QuantumEvaluator()

    def test_evaluate(self) -> None:
        model = SimpleQuantumModel()
        model.train([[1.0, 2.0], [3.0, 4.0]], [0, 1])
        x_test = [[1.0, 2.0], [3.0, 4.0]]
        y_test = [0, 1]
        metrics = self.evaluator.evaluate(model, x_test, y_test)
        assert 0.0 <= metrics.accuracy <= 1.0
        assert metrics.circuit_width == 4

    def test_compare_models(self) -> None:
        m1 = SimpleQuantumModel("model-a")
        m2 = SimpleQuantumModel("model-b")
        m1.train([[1.0, 2.0], [3.0, 4.0]], [0, 1])
        m2.train([[1.0, 2.0], [3.0, 4.0]], [0, 1])
        x_test = [[1.0, 2.0]]
        y_test = [0]
        results = self.evaluator.compare_models([m1, m2], x_test, y_test)
        assert "model-a" in results
        assert "model-b" in results

    def test_evaluate_empty_data(self) -> None:
        model = SimpleQuantumModel()
        model.train([[1.0, 2.0]], [0])
        metrics = self.evaluator.evaluate(model, [], [])
        assert metrics.accuracy == 0.0
