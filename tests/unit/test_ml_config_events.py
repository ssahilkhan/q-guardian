"""Tests for ML events and config."""

from __future__ import annotations

from q_guardian.ml.config import MLConfig
from q_guardian.ml.enums import (
    DatasetFormat,
    FeatureType,
    ModelBackend,
    ModelStatus,
    ModelType,
    TrainingStatus,
)
from q_guardian.ml.events import (
    AnomalyDetected,
    EnsemblePrediction,
    EvaluationCompleted,
    FeatureExtracted,
    InferenceCompleted,
    ModelLoaded,
    ModelRegistered,
    ModelTrainingCompleted,
    ModelTrainingFailed,
    ModelTrainingStarted,
    ModelUnloaded,
    ThreatClassified,
)


class TestMLConfig:
    def test_defaults(self) -> None:
        config = MLConfig()
        assert config.enabled is True
        assert config.anomaly_threshold == 0.5
        assert config.classification_threshold == 0.5
        assert config.default_cv_folds == 5
        assert config.random_state == 42

    def test_explicit_disabled(self) -> None:
        config = MLConfig(enabled=False)
        assert config.enabled is False

    def test_custom(self) -> None:
        config = MLConfig(enabled=True, anomaly_threshold=0.3, max_features=5000)
        assert config.enabled is True
        assert config.anomaly_threshold == 0.3
        assert config.max_features == 5000

    def test_roundtrip(self) -> None:
        config = MLConfig(enabled=True)
        data = config.model_dump()
        restored = MLConfig.model_validate(data)
        assert restored.enabled == config.enabled

    def test_roundtrip_disabled(self) -> None:
        config = MLConfig(enabled=False)
        data = config.model_dump()
        restored = MLConfig.model_validate(data)
        assert restored.enabled is False


class TestMLEnums:
    def test_model_type(self) -> None:
        assert ModelType.ANOMALY_DETECTION.value == "anomaly_detection"
        assert ModelType.CLASSIFICATION.value == "classification"

    def test_model_backend(self) -> None:
        assert ModelBackend.SKLEARN.value == "sklearn"
        assert ModelBackend.XGBOOST.value == "xgboost"

    def test_training_status(self) -> None:
        assert TrainingStatus.COMPLETED.value == "completed"

    def test_model_status(self) -> None:
        assert ModelStatus.READY.value == "ready"

    def test_dataset_format(self) -> None:
        assert DatasetFormat.CSV.value == "csv"

    def test_feature_type(self) -> None:
        assert FeatureType.NUMERICAL.value == "numerical"


class TestMLEvents:
    def test_event_types(self) -> None:
        assert ModelRegistered().event_type == "ml.model.registered"
        assert ModelLoaded().event_type == "ml.model.loaded"
        assert ModelUnloaded().event_type == "ml.model.unloaded"
        assert ModelTrainingStarted().event_type == "ml.training.started"
        assert ModelTrainingCompleted().event_type == "ml.training.completed"
        assert ModelTrainingFailed().event_type == "ml.training.failed"
        assert InferenceCompleted().event_type == "ml.inference.completed"
        assert AnomalyDetected().event_type == "ml.inference.anomaly_detected"
        assert ThreatClassified().event_type == "ml.inference.threat_classified"
        assert EnsemblePrediction().event_type == "ml.inference.ensemble_prediction"
        assert FeatureExtracted().event_type == "ml.features.extracted"
        assert EvaluationCompleted().event_type == "ml.evaluation.completed"
