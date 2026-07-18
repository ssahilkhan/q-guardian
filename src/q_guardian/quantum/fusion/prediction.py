"""ThreatPrediction — the standardized output from any PredictionProvider.

This is the lingua franca of the Hybrid Intelligence Layer. Every
prediction source (rules, classical ML, quantum, future) produces a
ThreatPrediction. The Fusion Engine consumes only these objects and
never knows which algorithm produced them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.utils.uuid_utils import generate_uuid


class ReasoningTrace(BaseModel):
    """Optional reasoning trace explaining how a prediction was reached.

    Enables explainability across heterogeneous models without coupling
    to any specific model internals.
    """

    model_config = ConfigDict(populate_by_name=True)

    steps: list[str] = Field(default_factory=list, description="Ordered reasoning steps")
    evidence: list[str] = Field(default_factory=list, description="Supporting evidence snippets")
    rules_triggered: list[str] = Field(default_factory=list, description="Rule IDs that fired")
    feature_importances: dict[str, float] = Field(
        default_factory=dict, description="Feature name -> importance"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra reasoning data")


class ThreatPrediction(BaseModel):
    """Standardized prediction from any prediction source.

    Every PredictionProvider produces one of these. The Fusion Engine
    consumes only ThreatPrediction objects — it has zero knowledge of
    the underlying model type, algorithm, or backend.
    """

    model_config = ConfigDict(populate_by_name=True)

    prediction_id: str = Field(default_factory=generate_uuid, description="Unique ID")
    provider_id: str = Field(description="Identifier of the source provider")

    predicted_label: str = Field(description="Predicted class label (e.g. 'benign', 'injection')")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Calibrated confidence 0-1")
    probabilities: dict[str, float] = Field(
        default_factory=dict, description="Full class probability distribution"
    )

    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk score 0-1")

    latency_ms: float = Field(default=0.0, ge=0.0, description="Inference latency in ms")
    backend: str = Field(default="", description="Backend that produced this prediction")
    model_name: str = Field(default="", description="Name of the model")
    model_version: str = Field(default="", description="Model version")

    reasoning: ReasoningTrace | None = Field(
        default=None, description="Explainability trace"
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Extra source-specific metadata"
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation time"
    )

    is_valid: bool = Field(default=True, description="Whether prediction is usable")
    error_message: str = Field(default="", description="Error if prediction failed")
