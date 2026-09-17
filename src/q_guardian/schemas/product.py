"""Request/response schemas for the product workflow API."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from q_guardian.schemas.base import BaseSchema

MAX_TARGET_LENGTH = 200


class StartScanRequest(BaseSchema):
    """Start a security scan over a prepared dataset or training run.

    ``cv`` runs K-fold cross-validation of the hybrid detection pipeline over
    the target's held-out evaluation pools. ``model_eval`` scores a trained
    checkpoint from a training run over the same pools.
    """

    type: Literal["cv", "model_eval"] = Field(default="cv", description="Scan kind")
    target: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TARGET_LENGTH,
        description="Dataset id (prepared under artifacts/datasets) or training run name",
    )
    k: int = Field(default=3, ge=2, le=10, description="Cross-validation folds")
    seed: int = Field(default=42, ge=0, description="Fold/seed RNG seed")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Decision threshold")
    ablate: bool = Field(default=False, description="Also run provider ablation")


class StartTrainingRequest(BaseSchema):
    """Start a prepare+train job for the hybrid detector.

    ``dataset_ids`` default to the framework's public train sources. The
    epochs/batch_size/learning_rate parity fields are intentionally omitted:
    the hybrid pipeline is scikit-learn/quantum based and does not apply them.
    """

    dataset_ids: list[str] | None = Field(default=None, max_length=20)
    name: str | None = Field(
        default=None,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
        description="Optional run directory name",
    )
    validation_ratio: float | None = Field(default=None, ge=0.0, lt=1.0)
    seed: int | None = Field(default=None, ge=0)
    max_samples_per_class: int | None = Field(default=None, ge=1)
    quantum: bool | None = Field(default=None, description="Enable the QSVM provider")
    quantum_shots: int | None = Field(default=None, ge=1, le=1_000_000)
    quantum_feature_count: int | None = Field(default=None, ge=1, le=64)
    quantum_cap: int | None = Field(default=None, ge=1)
    n_estimators: int | None = Field(default=None, ge=1)
    contamination: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class CrossAnalyticsRequest(BaseSchema):
    """Run cross-dataset analytics over previously saved report JSON files."""

    files: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Report JSON paths relative to the artifact root",
    )
    mode: Literal["macro", "weighted", "micro"] = Field(default="macro")
    strict: bool = Field(default=True, description="Require full compatibility")


class GenerateReportRequest(BaseSchema):
    """Generate a report artifact from an existing source."""

    kind: Literal["scan", "training", "analytics"] = Field(...)
    report_id: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Source id, e.g. 'scan:<scan_id>' / 'training:<run>' / 'analytics:<name>'",
    )

