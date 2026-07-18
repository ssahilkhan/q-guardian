"""Tests for quantum enums, config, data models, and exceptions."""

from __future__ import annotations

import pytest

from q_guardian.quantum.enums import (
    BackendStatus,
    CircuitType,
    EncodingType,
    ExecutionStatus,
    FusionStrategyType,
    MeasurementBasis,
    OptimizerType,
    QuantumBackendType,
    QuantumModelType,
)
from q_guardian.quantum.config import (
    QuantumBackendConfig,
    QuantumConfig,
    QuantumFeatureMapConfig,
    QuantumFusionConfig,
    QuantumTrainingConfig,
)
from q_guardian.quantum.data import (
    BackendInfo,
    CircuitResult,
    FusedResult,
    QuantumCircuitInfo,
    QuantumEvaluationMetrics,
    QuantumInferenceResult,
    QuantumModelMetadata,
    QuantumTrainingResult,
)
from q_guardian.quantum.exceptions import (
    BackendError,
    BackendNotAvailableError,
    CircuitExecutionError,
    ConfigurationError,
    EncodingDimensionError,
    FeatureMapError,
    FusionError,
    KernelError,
    ModelNotTrainedError,
    QuantumError,
    TranspilationError,
    TrainingError,
)


class TestQuantumEnums:
    def test_backend_type_values(self) -> None:
        assert QuantumBackendType.SIMULATOR.value == "simulator"
        assert QuantumBackendType.QISKIT_AER.value == "qiskit_aer"
        assert QuantumBackendType.IBM_QUANTUM.value == "ibm_quantum"

    def test_encoding_type_values(self) -> None:
        assert EncodingType.ANGLE.value == "angle"
        assert EncodingType.AMPLITUDE.value == "amplitude"
        assert EncodingType.ZZ_FEATURE_MAP.value == "zz_feature_map"

    def test_circuit_type_values(self) -> None:
        assert CircuitType.FEATURE_MAP.value == "feature_map"
        assert CircuitType.VARIATIONAL.value == "variational"
        assert CircuitType.KERNEL.value == "kernel"

    def test_measurement_basis_values(self) -> None:
        assert MeasurementBasis.PAULI_Z.value == "pauli_z"
        assert MeasurementBasis.COMPUTATIONAL.value == "computational"

    def test_optimizer_type_values(self) -> None:
        assert OptimizerType.COBYLA.value == "cobyla"
        assert OptimizerType.SPSA.value == "spsa"
        assert OptimizerType.ADAM.value == "adam"

    def test_quantum_model_type_values(self) -> None:
        assert QuantumModelType.QSVM.value == "qsvm"
        assert QuantumModelType.VQC.value == "vqc"
        assert QuantumModelType.QNN.value == "qnn"

    def test_execution_status_values(self) -> None:
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"

    def test_backend_status_values(self) -> None:
        assert BackendStatus.HEALTHY.value == "healthy"
        assert BackendStatus.UNAVAILABLE.value == "unavailable"
        assert BackendStatus.ERROR.value == "error"

    def test_fusion_strategy_values(self) -> None:
        assert FusionStrategyType.WEIGHTED_VOTING.value == "weighted_voting"
        assert FusionStrategyType.STACKING.value == "stacking"
        assert FusionStrategyType.ADAPTIVE.value == "adaptive"


class TestQuantumConfig:
    def test_default_config(self) -> None:
        config = QuantumConfig()
        assert config.enabled is False
        assert config.backend.num_qubits == 5
        assert config.backend.shots == 1024
        assert config.feature_map.encoding_type == EncodingType.ANGLE
        assert config.training.optimizer == OptimizerType.COBYLA
        assert config.fusion.strategy == FusionStrategyType.STACKING

    def test_backend_config(self) -> None:
        config = QuantumBackendConfig(
            backend_type=QuantumBackendType.QISKIT_AER,
            num_qubits=10,
            shots=2048,
        )
        assert config.backend_type == QuantumBackendType.QISKIT_AER
        assert config.num_qubits == 10
        assert config.shots == 2048

    def test_feature_map_config(self) -> None:
        config = QuantumFeatureMapConfig(
            encoding_type=EncodingType.ZZ_FEATURE_MAP,
            feature_map_depth=3,
            entanglement="full",
        )
        assert config.encoding_type == EncodingType.ZZ_FEATURE_MAP
        assert config.feature_map_depth == 3
        assert config.entanglement == "full"

    def test_training_config(self) -> None:
        config = QuantumTrainingConfig(
            optimizer=OptimizerType.SPSA,
            max_iterations=200,
            learning_rate=0.05,
        )
        assert config.optimizer == OptimizerType.SPSA
        assert config.max_iterations == 200
        assert config.learning_rate == 0.05

    def test_fusion_config(self) -> None:
        config = QuantumFusionConfig(
            strategy=FusionStrategyType.WEIGHTED_VOTING,
            quantum_weight=0.4,
            classical_weight=0.4,
            rule_weight=0.2,
        )
        assert config.strategy == FusionStrategyType.WEIGHTED_VOTING
        assert config.quantum_weight == 0.4

    def test_config_serialization(self) -> None:
        config = QuantumConfig(enabled=True)
        data = config.model_dump()
        assert data["enabled"] is True
        assert "backend" in data
        assert "feature_map" in data

    def test_backend_config_validation(self) -> None:
        with pytest.raises(Exception):
            QuantumBackendConfig(num_qubits=0)
        with pytest.raises(Exception):
            QuantumBackendConfig(shots=0)


class TestQuantumData:
    def test_circuit_result(self) -> None:
        result = CircuitResult(
            counts={"00": 512, "11": 512},
            probabilities={"00": 0.5, "11": 0.5},
            backend="local-simulator",
            shots=1024,
        )
        assert result.counts == {"00": 512, "11": 512}
        assert result.backend == "local-simulator"
        assert result.shots == 1024

    def test_circuit_result_defaults(self) -> None:
        result = CircuitResult()
        assert result.counts == {}
        assert result.probabilities == {}
        assert result.execution_time_ms == 0.0

    def test_quantum_circuit_info(self) -> None:
        info = QuantumCircuitInfo(
            circuit_type=CircuitType.KERNEL,
            num_qubits=4,
            depth=10,
            gate_count=20,
        )
        assert info.circuit_type == CircuitType.KERNEL
        assert info.num_qubits == 4
        assert info.depth == 10

    def test_quantum_model_metadata(self) -> None:
        meta = QuantumModelMetadata(
            name="test-qsvm",
            model_type=QuantumModelType.QSVM,
            backend_type=QuantumBackendType.LOCAL,
            num_qubits=4,
            feature_count=12,
        )
        assert meta.name == "test-qsvm"
        assert meta.model_type == QuantumModelType.QSVM
        assert meta.num_qubits == 4
        assert meta.status == "unloaded"

    def test_quantum_training_result(self) -> None:
        result = QuantumTrainingResult(
            model_name="test-model",
            status="completed",
            accuracy=0.85,
            training_time_s=1.5,
        )
        assert result.model_name == "test-model"
        assert result.status == "completed"
        assert result.accuracy == 0.85

    def test_quantum_training_result_failed(self) -> None:
        result = QuantumTrainingResult(
            model_name="test-model",
            status="failed",
            error_message="Training diverged",
        )
        assert result.status == "failed"
        assert result.error_message == "Training diverged"

    def test_quantum_inference_result(self) -> None:
        result = QuantumInferenceResult(
            model_name="test-model",
            predictions={"benign": 0.8, "injection": 0.2},
            predicted_class="benign",
            confidence=0.8,
            risk_score=0.2,
        )
        assert result.predicted_class == "benign"
        assert result.confidence == 0.8

    def test_quantum_evaluation_metrics(self) -> None:
        metrics = QuantumEvaluationMetrics(
            accuracy=0.92,
            precision=0.89,
            recall=0.95,
            f1_score=0.92,
            circuit_depth=10,
            circuit_width=5,
        )
        assert metrics.accuracy == 0.92
        assert metrics.circuit_depth == 10

    def test_fused_result(self) -> None:
        result = FusedResult(
            predicted_class="injection",
            confidence=0.85,
            risk_score=0.7,
            quantum_contribution=0.3,
            classical_contribution=0.5,
            rule_contribution=0.2,
            fusion_strategy="stacking",
        )
        assert result.fusion_strategy == "stacking"
        assert result.quantum_contribution == 0.3

    def test_backend_info(self) -> None:
        info = BackendInfo(
            name="local-sim",
            backend_type=QuantumBackendType.LOCAL,
            num_qubits=10,
            supports_simulation=True,
        )
        assert info.name == "local-sim"
        assert info.supports_simulation is True


class TestQuantumExceptions:
    def test_exception_hierarchy(self) -> None:
        assert issubclass(BackendError, QuantumError)
        assert issubclass(BackendNotAvailableError, BackendError)
        assert issubclass(CircuitExecutionError, BackendError)
        assert issubclass(TranspilationError, BackendError)
        assert issubclass(FeatureMapError, QuantumError)
        assert issubclass(EncodingDimensionError, FeatureMapError)
        assert issubclass(KernelError, QuantumError)
        assert issubclass(ModelNotTrainedError, QuantumError)
        assert issubclass(TrainingError, QuantumError)
        assert issubclass(ConfigurationError, QuantumError)
        assert issubclass(FusionError, QuantumError)

    def test_exception_messages(self) -> None:
        exc = BackendNotAvailableError("No backend available")
        assert str(exc) == "No backend available"

        exc = CircuitExecutionError("Circuit failed")
        assert str(exc) == "Circuit failed"
