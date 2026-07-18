"""Quantum computing layer enumerations."""

from __future__ import annotations

from enum import Enum


class QuantumBackendType(str, Enum):
    """Supported quantum backend types."""

    SIMULATOR = "simulator"
    QISKIT_AER = "qiskit_aer"
    QISKIT_RUNTIME = "qiskit_runtime"
    IBM_QUANTUM = "ibm_quantum"
    PENNYLANE = "pennylane"
    CUDAQ = "cudaq"
    LOCAL = "local"
    CUSTOM = "custom"


class EncodingType(str, Enum):
    """Quantum feature encoding strategies."""

    ANGLE = "angle"
    AMPLITUDE = "amplitude"
    ZZ_FEATURE_MAP = "zz_feature_map"
    PAULI = "pauli"
    CUSTOM = "custom"


class CircuitType(str, Enum):
    """Types of quantum circuits."""

    FEATURE_MAP = "feature_map"
    VARIATIONAL = "variational"
    KERNEL = "kernel"
    MEASUREMENT = "measurement"
    HYBRID = "hybrid"


class MeasurementBasis(str, Enum):
    """Measurement basis for quantum circuits."""

    PAULI_Z = "pauli_z"
    PAULI_X = "pauli_x"
    PAULI_Y = "pauli_y"
    COMPUTATIONAL = "computational"


class OptimizerType(str, Enum):
    """Supported quantum optimizers."""

    COBYLA = "cobyla"
    L_BFGS_B = "l_bfgs_b"
    SPSA = "spsa"
    ADAM = "adam"
    GRADIENT_DESCENT = "gradient_descent"
    NELDER_MEAD = "nelder_mead"
    POWELL = "powell"


class QuantumModelType(str, Enum):
    """Types of quantum ML models."""

    QSVM = "qsvm"
    VQC = "vqc"
    QNN = "qnn"
    KERNEL_ESTIMATOR = "kernel_estimator"
    ENSEMBLE = "ensemble"
    CUSTOM = "custom"


class ExecutionStatus(str, Enum):
    """Status of a quantum circuit execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackendStatus(str, Enum):
    """Health status of a quantum backend."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    INITIALIZING = "initializing"
    ERROR = "error"


class FusionStrategyType(str, Enum):
    """Hybrid fusion strategy types."""

    WEIGHTED_VOTING = "weighted_voting"
    CONFIDENCE_BASED = "confidence_based"
    STACKING = "stacking"
    ADAPTIVE = "adaptive"
    BAYESIAN = "bayesian"
    MAX_CONFIDENCE = "max_confidence"
