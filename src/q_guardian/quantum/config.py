"""Quantum module configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.quantum.enums import (
    EncodingType,
    FusionStrategyType,
    OptimizerType,
    QuantumBackendType,
)


class QuantumBackendConfig(BaseModel):
    """Configuration for a specific quantum backend."""

    model_config = ConfigDict(extra="allow")

    backend_type: QuantumBackendType = Field(
        default=QuantumBackendType.SIMULATOR,
        description="Type of quantum backend",
    )
    num_qubits: int = Field(
        default=5, ge=1, le=100, description="Number of qubits"
    )
    shots: int = Field(
        default=1024, ge=1, description="Number of measurement shots"
    )
    optimization_level: int = Field(
        default=1, ge=0, le=3, description="Transpiler optimization level"
    )
    seed: int | None = Field(
        default=None, description="Random seed for reproducibility"
    )
    timeout_seconds: float = Field(
        default=30.0, ge=0, description="Execution timeout in seconds"
    )
    max_parallel_jobs: int = Field(
        default=4, ge=1, description="Max parallel circuit executions"
    )
    provider_options: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific options"
    )


class QuantumFeatureMapConfig(BaseModel):
    """Configuration for quantum feature maps."""

    model_config = ConfigDict(extra="allow")

    encoding_type: EncodingType = Field(
        default=EncodingType.ANGLE,
        description="Feature encoding strategy",
    )
    feature_map_depth: int = Field(
        default=2, ge=1, le=10, description="Depth of parameterized feature map"
    )
    entanglement: str = Field(
        default="linear", description="Entanglement pattern (linear, full, circular)"
    )
    feature_range: tuple[float, float] = Field(
        default=(0.0, 3.14159), description="Range for feature normalization"
    )
    normalize_features: bool = Field(
        default=True, description="Normalize features before encoding"
    )
    max_features: int = Field(
        default=32, ge=1, le=100, description="Maximum features to encode"
    )


class QuantumTrainingConfig(BaseModel):
    """Configuration for quantum model training."""

    model_config = ConfigDict(extra="allow")

    optimizer: OptimizerType = Field(
        default=OptimizerType.COBYLA, description="Optimization algorithm"
    )
    max_iterations: int = Field(
        default=100, ge=1, description="Maximum optimization iterations"
    )
    convergence_threshold: float = Field(
        default=1e-6, ge=0, description="Convergence threshold"
    )
    learning_rate: float = Field(
        default=0.1, gt=0, description="Learning rate for gradient-based optimizers"
    )
    batch_size: int = Field(
        default=32, ge=1, description="Batch size for training"
    )
    validation_split: float = Field(
        default=0.2, ge=0.0, le=1.0, description="Validation split ratio"
    )
    early_stopping_patience: int = Field(
        default=10, ge=1, description="Early stopping patience"
    )
    random_state: int = Field(default=42, description="Random seed for reproducibility")


class QuantumFusionConfig(BaseModel):
    """Configuration for hybrid fusion strategies."""

    model_config = ConfigDict(extra="allow")

    strategy: FusionStrategyType = Field(
        default=FusionStrategyType.STACKING,
        description="Fusion strategy type",
    )
    quantum_weight: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Weight for quantum predictions"
    )
    classical_weight: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Weight for classical predictions"
    )
    rule_weight: float = Field(
        default=0.2, ge=0.0, le=1.0, description="Weight for rule-based predictions"
    )
    confidence_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Minimum confidence for prediction"
    )
    adaptive_window_size: int = Field(
        default=100, ge=1, description="Window size for adaptive weight updates"
    )
    stacking_meta_learner: str = Field(
        default="logistic_regression",
        description="Meta-learner for stacking fusion",
    )


class QuantumConfig(BaseModel):
    """Top-level configuration for the Quantum module.

    Controls backend selection, feature encoding, model training,
    fusion strategy, and evaluation settings.
    """

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(
        default=False, description="Enable quantum analysis"
    )

    # Backend
    backend: QuantumBackendConfig = Field(
        default_factory=QuantumBackendConfig,
        description="Quantum backend configuration",
    )

    # Feature mapping
    feature_map: QuantumFeatureMapConfig = Field(
        default_factory=QuantumFeatureMapConfig,
        description="Feature map configuration",
    )

    # Training
    training: QuantumTrainingConfig = Field(
        default_factory=QuantumTrainingConfig,
        description="Training configuration",
    )

    # Fusion
    fusion: QuantumFusionConfig = Field(
        default_factory=QuantumFusionConfig,
        description="Hybrid fusion configuration",
    )

    # Storage
    model_storage_path: Path = Field(
        default=Path("models/quantum"),
        description="Directory for persisted quantum model artifacts",
    )
    auto_save: bool = Field(default=True, description="Auto-save models after training")

    # Evaluation
    evaluation_shots: int = Field(
        default=4096, ge=1, description="Shots for evaluation runs"
    )
    benchmark_repetitions: int = Field(
        default=3, ge=1, description="Repetitions for benchmarking"
    )

    # Logging
    log_circuits: bool = Field(default=False, description="Log circuit diagrams")
    log_executions: bool = Field(default=True, description="Log circuit executions")
    log_metadata: bool = Field(default=True, description="Log quantum metadata")
