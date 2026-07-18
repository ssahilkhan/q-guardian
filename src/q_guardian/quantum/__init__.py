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

from q_guardian.quantum.config import (
    QuantumBackendConfig,
    QuantumConfig,
    QuantumFeatureMapConfig,
    QuantumFusionConfig,
    QuantumTrainingConfig,
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
    QuantumInferenceError,
    TranspilationError,
    TrainingError,
)
from q_guardian.quantum.backends.base import QuantumBackend
from q_guardian.quantum.backends.manager import BackendManager
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.feature_maps.base import EncodedCircuit, QuantumFeatureMap
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.feature_maps.zz_feature_map import ZZFeatureMap
from q_guardian.quantum.feature_maps.pauli_feature_map import PauliFeatureMap
from q_guardian.quantum.kernels.base import QuantumKernel
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.execution.executor import CircuitExecutor
from q_guardian.quantum.models.base import BaseQuantumModel
from q_guardian.quantum.models.qsvm import QSVMModel
from q_guardian.quantum.models.manager import QuantumModelManager
from q_guardian.quantum.training.trainer import QuantumTrainer
from q_guardian.quantum.training.kernel_trainer import (
    KernelHyperparams,
    KernelCandidate,
    KernelSearchResult,
    QuantumKernelTrainer,
)
from q_guardian.quantum.evaluation.metrics import QuantumEvaluator
from q_guardian.quantum.inference.engine import QuantumInferenceEngine
from q_guardian.quantum.storage import QuantumModelStorage
from q_guardian.quantum.plugin import QuantumAnalysisPlugin
# Phase 3: Hybrid Intelligence Layer
from q_guardian.quantum.fusion import (
    ThreatPrediction,
    ReasoningTrace,
    PredictionProvider,
    ConfidenceCalibrator,
    HybridFusionEngine,
    RuleEngineProvider,
    ClassicalModelProvider,
    QuantumModelProvider,
    GenericProvider,
    FusionStrategy,
    FusedPrediction,
    WeightedVotingStrategy,
    ConfidenceFusionStrategy,
    AdaptiveFusionStrategy,
    StackingFusionStrategy,
    BayesianFusionStrategy,
)

__all__ = [
    # Config
    "QuantumBackendConfig",
    "QuantumConfig",
    "QuantumFeatureMapConfig",
    "QuantumFusionConfig",
    "QuantumTrainingConfig",
    # Enums
    "BackendStatus",
    "CircuitType",
    "EncodingType",
    "ExecutionStatus",
    "FusionStrategyType",
    "MeasurementBasis",
    "OptimizerType",
    "QuantumBackendType",
    "QuantumModelType",
    # Data
    "BackendInfo",
    "CircuitResult",
    "FusedResult",
    "QuantumCircuitInfo",
    "QuantumEvaluationMetrics",
    "QuantumInferenceResult",
    "QuantumModelMetadata",
    "QuantumTrainingResult",
    # Exceptions
    "BackendError",
    "BackendNotAvailableError",
    "CircuitExecutionError",
    "ConfigurationError",
    "EncodingDimensionError",
    "FeatureMapError",
    "FusionError",
    "KernelError",
    "ModelNotTrainedError",
    "QuantumError",
    "QuantumInferenceError",
    "TranspilationError",
    "TrainingError",
    # Backends
    "BackendManager",
    "LocalSimulatorBackend",
    "QuantumBackend",
    # Feature maps
    "AngleEncodingMap",
    "EncodedCircuit",
    "PauliFeatureMap",
    "QuantumFeatureMap",
    "ZZFeatureMap",
    # Kernels
    "QuantumKernel",
    "QuantumKernelEstimator",
    # Execution
    "CircuitExecutor",
    # Models
    "BaseQuantumModel",
    "QSVMModel",
    "QuantumModelManager",
    # Training
    "QuantumTrainer",
    "QuantumKernelTrainer",
    "KernelHyperparams",
    "KernelCandidate",
    "KernelSearchResult",
    # Evaluation
    "QuantumEvaluator",
    # Inference
    "QuantumInferenceEngine",
    # Storage
    "QuantumModelStorage",
    # Plugin
    "QuantumAnalysisPlugin",
    # Phase 3: Hybrid Intelligence Layer
    "ThreatPrediction",
    "ReasoningTrace",
    "PredictionProvider",
    "ConfidenceCalibrator",
    "HybridFusionEngine",
    "RuleEngineProvider",
    "ClassicalModelProvider",
    "QuantumModelProvider",
    "GenericProvider",
    "FusionStrategy",
    "FusedPrediction",
    "WeightedVotingStrategy",
    "ConfidenceFusionStrategy",
    "AdaptiveFusionStrategy",
    "StackingFusionStrategy",
    "BayesianFusionStrategy",
]
