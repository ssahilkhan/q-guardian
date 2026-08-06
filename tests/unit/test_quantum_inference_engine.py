"""Unit tests for QuantumInferenceEngine — Phase 2."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.data import QuantumInferenceResult
from q_guardian.quantum.exceptions import QuantumInferenceError
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.inference.engine import QuantumInferenceEngine
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.models.qsvm import QSVMModel


@pytest.fixture
def backend() -> LocalSimulatorBackend:
    return LocalSimulatorBackend()


@pytest.fixture
def feature_map() -> AngleEncodingMap:
    return AngleEncodingMap(num_qubits=4)


@pytest.fixture
def kernel(feature_map: AngleEncodingMap, backend: LocalSimulatorBackend) -> QuantumKernelEstimator:
    return QuantumKernelEstimator(feature_map=feature_map, backend=backend)


@pytest.fixture
def engine() -> QuantumInferenceEngine:
    return QuantumInferenceEngine()


@pytest.fixture
def trained_qsvm(kernel: QuantumKernelEstimator, feature_map: AngleEncodingMap) -> QSVMModel:
    import numpy as np

    rng = np.random.default_rng(42)
    x = rng.uniform(-np.pi, np.pi, size=(20, 4)).tolist()
    y = [0 if i < 10 else 1 for i in range(20)]
    qsvm = QSVMModel(kernel=kernel, feature_map=feature_map)
    qsvm.train(x, y)
    return qsvm


@pytest.fixture
def trained_qsvm2(kernel: QuantumKernelEstimator, feature_map: AngleEncodingMap) -> QSVMModel:
    import numpy as np

    rng = np.random.default_rng(99)
    x = rng.uniform(-np.pi, np.pi, size=(20, 4)).tolist()
    y = [0 if i < 10 else 1 for i in range(20)]
    qsvm = QSVMModel(kernel=kernel, feature_map=feature_map, name="qsvm-secondary")
    qsvm.train(x, y)
    return qsvm


class TestEngineConstruction:
    def test_model_count_zero(self, engine: QuantumInferenceEngine):
        assert engine.model_count == 0

    def test_total_inferences_zero(self, engine: QuantumInferenceEngine):
        assert engine.total_inferences == 0

    def test_total_errors_zero(self, engine: QuantumInferenceEngine):
        assert engine.total_errors == 0

    def test_average_latency_zero(self, engine: QuantumInferenceEngine):
        assert engine.average_latency_ms == 0.0

    def test_model_names_empty(self, engine: QuantumInferenceEngine):
        assert engine.model_names == []

    def test_fallback_order_empty(self, engine: QuantumInferenceEngine):
        assert engine.fallback_order == []


class TestEngineRegistration:
    def test_register_model(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        assert engine.model_count == 1
        assert "qsvm" in engine.model_names

    def test_register_with_priority(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm, fallback_priority=0)
        assert engine.fallback_order == ["qsvm"]

    def test_register_multiple(
        self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel, trained_qsvm2: QSVMModel
    ):
        engine.register_model(trained_qsvm, fallback_priority=0)
        engine.register_model(trained_qsvm2, fallback_priority=1)
        assert engine.model_count == 2
        assert len(engine.fallback_order) == 2

    def test_unregister_model(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        assert engine.unregister_model("qsvm") is True
        assert engine.model_count == 0

    def test_unregister_nonexistent(self, engine: QuantumInferenceEngine):
        assert engine.unregister_model("nonexistent") is False

    def test_get_model(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        assert engine.get_model("qsvm") is trained_qsvm

    def test_get_model_nonexistent(self, engine: QuantumInferenceEngine):
        assert engine.get_model("nonexistent") is None


class TestEngineModelSelection:
    def test_select_by_name(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        model = engine.select_model("qsvm")
        assert model is trained_qsvm

    def test_select_auto(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        model = engine.select_model()
        assert model is trained_qsvm

    def test_select_auto_none_available(self, engine: QuantumInferenceEngine):
        model = engine.select_model()
        assert model is None

    def test_select_by_fallback_priority(
        self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel, trained_qsvm2: QSVMModel
    ):
        engine.register_model(trained_qsvm2, fallback_priority=0)
        engine.register_model(trained_qsvm, fallback_priority=1)
        model = engine.select_model()
        assert model is trained_qsvm2

    def test_select_nonexistent_name(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        model = engine.select_model("wrong-name")
        assert model is None


class TestEngineInference:
    async def test_infer_basic(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        result = await engine.infer([1.0, 2.0, 3.0, 4.0])
        assert isinstance(result, QuantumInferenceResult)

    async def test_infer_increments_count(
        self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel
    ):
        engine.register_model(trained_qsvm)
        await engine.infer([1.0, 2.0, 3.0, 4.0])
        assert engine.total_inferences == 1

    async def test_infer_with_model_name(
        self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel
    ):
        engine.register_model(trained_qsvm)
        result = await engine.infer([1.0, 2.0, 3.0, 4.0], model_name="qsvm")
        assert result.model_name == "qsvm"

    async def test_infer_no_model_raises(self, engine: QuantumInferenceEngine):
        with pytest.raises(QuantumInferenceError):
            await engine.infer([1.0, 2.0, 3.0, 4.0])

    async def test_infer_no_model_with_name_raises(self, engine: QuantumInferenceEngine):
        with pytest.raises(QuantumInferenceError):
            await engine.infer([1.0, 2.0, 3.0, 4.0], model_name="nonexistent")


class TestEngineBatchInference:
    async def test_batch_infer_basic(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        results = await engine.infer_batch(
            [
                [1.0, 2.0, 3.0, 4.0],
                [5.0, 6.0, 7.0, 8.0],
            ]
        )
        assert len(results) == 2
        assert all(isinstance(r, QuantumInferenceResult) for r in results)

    async def test_batch_infer_empty(self, engine: QuantumInferenceEngine):
        results = await engine.infer_batch([])
        assert results == []

    async def test_batch_infer_count(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        await engine.infer_batch([[1.0, 2.0, 3.0, 4.0]] * 3)
        assert engine.total_inferences == 3


class TestEngineFallback:
    async def test_fallback_on_error(
        self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel, trained_qsvm2: QSVMModel
    ):
        engine.register_model(trained_qsvm, fallback_priority=0)
        engine.register_model(trained_qsvm2, fallback_priority=1)
        result = await engine.infer([1.0, 2.0, 3.0, 4.0])
        assert isinstance(result, QuantumInferenceResult)

    async def test_fallback_exhausted(self, engine: QuantumInferenceEngine):
        mock_model = MagicMock()
        mock_model.name = "failing-model"
        mock_model.is_trained = True
        mock_model.predict_quantum = AsyncMock(side_effect=RuntimeError("fail"))
        engine.register_model(mock_model, fallback_priority=0)
        result = await engine.infer([1.0, 2.0, 3.0, 4.0])
        assert result.predicted_class == "unknown"
        assert engine.total_errors == 1


class TestEnginePerformanceStats:
    async def test_stats_empty(self, engine: QuantumInferenceEngine):
        stats = engine.get_performance_stats()
        assert stats["total_inferences"] == 0

    async def test_stats_after_inference(
        self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel
    ):
        engine.register_model(trained_qsvm)
        await engine.infer([1.0, 2.0, 3.0, 4.0])
        stats = engine.get_performance_stats()
        assert stats["total_inferences"] == 1
        assert stats["average_latency_ms"] > 0

    async def test_stats_model_usage(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        await engine.infer([1.0, 2.0, 3.0, 4.0])
        stats = engine.get_performance_stats()
        assert "qsvm" in stats["model_usage"]


class TestEngineHistory:
    async def test_clear_history(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        await engine.infer([1.0, 2.0, 3.0, 4.0])
        cleared = engine.clear_history()
        assert cleared == 1
        assert engine.get_performance_stats()["total_inferences"] == 0


class TestEngineHealth:
    def test_health_empty(self, engine: QuantumInferenceEngine):
        h = engine.health()
        assert h["model_count"] == 0
        assert h["trained_models"] == 0

    def test_health_with_models(self, engine: QuantumInferenceEngine, trained_qsvm: QSVMModel):
        engine.register_model(trained_qsvm)
        h = engine.health()
        assert h["model_count"] == 1
        assert h["trained_models"] == 1
        assert "qsvm" in h["models"]
