"""Quantum Computing Layer for Q-Guardian.

Provides backend-agnostic quantum computing abstractions including:
- Backend management (simulators, Qiskit, IBM Quantum)
- Feature maps (angle, ZZ, Pauli encoding)
- Quantum kernels for kernel-based classification
- Circuit execution abstraction
- Base quantum model interface
- Training and evaluation pipelines

All quantum SDK imports (Qiskit, PennyLane, etc.) are isolated
within backend implementations. No external package should import
quantum SDKs directly.
"""

from q_guardian.quantum.backends.base import QuantumBackend
from q_guardian.quantum.backends.manager import BackendManager
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
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
from q_guardian.quantum.evaluation.metrics import QuantumEvaluator
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
    QuantumInferenceError,
    TrainingError,
    TranspilationError,
)
from q_guardian.quantum.execution.executor import CircuitExecutor
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.feature_maps.base import EncodedCircuit, QuantumFeatureMap
from q_guardian.quantum.feature_maps.pauli_feature_map import PauliFeatureMap
from q_guardian.quantum.feature_maps.zz_feature_map import ZZFeatureMap

# Phase 3: Hybrid Intelligence Layer
from q_guardian.quantum.fusion import (
    AdaptiveFusionStrategy,
    BayesianFusionStrategy,
    ClassicalModelProvider,
    ConfidenceCalibrator,
    ConfidenceFusionStrategy,
    FusedPrediction,
    FusionStrategy,
    GenericProvider,
    HybridFusionEngine,
    PredictionProvider,
    QuantumModelProvider,
    ReasoningTrace,
    RuleEngineProvider,
    StackingFusionStrategy,
    ThreatPrediction,
    WeightedVotingStrategy,
)
from q_guardian.quantum.inference.engine import QuantumInferenceEngine
from q_guardian.quantum.kernels.base import QuantumKernel
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.models.base import BaseQuantumModel
from q_guardian.quantum.models.manager import QuantumModelManager
from q_guardian.quantum.models.qsvm import QSVMModel
from q_guardian.quantum.plugin import QuantumAnalysisPlugin
from q_guardian.quantum.storage import QuantumModelStorage
from q_guardian.quantum.training.kernel_trainer import (
    KernelCandidate,
    KernelHyperparams,
    KernelSearchResult,
    QuantumKernelTrainer,
)
from q_guardian.quantum.training.trainer import QuantumTrainer

__all__ = [
    "AdaptiveFusionStrategy",
    # Feature maps
    "AngleEncodingMap",
    # Exceptions
    "BackendError",
    # Data
    "BackendInfo",
    # Backends
    "BackendManager",
    "BackendNotAvailableError",
    # Enums
    "BackendStatus",
    # Models
    "BaseQuantumModel",
    "BayesianFusionStrategy",
    "CircuitExecutionError",
    # Execution
    "CircuitExecutor",
    "CircuitResult",
    "CircuitType",
    "ClassicalModelProvider",
    "ConfidenceCalibrator",
    "ConfidenceFusionStrategy",
    "ConfigurationError",
    "EncodedCircuit",
    "EncodingDimensionError",
    "EncodingType",
    "ExecutionStatus",
    "FeatureMapError",
    "FusedPrediction",
    "FusedResult",
    "FusionError",
    "FusionStrategy",
    "FusionStrategyType",
    "GenericProvider",
    "HybridFusionEngine",
    "KernelCandidate",
    "KernelError",
    "KernelHyperparams",
    "KernelSearchResult",
    "LocalSimulatorBackend",
    "MeasurementBasis",
    "ModelNotTrainedError",
    "OptimizerType",
    "PauliFeatureMap",
    "PredictionProvider",
    "QSVMModel",
    # Plugin
    "QuantumAnalysisPlugin",
    "QuantumBackend",
    # Config
    "QuantumBackendConfig",
    "QuantumBackendType",
    "QuantumCircuitInfo",
    "QuantumConfig",
    "QuantumError",
    "QuantumEvaluationMetrics",
    # Evaluation
    "QuantumEvaluator",
    "QuantumFeatureMap",
    "QuantumFeatureMapConfig",
    "QuantumFusionConfig",
    # Inference
    "QuantumInferenceEngine",
    "QuantumInferenceError",
    "QuantumInferenceResult",
    # Kernels
    "QuantumKernel",
    "QuantumKernelEstimator",
    "QuantumKernelTrainer",
    "QuantumModelManager",
    "QuantumModelMetadata",
    "QuantumModelProvider",
    # Storage
    "QuantumModelStorage",
    "QuantumModelType",
    # Training
    "QuantumTrainer",
    "QuantumTrainingConfig",
    "QuantumTrainingResult",
    "ReasoningTrace",
    "RuleEngineProvider",
    "StackingFusionStrategy",
    # Phase 3: Hybrid Intelligence Layer
    "ThreatPrediction",
    "TrainingError",
    "TranspilationError",
    "WeightedVotingStrategy",
    "ZZFeatureMap",
]
