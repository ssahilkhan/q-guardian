"""Unit tests for QSVMModel — Phase 2 quantum learning layer."""

from __future__ import annotations

import pytest
import numpy as np

from q_guardian.quantum.models.qsvm import QSVMModel, THREAT_CATEGORIES
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.feature_maps.zz_feature_map import ZZFeatureMap
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.enums import QuantumModelType, QuantumBackendType
from q_guardian.quantum.exceptions import TrainingError
from q_guardian.security.models import PromptFeatures


@pytest.fixture
def backend() -> LocalSimulatorBackend:
    return LocalSimulatorBackend()


@pytest.fixture
def feature_map() -> AngleEncodingMap:
    return AngleEncodingMap(num_qubits=4)


@pytest.fixture
def zz_feature_map() -> ZZFeatureMap:
    return ZZFeatureMap(num_qubits=4)


@pytest.fixture
def kernel(feature_map: AngleEncodingMap, backend: LocalSimulatorBackend) -> QuantumKernelEstimator:
    return QuantumKernelEstimator(feature_map=feature_map, backend=backend)


@pytest.fixture
def zz_kernel(zz_feature_map: ZZFeatureMap, backend: LocalSimulatorBackend) -> QuantumKernelEstimator:
    return QuantumKernelEstimator(feature_map=zz_feature_map, backend=backend)


@pytest.fixture
def qsvm(kernel: QuantumKernelEstimator) -> QSVMModel:
    return QSVMModel(kernel=kernel, feature_map=kernel.feature_map)


@pytest.fixture
def sample_data() -> tuple[list[list[float]], list[int]]:
    rng = np.random.default_rng(42)
    X = rng.uniform(-np.pi, np.pi, size=(20, 4)).tolist()
    y = [0 if i < 10 else 1 for i in range(20)]
    return X, y


@pytest.fixture
def multiclass_data() -> tuple[list[list[float]], list[int]]:
    rng = np.random.default_rng(42)
    X = rng.uniform(-np.pi, np.pi, size=(30, 4)).tolist()
    y = [0] * 10 + [1] * 10 + [2] * 10
    return X, y


class TestQSVMConstruction:
    def test_default_name(self, qsvm: QSVMModel):
        assert qsvm.name == "qsvm"

    def test_custom_name(self, kernel: QuantumKernelEstimator, feature_map: AngleEncodingMap):
        m = QSVMModel(kernel=kernel, feature_map=feature_map, name="custom-qsvm")
        assert m.name == "custom-qsvm"

    def test_version(self, qsvm: QSVMModel):
        assert qsvm.version == "1.0.0"

    def test_custom_version(self, kernel: QuantumKernelEstimator, feature_map: AngleEncodingMap):
        m = QSVMModel(kernel=kernel, feature_map=feature_map, version="2.1.0")
        assert m.version == "2.1.0"

    def test_kernel_property(self, qsvm: QSVMModel, kernel: QuantumKernelEstimator):
        assert qsvm.kernel is kernel

    def test_feature_map_property(self, qsvm: QSVMModel, feature_map: AngleEncodingMap):
        assert qsvm.feature_map is feature_map

    def test_not_trained_initially(self, qsvm: QSVMModel):
        assert qsvm.is_trained is False

    def test_support_vectors_empty_initially(self, qsvm: QSVMModel):
        assert qsvm.support_vectors == []

    def test_support_labels_empty_initially(self, qsvm: QSVMModel):
        assert qsvm.support_labels == []

    def test_bias_zero_initially(self, qsvm: QSVMModel):
        assert qsvm.bias == 0.0

    def test_classes_empty_initially(self, qsvm: QSVMModel):
        assert qsvm.classes == []


class TestQSVMTraining:
    def test_train_basic(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        assert qsvm.is_trained is True

    def test_train_sets_classes(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        assert sorted(qsvm.classes) == [0, 1]

    def test_train_populates_support_vectors(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        assert len(qsvm.support_vectors) == len(X)

    def test_train_populates_support_labels(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        assert len(qsvm.support_labels) == len(y)

    def test_train_multiclass(self, qsvm: QSVMModel, multiclass_data: tuple):
        X, y = multiclass_data
        qsvm.train(X, y)
        assert qsvm.is_trained is True
        assert sorted(qsvm.classes) == [0, 1, 2]

    def test_train_empty_raises(self, qsvm: QSVMModel):
        with pytest.raises(TrainingError, match="empty"):
            qsvm.train([], [])

    def test_train_no_labels_raises(self, qsvm: QSVMModel):
        with pytest.raises(TrainingError, match="labeled"):
            qsvm.train([[1.0, 2.0, 3.0, 4.0]])

    def test_train_mismatched_lengths_raises(self, qsvm: QSVMModel):
        with pytest.raises(TrainingError, match="mismatch"):
            qsvm.train([[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]], [0])

    def test_train_with_zz_kernel(self, zz_kernel: QuantumKernelEstimator, sample_data: tuple):
        qsvm = QSVMModel(kernel=zz_kernel, feature_map=zz_kernel.feature_map)
        X, y = sample_data
        qsvm.train(X, y)
        assert qsvm.is_trained is True

    def test_training_time_recorded(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        assert qsvm.quantum_metadata.metadata["training_time_s"] > 0


class TestQSVMMetadata:
    def test_metadata_before_training(self, qsvm: QSVMModel):
        m = qsvm.metadata
        assert m.name == "qsvm"
        assert m.status.value == "unloaded"

    def test_metadata_after_training(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        m = qsvm.metadata
        assert m.status.value == "ready"
        assert m.training_samples == len(X)

    def test_quantum_metadata(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        qm = qsvm.quantum_metadata
        assert qm.model_type == QuantumModelType.QSVM
        assert qm.name == "qsvm"
        assert qm.num_qubits == 4
        assert qm.training_samples == len(X)

    def test_quantum_metadata_model_type(self, qsvm: QSVMModel):
        qm = qsvm.quantum_metadata
        assert qm.model_type == QuantumModelType.QSVM


class TestQSVMPrediction:
    async def test_predict_before_training(self, qsvm: QSVMModel):
        result = await qsvm.predict([1.0, 2.0, 3.0, 4.0])
        assert result["predicted_class"] == "unknown"
        assert result["confidence"] == 0.0

    async def test_predict_after_training(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        result = await qsvm.predict(X[0])
        assert "predicted_class" in result
        assert "confidence" in result
        assert "probabilities" in result

    async def test_predict_returns_scores(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        result = await qsvm.predict(X[0])
        assert "scores" in result
        assert isinstance(result["scores"], dict)

    async def test_predict_quantum(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        qr = await qsvm.predict_quantum(X[0])
        assert qr.model_name == "qsvm"
        assert 0.0 <= qr.confidence <= 1.0

    async def test_predict_quantum_before_training(self, qsvm: QSVMModel):
        qr = await qsvm.predict_quantum([1.0, 2.0, 3.0, 4.0])
        assert qr.model_name == "qsvm"
        assert qr.confidence == 0.0

    async def test_predict_probabilities_sum(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        result = await qsvm.predict(X[0])
        probs = result["probabilities"]
        total = sum(probs.values())
        assert abs(total - 1.0) < 0.01


class TestQSVMClassifyQuantum:
    def _make_features(self) -> PromptFeatures:
        return PromptFeatures(
            length=100,
            word_count=20,
            line_count=3,
            token_estimate=25,
            entropy=3.5,
            uppercase_ratio=0.2,
            digit_ratio=0.1,
            special_char_count=5,
            code_block_count=0,
            url_count=0,
            suspicious_keywords=["ignore", "instructions"],
            repeated_patterns=[],
        )

    async def test_classify_quantum_benign(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        features = self._make_features()
        result = await qsvm.classify_quantum("Hello world", features)
        assert result.detector_name == "qsvm"
        assert 0.0 <= result.risk_score <= 1.0

    async def test_classify_quantum_untrained(self, qsvm: QSVMModel):
        features = self._make_features()
        result = await qsvm.classify_quantum("test", features)
        assert result.detector_name == "qsvm"
        assert result.risk_score == 0.0

    async def test_classify_quantum_feature_vector_length(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        features = self._make_features()
        result = await qsvm.classify_quantum("test", features)
        assert "predicted_class" in result.metadata


class TestQSVMSaveLoad:
    def test_save_returns_dict(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        state = qsvm.save()
        assert isinstance(state, dict)
        assert state["name"] == "qsvm"
        assert state["trained"] is True
        assert len(state["train_X"]) == len(X)

    def test_save_untrained(self, qsvm: QSVMModel):
        state = qsvm.save()
        assert state["trained"] is False

    def test_load_restores_state(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        state = qsvm.save()

        qsvm2 = QSVMModel(kernel=qsvm.kernel, feature_map=qsvm.feature_map)
        assert qsvm2.is_trained is False
        qsvm2.load(state)
        assert qsvm2.is_trained is True
        assert qsvm2.classes == [0, 1]

    def test_load_preserves_bias(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        state = qsvm.save()
        original_bias = qsvm.bias

        qsvm2 = QSVMModel(kernel=qsvm.kernel, feature_map=qsvm.feature_map)
        qsvm2.load(state)
        assert qsvm2.bias == original_bias

    def test_load_preserves_support_vectors(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        state = qsvm.save()

        qsvm2 = QSVMModel(kernel=qsvm.kernel, feature_map=qsvm.feature_map)
        qsvm2.load(state)
        assert len(qsvm2.support_vectors) == len(X)


class TestQSVMHealth:
    def test_health_untrained(self, qsvm: QSVMModel):
        h = qsvm.health()
        assert "kernel" in h
        assert "feature_map" in h
        assert "num_classes" in h
        assert h["num_classes"] == 0

    def test_health_trained(self, qsvm: QSVMModel, sample_data: tuple):
        X, y = sample_data
        qsvm.train(X, y)
        h = qsvm.health()
        assert h["num_classes"] == 2
        assert h["num_support_vectors"] == len(X)
        assert h["training_time_s"] > 0


class TestQSVMThreatCategories:
    def test_threat_categories_defined(self):
        assert len(THREAT_CATEGORIES) == 8
        assert "benign" in THREAT_CATEGORIES
        assert "prompt_injection" in THREAT_CATEGORIES
        assert "jailbreak" in THREAT_CATEGORIES
