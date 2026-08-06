"""Enumerations for the ML Security module."""

from __future__ import annotations

from enum import StrEnum


class ModelType(StrEnum):
    """Type of ML model."""

    ANOMALY_DETECTION = "anomaly_detection"
    CLASSIFICATION = "classification"
    ENSEMBLE = "ensemble"
    CUSTOM = "custom"


class ModelBackend(StrEnum):
    """ML framework backend."""

    SKLEARN = "sklearn"
    XGBOOST = "xgboost"
    CUSTOM = "custom"


class FeatureType(StrEnum):
    """Type of extracted feature."""

    NUMERICAL = "numerical"
    CATEGORICAL = "categorical"
    TEXT = "text"
    EMBEDDING = "embedding"
    STATISTICAL = "statistical"


class TrainingStatus(StrEnum):
    """Status of a training run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelStatus(StrEnum):
    """Lifecycle status of a registered model."""

    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"
    DEPRECATED = "deprecated"


class DatasetFormat(StrEnum):
    """Supported dataset file formats."""

    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"
    HUGGINGFACE = "huggingface"
    NUMPY = "numpy"
