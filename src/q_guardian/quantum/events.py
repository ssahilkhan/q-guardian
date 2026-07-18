"""Quantum module events."""

from __future__ import annotations

from pydantic import Field

from q_guardian.events.base import Event


class BackendRegistered(Event):
    """Published when a quantum backend is registered."""

    event_type: str = Field(default="quantum.backend.registered", init=False)


class BackendConnected(Event):
    """Published when a quantum backend connection is established."""

    event_type: str = Field(default="quantum.backend.connected", init=False)


class BackendDisconnected(Event):
    """Published when a quantum backend connection is lost."""

    event_type: str = Field(default="quantum.backend.disconnected", init=False)


class BackendHealthChanged(Event):
    """Published when a backend health status changes."""

    event_type: str = Field(default="quantum.backend.health_changed", init=False)


class CircuitCompiled(Event):
    """Published when a quantum circuit is compiled/transpiled."""

    event_type: str = Field(default="quantum.circuit.compiled", init=False)


class CircuitExecuted(Event):
    """Published after a quantum circuit execution completes."""

    event_type: str = Field(default="quantum.circuit.executed", init=False)


class CircuitExecutionFailed(Event):
    """Published when a quantum circuit execution fails."""

    event_type: str = Field(default="quantum.circuit.execution_failed", init=False)


class QuantumModelRegistered(Event):
    """Published when a quantum model is registered."""

    event_type: str = Field(default="quantum.model.registered", init=False)


class QuantumModelTrained(Event):
    """Published when quantum model training completes."""

    event_type: str = Field(default="quantum.model.trained", init=False)


class QuantumModelPredictionCompleted(Event):
    """Published when a quantum model prediction completes."""

    event_type: str = Field(default="quantum.model.prediction_completed", init=False)


class QuantumInferenceCompleted(Event):
    """Published when quantum inference pipeline completes."""

    event_type: str = Field(default="quantum.inference.completed", init=False)


class QuantumFusionCompleted(Event):
    """Published when hybrid fusion completes."""

    event_type: str = Field(default="quantum.fusion.completed", init=False)


class QuantumEvaluationCompleted(Event):
    """Published when quantum model evaluation completes."""

    event_type: str = Field(default="quantum.evaluation.completed", init=False)


class FeatureEncoded(Event):
    """Published when features are encoded into quantum representation."""

    event_type: str = Field(default="quantum.features.encoded", init=False)


class KernelComputed(Event):
    """Published when a quantum kernel matrix is computed."""

    event_type: str = Field(default="quantum.kernel.computed", init=False)


# ── Learning lifecycle events (Phase 2) ─────────────────────────────────


class QuantumModelTrainingStarted(Event):
    """Published when quantum model training begins."""

    event_type: str = Field(default="quantum.training.started", init=False)


class QuantumModelTrainingCompleted(Event):
    """Published when quantum model training successfully finishes."""

    event_type: str = Field(default="quantum.training.completed", init=False)


class QuantumModelTrainingFailed(Event):
    """Published when quantum model training fails."""

    event_type: str = Field(default="quantum.training.failed", init=False)


class QuantumModelPredictionStarted(Event):
    """Published when a quantum model prediction begins."""

    event_type: str = Field(default="quantum.prediction.started", init=False)


class QuantumModelPredictionFailed(Event):
    """Published when a quantum model prediction fails."""

    event_type: str = Field(default="quantum.prediction.failed", init=False)


class QuantumModelSaved(Event):
    """Published when a quantum model is persisted to disk."""

    event_type: str = Field(default="quantum.model.saved", init=False)


class QuantumModelLoaded(Event):
    """Published when a quantum model is loaded from disk."""

    event_type: str = Field(default="quantum.model.loaded", init=False)


class QuantumModelVersionCreated(Event):
    """Published when a new model version is created."""

    event_type: str = Field(default="quantum.model.version_created", init=False)


class QuantumModelHealthChecked(Event):
    """Published when a quantum model health check completes."""

    event_type: str = Field(default="quantum.model.health_checked", init=False)


# ── Hybrid fusion events (Phase 3) ────────────────────────────────────


class FusionEngineInitialized(Event):
    """Published when the HybridFusionEngine is initialized."""

    event_type: str = Field(default="quantum.fusion.engine_initialized", init=False)


class FusionStrategySwitched(Event):
    """Published when the active fusion strategy is changed."""

    event_type: str = Field(default="quantum.fusion.strategy_switched", init=False)


class ProviderRegistered(Event):
    """Published when a PredictionProvider is registered with the fusion engine."""

    event_type: str = Field(default="quantum.fusion.provider_registered", init=False)


class ProviderFailed(Event):
    """Published when a PredictionProvider fails during prediction collection."""

    event_type: str = Field(default="quantum.fusion.provider_failed", init=False)


class ConfidenceCalibrationApplied(Event):
    """Published when confidence calibration is applied to predictions."""

    event_type: str = Field(default="quantum.fusion.calibration_applied", init=False)
