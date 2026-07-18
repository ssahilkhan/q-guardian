"""Domain models for the Quantum module."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.quantum.enums import (
    BackendStatus,
    CircuitType,
    EncodingType,
    ExecutionStatus,
    QuantumBackendType,
    QuantumModelType,
)
from q_guardian.utils.uuid_utils import generate_uuid


class CircuitResult(BaseModel):
    """Result from a quantum circuit execution."""

    model_config = ConfigDict(populate_by_name=True)

    result_id: str = Field(default_factory=generate_uuid, description="Unique result ID")
    circuit_id: str = Field(default="", description="ID of the executed circuit")
    counts: dict[str, int] = Field(default_factory=dict, description="Measurement counts")
    probabilities: dict[str, float] = Field(
        default_factory=dict, description="Measurement probabilities"
    )
    expectation_values: dict[str, float] = Field(
        default_factory=dict, description="Expectation values"
    )
    raw_result: Any = Field(default=None, description="Backend-specific raw result")
    backend: str = Field(default="", description="Backend that executed the circuit")
    shots: int = Field(default=0, description="Number of shots used")
    execution_time_ms: float = Field(default=0.0, description="Execution time in ms")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Execution timestamp"
    )


class QuantumCircuitInfo(BaseModel):
    """Metadata about a quantum circuit."""

    model_config = ConfigDict(populate_by_name=True)

    circuit_id: str = Field(default_factory=generate_uuid, description="Unique circuit ID")
    name: str = Field(default="", description="Circuit name")
    circuit_type: CircuitType = Field(description="Type of circuit")
    num_qubits: int = Field(description="Number of qubits")
    depth: int = Field(default=0, description="Circuit depth")
    gate_count: int = Field(default=0, description="Total gate count")
    gate_counts: dict[str, int] = Field(
        default_factory=dict, description="Gate count by type"
    )
    encoding_type: EncodingType | None = Field(
        default=None, description="Feature encoding type used"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")


class QuantumModelMetadata(BaseModel):
    """Metadata for a registered quantum model."""

    model_config = ConfigDict(populate_by_name=True)

    model_id: str = Field(default_factory=generate_uuid, description="Unique model ID")
    name: str = Field(description="Model name")
    model_type: QuantumModelType = Field(description="Quantum model type")
    backend_type: QuantumBackendType = Field(description="Quantum backend used")
    version: str = Field(default="1.0.0", description="Model version (semver)")
    description: str = Field(default="", description="Human-readable description")
    status: str = Field(default="unloaded", description="Lifecycle status")
    num_qubits: int = Field(default=0, description="Number of qubits used")
    feature_count: int = Field(default=0, description="Number of input features")
    encoding_type: EncodingType | None = Field(default=None, description="Encoding used")
    training_samples: int = Field(default=0, description="Number of training samples")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp"
    )
    artifact_path: str = Field(default="", description="Path to saved model artifact")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")


class BackendInfo(BaseModel):
    """Information about a quantum backend."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Backend name")
    backend_type: QuantumBackendType = Field(description="Backend type")
    status: BackendStatus = Field(default=BackendStatus.INITIALIZING, description="Status")
    num_qubits: int = Field(default=0, description="Available qubits")
    max_shots: int = Field(default=8192, description="Maximum shots per execution")
    min_qubits: int = Field(default=1, description="Minimum qubits required")
    supports_simulation: bool = Field(default=True, description="Is simulation backend")
    supports_hardware: bool = Field(default=False, description="Is real hardware")
    error_rate: float | None = Field(default=None, description="Gate error rate")
    connectivity: str | None = Field(default=None, description="Qubit connectivity map")
    capabilities: list[str] = Field(
        default_factory=list, description="Backend capabilities"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    last_health_check: datetime | None = Field(
        default=None, description="Last health check timestamp"
    )


class QuantumTrainingResult(BaseModel):
    """Result from a quantum model training run."""

    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(default_factory=generate_uuid, description="Unique run ID")
    model_name: str = Field(description="Name of the trained model")
    status: str = Field(default="completed", description="Training status (completed/failed)")
    accuracy: float = Field(default=0.0, ge=0.0, le=1.0, description="Training accuracy")
    loss: float = Field(default=0.0, ge=0.0, description="Final loss value")
    training_loss: float = Field(default=0.0, ge=0.0, description="Training loss value")
    validation_loss: float = Field(default=0.0, ge=0.0, description="Validation loss value")
    convergence_iteration: int = Field(default=0, description="Iteration at convergence")
    convergence_epoch: int = Field(default=0, description="Epoch at convergence")
    training_samples: int = Field(default=0, description="Number of training samples")
    total_training_time_s: float = Field(default=0.0, alias="training_time_s", description="Training time in seconds")
    training_time_s: float = Field(default=0.0, description="Training time in seconds")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Evaluation metrics")
    cv_scores: list[float] = Field(default_factory=list, description="Cross-validation scores")
    cv_mean: float = Field(default=0.0, description="Mean CV score")
    cv_std: float = Field(default=0.0, description="Std of CV scores")
    error_message: str = Field(default="", description="Error message if failed")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Training timestamp"
    )


class QuantumInferenceResult(BaseModel):
    """Result from a quantum model inference."""

    model_config = ConfigDict(populate_by_name=True)

    result_id: str = Field(default_factory=generate_uuid, description="Unique result ID")
    model_name: str = Field(description="Model that produced this result")
    predictions: dict[str, float] = Field(
        default_factory=dict, description="Class probabilities"
    )
    predicted_class: str = Field(default="", description="Top predicted class")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Prediction confidence")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk score")
    circuit_result: CircuitResult | None = Field(
        default=None, description="Underlying circuit result"
    )
    processing_time_ms: float = Field(default=0.0, description="Inference latency")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Inference timestamp"
    )


class QuantumEvaluationMetrics(BaseModel):
    """Evaluation metrics for quantum models."""

    model_config = ConfigDict(populate_by_name=True)

    accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    precision: float = Field(default=0.0, ge=0.0, le=1.0)
    recall: float = Field(default=0.0, ge=0.0, le=1.0)
    f1_score: float = Field(default=0.0, ge=0.0, le=1.0)
    auc_roc: float = Field(default=0.0, ge=0.0, le=1.0)
    false_positive_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    false_negative_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    circuit_depth: int = Field(default=0, description="Circuit depth")
    circuit_width: int = Field(default=0, description="Circuit width (qubits)")
    total_shots: int = Field(default=0, description="Total measurement shots")
    inference_time_ms: float = Field(default=0.0, description="Average inference time")
    training_time_s: float = Field(default=0.0, description="Training time in seconds")
    memory_usage_mb: float = Field(default=0.0, description="Peak memory usage in MB")
    backend_used: str = Field(default="", description="Backend used for evaluation")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")


class FusedResult(BaseModel):
    """Result from hybrid fusion of multiple model predictions."""

    model_config = ConfigDict(populate_by_name=True)

    result_id: str = Field(default_factory=generate_uuid, description="Unique result ID")
    predictions: dict[str, float] = Field(
        default_factory=dict, description="Fused class probabilities"
    )
    predicted_class: str = Field(default="", description="Top predicted class")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Fused confidence")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Fused risk score")
    quantum_contribution: float = Field(
        default=0.0, description="Quantum model contribution weight"
    )
    classical_contribution: float = Field(
        default=0.0, description="Classical model contribution weight"
    )
    rule_contribution: float = Field(
        default=0.0, description="Rule engine contribution weight"
    )
    fusion_strategy: str = Field(default="", description="Strategy used for fusion")
    source_results: list[dict[str, Any]] = Field(
        default_factory=list, description="Individual model results"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
