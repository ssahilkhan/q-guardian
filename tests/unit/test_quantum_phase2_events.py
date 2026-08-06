"""Unit tests for Phase 2 learning lifecycle events."""

from __future__ import annotations

from q_guardian.quantum.events import (
    QuantumModelHealthChecked,
    QuantumModelLoaded,
    QuantumModelPredictionFailed,
    QuantumModelPredictionStarted,
    QuantumModelSaved,
    QuantumModelTrainingCompleted,
    QuantumModelTrainingFailed,
    QuantumModelTrainingStarted,
    QuantumModelVersionCreated,
)


class TestLearningLifecycleEvents:
    def test_training_started_type(self):
        e = QuantumModelTrainingStarted()
        assert e.event_type == "quantum.training.started"

    def test_training_completed_type(self):
        e = QuantumModelTrainingCompleted()
        assert e.event_type == "quantum.training.completed"

    def test_training_failed_type(self):
        e = QuantumModelTrainingFailed()
        assert e.event_type == "quantum.training.failed"

    def test_prediction_started_type(self):
        e = QuantumModelPredictionStarted()
        assert e.event_type == "quantum.prediction.started"

    def test_prediction_failed_type(self):
        e = QuantumModelPredictionFailed()
        assert e.event_type == "quantum.prediction.failed"

    def test_model_saved_type(self):
        e = QuantumModelSaved()
        assert e.event_type == "quantum.model.saved"

    def test_model_loaded_type(self):
        e = QuantumModelLoaded()
        assert e.event_type == "quantum.model.loaded"

    def test_version_created_type(self):
        e = QuantumModelVersionCreated()
        assert e.event_type == "quantum.model.version_created"

    def test_health_checked_type(self):
        e = QuantumModelHealthChecked()
        assert e.event_type == "quantum.model.health_checked"

    def test_training_started_has_id(self):
        e = QuantumModelTrainingStarted()
        assert e.id is not None
        assert len(e.id) > 0

    def test_training_completed_has_timestamp(self):
        e = QuantumModelTrainingCompleted()
        assert e.timestamp is not None
