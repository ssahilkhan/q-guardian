"""Tests for CircuitExecutor and QuantumPlugin."""

from __future__ import annotations

import pytest

from q_guardian.quantum.execution.executor import CircuitExecutor
from q_guardian.quantum.backends.manager import BackendManager
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.config import QuantumBackendConfig
from q_guardian.quantum.exceptions import CircuitExecutionError


class TestCircuitExecutor:
    def setup_method(self) -> None:
        self.manager = BackendManager()
        self.backend = LocalSimulatorBackend(num_qubits=5)
        self.manager.register_backend(self.backend)
        self.manager.set_active_backend("local-simulator")
        self.executor = CircuitExecutor(self.manager)

    @pytest.mark.asyncio
    async def test_execute_circuit(self) -> None:
        circuit = self.backend.create_circuit(1)
        circuit.add_gate("x", [0])
        result = await self.executor.execute(circuit, shots=100)
        assert result.counts.get("1", 0) == 100

    @pytest.mark.asyncio
    async def test_execute_with_backend_name(self) -> None:
        circuit = self.backend.create_circuit(1)
        result = await self.executor.execute(circuit, shots=50, backend_name="local-simulator")
        assert sum(result.counts.values()) == 50

    @pytest.mark.asyncio
    async def test_execute_unknown_backend(self) -> None:
        circuit = self.backend.create_circuit(1)
        with pytest.raises(CircuitExecutionError):
            await self.executor.execute(circuit, backend_name="nonexistent")

    @pytest.mark.asyncio
    async def test_execution_count(self) -> None:
        circuit = self.backend.create_circuit(1)
        assert self.executor.execution_count == 0
        await self.executor.execute(circuit, shots=10)
        assert self.executor.execution_count == 1
        await self.executor.execute(circuit, shots=10)
        assert self.executor.execution_count == 2

    @pytest.mark.asyncio
    async def test_average_execution_time(self) -> None:
        circuit = self.backend.create_circuit(1)
        assert self.executor.average_execution_time_ms == 0.0
        await self.executor.execute(circuit, shots=10)
        assert self.executor.average_execution_time_ms >= 0.0

    def test_get_backend_for_model(self) -> None:
        backend = self.executor.get_backend_for_model(num_qubits=3)
        assert backend is not None

    def test_get_backend_for_model_no_backends(self) -> None:
        empty_manager = BackendManager()
        executor = CircuitExecutor(empty_manager)
        with pytest.raises(CircuitExecutionError):
            executor.get_backend_for_model(num_qubits=3)

    def test_health(self) -> None:
        h = self.executor.health()
        assert h["status"] == "healthy"
        assert h["execution_count"] == 0


class TestQuantumPlugin:
    def setup_method(self) -> None:
        from q_guardian.quantum.config import QuantumConfig
        from q_guardian.quantum.plugin import QuantumAnalysisPlugin

        self.config = QuantumConfig(enabled=True)
        self.plugin = QuantumAnalysisPlugin(self.config)

    def test_plugin_properties(self) -> None:
        assert self.plugin.name == "quantum-analysis"
        assert self.plugin.version == "1.0.0"
        assert "quantum_analyzer" in self.plugin.interfaces

    def test_register_model(self) -> None:
        from q_guardian.quantum.models.base import BaseQuantumModel
        from q_guardian.quantum.data import QuantumModelMetadata
        from q_guardian.quantum.enums import QuantumModelType, QuantumBackendType
        from typing import Any

        class DummyQuantumModel(BaseQuantumModel):
            @property
            def name(self):
                return "test-qm"

            @property
            def metadata(self):
                from q_guardian.ml.data import ModelMetadata
                return ModelMetadata(name="test", model_type="classification", backend="custom")

            @property
            def quantum_metadata(self):
                return QuantumModelMetadata(
                    name="test-qm",
                    model_type=QuantumModelType.QSVM,
                    backend_type=QuantumBackendType.LOCAL,
                )

            @property
            def is_trained(self):
                return False

            async def predict(self, features):
                return {"predicted_class": "benign", "confidence": 0.9}

            async def predict_quantum(self, features):
                from q_guardian.quantum.data import QuantumInferenceResult
                return QuantumInferenceResult(model_name="test-qm")

            async def classify_quantum(self, prompt, features):
                from q_guardian.security.extensibility import DetectionResult
                return DetectionResult(detector_name="test-qm")

        model = DummyQuantumModel()
        self.plugin.register_model(model)
        assert "test-qm" in self.plugin.list_models()

    def test_unregister_model(self) -> None:
        from q_guardian.quantum.models.base import BaseQuantumModel
        from q_guardian.quantum.data import QuantumModelMetadata
        from q_guardian.quantum.enums import QuantumModelType, QuantumBackendType

        class DummyQM(BaseQuantumModel):
            @property
            def name(self):
                return "dummy-qm"

            @property
            def metadata(self):
                from q_guardian.ml.data import ModelMetadata
                return ModelMetadata(name="dummy", model_type="classification", backend="custom")

            @property
            def quantum_metadata(self):
                return QuantumModelMetadata(name="dummy-qm", model_type=QuantumModelType.VQC, backend_type=QuantumBackendType.LOCAL)

            @property
            def is_trained(self):
                return False

            async def predict(self, features):
                return {}

            async def predict_quantum(self, features):
                from q_guardian.quantum.data import QuantumInferenceResult
                return QuantumInferenceResult(model_name="dummy-qm")

            async def classify_quantum(self, prompt, features):
                from q_guardian.security.extensibility import DetectionResult
                return DetectionResult(detector_name="dummy-qm")

        model = DummyQM()
        self.plugin.register_model(model)
        assert self.plugin.unregister_model("dummy-qm") is True
        assert self.plugin.unregister_model("dummy-qm") is False

    def test_get_model(self) -> None:
        assert self.plugin.get_model("nonexistent") is None

    def test_list_models_empty(self) -> None:
        assert self.plugin.list_models() == []

    @pytest.mark.asyncio
    async def test_initialize(self) -> None:
        from q_guardian.framework.context import FrameworkContext
        from q_guardian.events.bus import EventBus
        from q_guardian.plugins.registry import PluginRegistry
        from q_guardian.hooks.manager import HookManager
        from q_guardian.framework.config import FrameworkConfig
        import logging

        ctx = FrameworkContext(
            logger=logging.getLogger("test"),
            config=FrameworkConfig(),
            event_bus=EventBus(),
            plugin_registry=PluginRegistry(),
            hook_manager=HookManager(),
        )
        await self.plugin.initialize(ctx)
        assert self.plugin._context is ctx

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        await self.plugin.start()
        await self.plugin.stop()

    def test_health(self) -> None:
        h = self.plugin.health()
        assert h["status"] == "healthy"
        assert h["enabled"] is True
        assert h["models"] == 0

    def test_configuration(self) -> None:
        config = self.plugin.configuration()
        assert "enabled" in config
        assert config["enabled"] is True
