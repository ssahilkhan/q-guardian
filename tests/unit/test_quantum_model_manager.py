"""Unit tests for QuantumModelManager — Phase 2."""

from __future__ import annotations

import pytest
import numpy as np

from q_guardian.quantum.models.manager import QuantumModelManager, ModelRegistration
from q_guardian.quantum.models.qsvm import QSVMModel
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.enums import QuantumModelType


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
def manager() -> QuantumModelManager:
    return QuantumModelManager()


@pytest.fixture
def qsvm(kernel: QuantumKernelEstimator, feature_map: AngleEncodingMap) -> QSVMModel:
    return QSVMModel(kernel=kernel, feature_map=feature_map, name="qsvm-1")


@pytest.fixture
def qsvm2(kernel: QuantumKernelEstimator, feature_map: AngleEncodingMap) -> QSVMModel:
    return QSVMModel(kernel=kernel, feature_map=feature_map, name="qsvm-2")


@pytest.fixture
def trained_qsvm(kernel: QuantumKernelEstimator, feature_map: AngleEncodingMap) -> QSVMModel:
    rng = np.random.default_rng(42)
    X = rng.uniform(-np.pi, np.pi, size=(20, 4)).tolist()
    y = [0 if i < 10 else 1 for i in range(20)]
    qsvm = QSVMModel(kernel=kernel, feature_map=feature_map, name="qsvm-trained")
    qsvm.train(X, y)
    return qsvm


class TestManagerConstruction:
    def test_model_count_zero(self, manager: QuantumModelManager):
        assert manager.model_count == 0

    def test_model_names_empty(self, manager: QuantumModelManager):
        assert manager.model_names == []


class TestManagerRegistration:
    def test_register(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        assert manager.model_count == 1
        assert "qsvm-1" in manager.model_names

    def test_register_with_tags(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm, tags=["production", "v1"])
        reg = manager.get_registration("qsvm-1")
        assert reg is not None
        assert "production" in reg.tags

    def test_register_with_metadata(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm, metadata={"author": "test"})
        reg = manager.get_registration("qsvm-1")
        assert reg is not None
        assert reg.metadata["author"] == "test"

    def test_register_duplicate_no_op(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        manager.register(qsvm)
        assert manager.model_count == 1

    def test_unregister(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        assert manager.unregister("qsvm-1") is True
        assert manager.model_count == 0

    def test_unregister_nonexistent(self, manager: QuantumModelManager):
        assert manager.unregister("nonexistent") is False

    def test_get_model(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        assert manager.get("qsvm-1") is qsvm

    def test_get_nonexistent(self, manager: QuantumModelManager):
        assert manager.get("nonexistent") is None

    def test_get_metadata(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        meta = manager.get_metadata("qsvm-1")
        assert meta is not None
        assert meta.name == "qsvm-1"

    def test_get_metadata_nonexistent(self, manager: QuantumModelManager):
        assert manager.get_metadata("nonexistent") is None


class TestManagerListModels:
    def test_list_all(self, manager: QuantumModelManager, qsvm: QSVMModel, qsvm2: QSVMModel):
        manager.register(qsvm)
        manager.register(qsvm2)
        result = manager.list_models()
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert "qsvm-1" in names
        assert "qsvm-2" in names

    def test_list_trained_only(self, manager: QuantumModelManager, qsvm: QSVMModel, trained_qsvm: QSVMModel):
        manager.register(qsvm)
        manager.register(trained_qsvm)
        result = manager.list_models(trained_only=True)
        assert len(result) == 1
        assert result[0]["name"] == "qsvm-trained"

    def test_list_by_model_type(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        result = manager.list_models(model_type=QuantumModelType.QSVM)
        assert len(result) == 1

    def test_list_by_model_type_wrong(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        result = manager.list_models(model_type=QuantumModelType.VQC)
        assert len(result) == 0

    def test_list_by_tags(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm, tags=["production"])
        result = manager.list_models(tags=["production"])
        assert len(result) == 1

    def test_list_by_tags_no_match(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm, tags=["production"])
        result = manager.list_models(tags=["staging"])
        assert len(result) == 0


class TestManagerInferenceRecording:
    def test_record_inference(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        manager.record_inference("qsvm-1")
        reg = manager.get_registration("qsvm-1")
        assert reg is not None
        assert reg.inference_count == 1

    def test_record_inference_error(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        manager.record_inference("qsvm-1", success=False)
        reg = manager.get_registration("qsvm-1")
        assert reg is not None
        assert reg.error_count == 1

    def test_record_inference_nonexistent(self, manager: QuantumModelManager):
        manager.record_inference("nonexistent")


class TestManagerBestModel:
    def test_get_best_model_none_trained(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        assert manager.get_best_model() is None

    def test_get_best_model(self, manager: QuantumModelManager, trained_qsvm: QSVMModel):
        manager.register(trained_qsvm)
        best = manager.get_best_model()
        assert best is trained_qsvm

    def test_get_best_model_by_type(self, manager: QuantumModelManager, trained_qsvm: QSVMModel):
        manager.register(trained_qsvm)
        best = manager.get_best_model(model_type=QuantumModelType.QSVM)
        assert best is trained_qsvm

    def test_get_best_model_wrong_type(self, manager: QuantumModelManager, trained_qsvm: QSVMModel):
        manager.register(trained_qsvm)
        best = manager.get_best_model(model_type=QuantumModelType.VQC)
        assert best is None


class TestManagerHealth:
    def test_health_empty(self, manager: QuantumModelManager):
        h = manager.health()
        assert h["model_count"] == 0
        assert h["trained_count"] == 0
        assert h["total_inferences"] == 0

    def test_health_with_models(self, manager: QuantumModelManager, trained_qsvm: QSVMModel):
        manager.register(trained_qsvm)
        h = manager.health()
        assert h["model_count"] == 1
        assert h["trained_count"] == 1

    def test_health_error_rate(self, manager: QuantumModelManager, qsvm: QSVMModel):
        manager.register(qsvm)
        manager.record_inference("qsvm-1", success=True)
        manager.record_inference("qsvm-1", success=False)
        h = manager.health()
        assert h["total_inferences"] == 2
        assert h["total_errors"] == 1


class TestManagerSaveState:
    def test_save_state_empty(self, manager: QuantumModelManager):
        state = manager.save_state()
        assert state["model_count"] == 0

    def test_save_state_with_models(self, manager: QuantumModelManager, trained_qsvm: QSVMModel):
        manager.register(trained_qsvm, tags=["prod"])
        state = manager.save_state()
        assert state["model_count"] == 1
        assert "qsvm-trained" in state["models"]
        assert "prod" in state["models"]["qsvm-trained"]["tags"]


class TestManagerClear:
    def test_clear(self, manager: QuantumModelManager, qsvm: QSVMModel, qsvm2: QSVMModel):
        manager.register(qsvm)
        manager.register(qsvm2)
        count = manager.clear()
        assert count == 2
        assert manager.model_count == 0
