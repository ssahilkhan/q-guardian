"""Events for the ML Security module."""

from __future__ import annotations

from pydantic import Field

from q_guardian.events.base import Event


class ModelRegistered(Event):
    """Published when a new model is registered with the ModelManager."""

    event_type: str = Field(default="ml.model.registered", init=False)


class ModelLoaded(Event):
    """Published when a model is loaded into memory."""

    event_type: str = Field(default="ml.model.loaded", init=False)


class ModelUnloaded(Event):
    """Published when a model is unloaded from memory."""

    event_type: str = Field(default="ml.model.unloaded", init=False)


class ModelTrainingStarted(Event):
    """Published when model training begins."""

    event_type: str = Field(default="ml.training.started", init=False)


class ModelTrainingCompleted(Event):
    """Published when model training completes successfully."""

    event_type: str = Field(default="ml.training.completed", init=False)


class ModelTrainingFailed(Event):
    """Published when model training fails."""

    event_type: str = Field(default="ml.training.failed", init=False)


class InferenceCompleted(Event):
    """Published when ML inference completes."""

    event_type: str = Field(default="ml.inference.completed", init=False)


class AnomalyDetected(Event):
    """Published when an anomaly is detected by any detector."""

    event_type: str = Field(default="ml.inference.anomaly_detected", init=False)


class ThreatClassified(Event):
    """Published when a prompt is classified as a threat."""

    event_type: str = Field(default="ml.inference.threat_classified", init=False)


class EnsemblePrediction(Event):
    """Published when ensemble produces a combined prediction."""

    event_type: str = Field(default="ml.inference.ensemble_prediction", init=False)


class FeatureExtracted(Event):
    """Published when ML features are extracted from a prompt."""

    event_type: str = Field(default="ml.features.extracted", init=False)


class EvaluationCompleted(Event):
    """Published when model evaluation completes."""

    event_type: str = Field(default="ml.evaluation.completed", init=False)
