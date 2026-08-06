"""Domain models for the ML Security module."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.ml.enums import ModelBackend, ModelStatus, ModelType, TrainingStatus
from q_guardian.security.enums import PromptCategory, PromptSeverity
from q_guardian.security.models import PromptFinding
from q_guardian.utils.uuid_utils import generate_uuid


class ModelMetadata(BaseModel):
    """Metadata for a registered ML model."""

    model_config = ConfigDict(populate_by_name=True)

    model_id: str = Field(default_factory=generate_uuid, description="Unique model ID")
    name: str = Field(description="Model name (e.g. 'isolation-forest-v1')")
    model_type: ModelType = Field(description="Type of model")
    backend: ModelBackend = Field(description="ML framework backend")
    version: str = Field(default="1.0.0", description="Model version (semver)")
    description: str = Field(default="", description="Human-readable description")
    status: ModelStatus = Field(default=ModelStatus.UNLOADED, description="Lifecycle status")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp"
    )
    artifact_path: str = Field(default="", description="Path to saved model artifact")
    training_samples: int = Field(default=0, description="Number of training samples")
    feature_count: int = Field(default=0, description="Number of input features")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")


class InferenceResult(BaseModel):
    """Result from a single model inference."""

    model_config = ConfigDict(populate_by_name=True)

    result_id: str = Field(default_factory=generate_uuid, description="Unique result ID")
    model_name: str = Field(description="Name of the model that produced this result")
    is_anomaly: bool = Field(default=False, description="Whether anomaly was detected")
    anomaly_score: float = Field(default=0.0, ge=-1.0, le=1.0, description="Raw anomaly score")
    predictions: dict[str, float] = Field(default_factory=dict, description="Class probabilities")
    predicted_class: str = Field(default="", description="Top predicted class")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Prediction confidence")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Derived risk score")
    findings: list[PromptFinding] = Field(
        default_factory=list, description="Findings from this model"
    )
    processing_time_ms: float = Field(default=0.0, description="Inference latency")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Inference timestamp"
    )


class TrainingResult(BaseModel):
    """Result from a model training run."""

    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(default_factory=generate_uuid, description="Unique run ID")
    model_name: str = Field(description="Name of the trained model")
    status: TrainingStatus = Field(description="Training status")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Evaluation metrics")
    feature_importance: dict[str, float] = Field(
        default_factory=dict, description="Feature importance scores"
    )
    training_samples: int = Field(default=0, description="Number of training samples")
    validation_samples: int = Field(default=0, description="Number of validation samples")
    training_time_s: float = Field(default=0.0, description="Training time in seconds")
    cv_scores: list[float] = Field(default_factory=list, description="Cross-validation scores")
    cv_mean: float = Field(default=0.0, description="Mean CV score")
    cv_std: float = Field(default=0.0, description="Std of CV scores")
    error_message: str = Field(default="", description="Error message if failed")
    artifact_path: str = Field(default="", description="Path to saved model")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Training timestamp"
    )


class FeatureVector(BaseModel):
    """A numeric feature vector for ML models."""

    model_config = ConfigDict(populate_by_name=True)

    vector_id: str = Field(default_factory=generate_uuid, description="Unique vector ID")
    prompt_id: str = Field(default="", description="Associated prompt/analysis ID")
    features: list[float] = Field(default_factory=list, description="Feature values")
    feature_names: list[str] = Field(default_factory=list, description="Feature names")
    source_model: str = Field(default="", description="Model that produced this vector")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")


class EvaluationMetrics(BaseModel):
    """Evaluation metrics for a trained model."""

    model_config = ConfigDict(populate_by_name=True)

    accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    precision: float = Field(default=0.0, ge=0.0, le=1.0)
    recall: float = Field(default=0.0, ge=0.0, le=1.0)
    f1_score: float = Field(default=0.0, ge=0.0, le=1.0)
    auc_roc: float = Field(default=0.0, ge=0.0, le=1.0)
    true_positives: int = Field(default=0)
    true_negatives: int = Field(default=0)
    false_positives: int = Field(default=0)
    false_negatives: int = Field(default=0)
    confusion_matrix: list[list[int]] = Field(default_factory=list)
    per_class_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetEntry(BaseModel):
    """A single dataset entry for training/evaluation."""

    model_config = ConfigDict(populate_by_name=True)

    entry_id: str = Field(default_factory=generate_uuid, description="Unique entry ID")
    prompt: str = Field(description="Prompt text")
    label: PromptCategory = Field(description="Ground truth label")
    severity: PromptSeverity = Field(default=PromptSeverity.LOW, description="Label severity")
    is_malicious: bool = Field(default=False, description="Whether prompt is malicious")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
