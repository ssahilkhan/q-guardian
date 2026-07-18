"""Tests for quantum events."""

from __future__ import annotations

import pytest

from q_guardian.quantum.events import (
    BackendConnected,
    BackendDisconnected,
    BackendHealthChanged,
    BackendRegistered,
    CircuitCompiled,
    CircuitExecuted,
    CircuitExecutionFailed,
    FeatureEncoded,
    KernelComputed,
    QuantumEvaluationCompleted,
    QuantumFusionCompleted,
    QuantumInferenceCompleted,
    QuantumModelPredictionCompleted,
    QuantumModelRegistered,
    QuantumModelTrained,
)


class TestQuantumEvents:
    def test_backend_registered(self) -> None:
        event = BackendRegistered(source="test")
        assert event.event_type == "quantum.backend.registered"

    def test_backend_connected(self) -> None:
        event = BackendConnected(source="test")
        assert event.event_type == "quantum.backend.connected"

    def test_backend_disconnected(self) -> None:
        event = BackendDisconnected(source="test")
        assert event.event_type == "quantum.backend.disconnected"

    def test_backend_health_changed(self) -> None:
        event = BackendHealthChanged(source="test")
        assert event.event_type == "quantum.backend.health_changed"

    def test_circuit_compiled(self) -> None:
        event = CircuitCompiled(source="test")
        assert event.event_type == "quantum.circuit.compiled"

    def test_circuit_executed(self) -> None:
        event = CircuitExecuted(source="test")
        assert event.event_type == "quantum.circuit.executed"

    def test_circuit_execution_failed(self) -> None:
        event = CircuitExecutionFailed(source="test")
        assert event.event_type == "quantum.circuit.execution_failed"

    def test_quantum_model_registered(self) -> None:
        event = QuantumModelRegistered(source="test")
        assert event.event_type == "quantum.model.registered"

    def test_quantum_model_trained(self) -> None:
        event = QuantumModelTrained(source="test")
        assert event.event_type == "quantum.model.trained"

    def test_quantum_model_prediction_completed(self) -> None:
        event = QuantumModelPredictionCompleted(source="test")
        assert event.event_type == "quantum.model.prediction_completed"

    def test_quantum_inference_completed(self) -> None:
        event = QuantumInferenceCompleted(source="test")
        assert event.event_type == "quantum.inference.completed"

    def test_quantum_fusion_completed(self) -> None:
        event = QuantumFusionCompleted(source="test")
        assert event.event_type == "quantum.fusion.completed"

    def test_quantum_evaluation_completed(self) -> None:
        event = QuantumEvaluationCompleted(source="test")
        assert event.event_type == "quantum.evaluation.completed"

    def test_feature_encoded(self) -> None:
        event = FeatureEncoded(source="test")
        assert event.event_type == "quantum.features.encoded"

    def test_kernel_computed(self) -> None:
        event = KernelComputed(source="test")
        assert event.event_type == "quantum.kernel.computed"

    def test_events_have_base_fields(self) -> None:
        event = CircuitExecuted(source="executor", data={"shots": 1024})
        assert event.source == "executor"
        assert event.data["shots"] == 1024
        assert event.id is not None
        assert event.timestamp is not None
