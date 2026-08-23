"""ML Security module configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class MLConfig(BaseModel):
    """Configuration for the ML Security module.

    Controls model storage, inference thresholds, training defaults,
    feature extraction, and dataset loading.
    """

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable ML-based analysis")

    # Storage
    model_storage_path: Path = Field(
        default=Path("models/ml"),
        description="Directory for persisted model artifacts",
    )
    auto_save: bool = Field(default=True, description="Auto-save models after training")

    # Inference
    anomaly_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Threshold for anomaly detection (Isolation Forest)",
    )
    classification_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Threshold for classification confidence",
    )
    ensemble_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Weight per model name in ensemble (empty = equal weights)",
    )

    # Feature extraction
    max_features: int = Field(default=10_000, description="Maximum vocabulary size for TF-IDF")
    ngram_range: tuple[int, int] = Field(default=(1, 2), description="N-gram range for TF-IDF")
    use_tfidf: bool = Field(default=True, description="Use TF-IDF features")
    use_statistical: bool = Field(default=True, description="Use statistical features")
    use_keyword_features: bool = Field(default=True, description="Use keyword features")

    # Training defaults
    default_test_size: float = Field(
        default=0.2, ge=0.0, le=1.0, description="Default test split ratio"
    )
    default_cv_folds: int = Field(default=5, ge=2, description="Default cross-validation folds")
    random_state: int = Field(default=42, description="Random seed for reproducibility")

    # XGBoost (optional)
    xgboost_available: bool = Field(default=False, description="Whether XGBoost is installed")

    # Logging
    log_predictions: bool = Field(default=True, description="Log inference predictions")
    log_feature_importance: bool = Field(
        default=False, description="Log feature importance during training"
    )
