"""Tests for quantum backends — LocalSimulatorBackend, BackendManager, Qiskit backends."""

from __future__ import annotations

from typing import Any

import pytest

from q_guardian.quantum.backends.base import QuantumBackend
from q_guardian.quantum.backends.manager import BackendManager
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.data import BackendInfo, CircuitResult
from q_guardian.quantum.enums import BackendStatus, QuantumBackendType
from q_guardian.quantum.exceptions import BackendNotAvailableError


class DummyQuantumBackend(QuantumBackend):
    """Minimal concrete backend for testing ABC contract."""

    def __init__(self, name: str = "dummy", available: bool = True) -> None:
        self._name = name
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def backend_info(self) -> BackendInfo:
        return BackendInfo(
            name=self._name,
            backend_type=QuantumBackendType.CUSTOM,
            status=BackendStatus.HEALTHY if self._available else BackendStatus.UNAVAILABLE,
            num_qubits=5,
        )

    def is_available(self) -> bool:
        return self._available

    async def execute_circuit(
        self, circuit: Any, shots: int = 1024, **kwargs: Any
    ) -> CircuitResult:
        return CircuitResult(
            counts={"0": shots},
            backend=self._name,
            shots=shots,
        )

    def transpile(self, circuit: Any, optimization_level: int = 1, **kwargs: Any) -> Any:
        return circuit


class TestQuantumBackendABC:
    def test_interface_contract(self) -> None:
        backend = DummyQuantumBackend()
        assert backend.name == "dummy"
        assert backend.is_available() is True
        assert backend.backend_info.num_qubits == 5

    def test_health(self) -> None:
        backend = DummyQuantumBackend("test-health")
        h = backend.health()
        assert h["status"] == "healthy"
        assert h["backend"] == "test-health"
        assert h["available"] is True

    def test_supports_operation(self) -> None:
        backend = DummyQuantumBackend()
        assert backend.supports_operation("h") is True
        assert backend.supports_operation("anything") is True

    @pytest.mark.asyncio
    async def test_execute_circuit(self) -> None:
        backend = DummyQuantumBackend()
        result = await backend.execute_circuit({"dummy": True}, shots=512)
        assert result.counts == {"0": 512}
        assert result.backend == "dummy"


class TestLocalSimulatorBackend:
    def setup_method(self) -> None:
        self.backend = LocalSimulatorBackend(num_qubits=5)

    def test_name(self) -> None:
        assert self.backend.name == "local-simulator"

    def test_backend_info(self) -> None:
        info = self.backend.backend_info
        assert info.backend_type == QuantumBackendType.LOCAL
        assert info.supports_simulation is True
        assert info.supports_hardware is False
        assert "statevector" in info.capabilities

    def test_is_available(self) -> None:
        assert self.backend.is_available() is True

    def test_set_availability(self) -> None:
        self.backend.set_availability(False)
        assert self.backend.is_available() is False
        self.backend.set_availability(True)
        assert self.backend.is_available() is True

    @pytest.mark.asyncio
    async def test_execute_empty_circuit(self) -> None:
        circuit = self.backend.create_circuit(2)
        result = await self.backend.execute_circuit(circuit, shots=100)
        assert result.shots == 100
        assert sum(result.counts.values()) == 100
        assert result.backend == "local-simulator"

    @pytest.mark.asyncio
    async def test_execute_h_gate(self) -> None:
        circuit = self.backend.create_circuit(1)
        circuit.add_gate("h", [0])
        circuit.add_measurement([0])
        result = await self.backend.execute_circuit(circuit, shots=1000)
        assert sum(result.counts.values()) == 1000
        assert len(result.probabilities) <= 2

    @pytest.mark.asyncio
    async def test_execute_x_gate(self) -> None:
        circuit = self.backend.create_circuit(1)
        circuit.add_gate("x", [0])
        circuit.add_measurement([0])
        result = await self.backend.execute_circuit(circuit, shots=100)
        assert result.counts.get("1", 0) == 100

    @pytest.mark.asyncio
    async def test_execute_y_gate(self) -> None:
        circuit = self.backend.create_circuit(1)
        circuit.add_gate("y", [0])
        circuit.add_measurement([0])
        result = await self.backend.execute_circuit(circuit, shots=100)
        assert sum(result.counts.values()) == 100

    @pytest.mark.asyncio
    async def test_execute_z_gate(self) -> None:
        circuit = self.backend.create_circuit(1)
        circuit.add_gate("z", [0])
        circuit.add_measurement([0])
        result = await self.backend.execute_circuit(circuit, shots=100)
        assert result.counts.get("0", 0) == 100

    @pytest.mark.asyncio
    async def test_execute_rx_gate(self) -> None:
        circuit = self.backend.create_circuit(1)
        circuit.add_gate("rx", [0], [3.14159])
        circuit.add_measurement([0])
        result = await self.backend.execute_circuit(circuit, shots=100)
        assert sum(result.counts.values()) == 100

    @pytest.mark.asyncio
    async def test_execute_ry_gate(self) -> None:
        circuit = self.backend.create_circuit(1)
        circuit.add_gate("ry", [0], [3.14159])
        circuit.add_measurement([0])
        result = await self.backend.execute_circuit(circuit, shots=1000)
        assert sum(result.counts.values()) == 1000

    @pytest.mark.asyncio
    async def test_execute_rz_gate(self) -> None:
        circuit = self.backend.create_circuit(1)
        circuit.add_gate("rz", [0], [1.57])
        circuit.add_measurement([0])
        result = await self.backend.execute_circuit(circuit, shots=100)
        assert sum(result.counts.values()) == 100

    @pytest.mark.asyncio
    async def test_execute_cx_gate(self) -> None:
        circuit = self.backend.create_circuit(2)
        circuit.add_gate("x", [0])
        circuit.add_gate("cx", [0, 1])
        circuit.add_measurement([0, 1])
        result = await self.backend.execute_circuit(circuit, shots=100)
        assert result.counts.get("11", 0) == 100

    @pytest.mark.asyncio
    async def test_execute_cz_gate(self) -> None:
        circuit = self.backend.create_circuit(2)
        circuit.add_gate("x", [0])
        circuit.add_gate("x", [1])
        circuit.add_gate("cz", [0, 1])
        circuit.add_measurement([0, 1])
        result = await self.backend.execute_circuit(circuit, shots=100)
        assert result.counts.get("11", 0) == 100

    @pytest.mark.asyncio
    async def test_execute_from_dict(self) -> None:
        circuit_dict = {
            "num_qubits": 2,
            "gates": [
                {"type": "x", "qubits": [0], "params": []},
                {"type": "cx", "qubits": [0, 1], "params": []},
            ],
            "measurements": [0, 1],
        }
        result = await self.backend.execute_circuit(circuit_dict, shots=100)
        assert result.counts.get("11", 0) == 100

    def test_transpile_passthrough(self) -> None:
        circuit = self.backend.create_circuit(2)
        transpiled = self.backend.transpile(circuit)
        assert transpiled is circuit

    def test_create_circuit(self) -> None:
        circuit = self.backend.create_circuit(3)
        assert circuit.num_qubits == 3

    def test_create_circuit_default_qubits(self) -> None:
        circuit = self.backend.create_circuit()
        assert circuit.num_qubits == 5

    @pytest.mark.asyncio
    async def test_execution_time_recorded(self) -> None:
        circuit = self.backend.create_circuit(1)
        result = await self.backend.execute_circuit(circuit, shots=10)
        assert result.execution_time_ms >= 0.0

    @pytest.mark.asyncio
    async def test_metadata_recorded(self) -> None:
        circuit = self.backend.create_circuit(2)
        circuit.add_gate("h", [0])
        result = await self.backend.execute_circuit(circuit, shots=10)
        assert "num_qubits" in result.metadata
        assert "circuit_depth" in result.metadata

    def test_health_check(self) -> None:
        h = self.backend.health()
        assert h["status"] == "healthy"
        assert h["num_qubits"] == 5


class TestBackendManager:
    def setup_method(self) -> None:
        self.manager = BackendManager()

    def test_register_and_get(self) -> None:
        backend = DummyQuantumBackend("test-reg")
        self.manager.register_backend(backend)
        assert self.manager.get_backend("test-reg") is backend

    def test_unregister(self) -> None:
        backend = DummyQuantumBackend("unreg")
        self.manager.register_backend(backend)
        assert self.manager.unregister_backend("unreg") is True
        assert self.manager.get_backend("unreg") is None

    def test_unregister_nonexistent(self) -> None:
        assert self.manager.unregister_backend("nope") is False

    def test_list_backends(self) -> None:
        self.manager.register_backend(DummyQuantumBackend("a"))
        self.manager.register_backend(DummyQuantumBackend("b"))
        names = self.manager.list_backends()
        assert "a" in names
        assert "b" in names

    def test_set_active_backend(self) -> None:
        backend = DummyQuantumBackend("active-test")
        self.manager.register_backend(backend)
        self.manager.set_active_backend("active-test")
        assert self.manager.active_backend is backend

    def test_set_active_nonexistent(self) -> None:
        with pytest.raises(BackendNotAvailableError):
            self.manager.set_active_backend("nonexistent")

    def test_get_active_or_fallback(self) -> None:
        backend = DummyQuantumBackend("fallback-test")
        self.manager.register_backend(backend)
        active = self.manager.get_active_or_fallback()
        assert active.name == "fallback-test"

    def test_get_active_or_fallback_unavailable(self) -> None:
        backend = DummyQuantumBackend("unavail", available=False)
        self.manager.register_backend(backend)
        with pytest.raises(BackendNotAvailableError):
            self.manager.get_active_or_fallback()

    def test_fallback_order(self) -> None:
        b1 = DummyQuantumBackend("primary", available=False)
        b2 = DummyQuantumBackend("secondary", available=True)
        self.manager.register_backend(b1)
        self.manager.register_backend(b2)
        self.manager.set_fallback_order(["primary", "secondary"])
        active = self.manager.get_active_or_fallback()
        assert active.name == "secondary"

    def test_health_check(self) -> None:
        self.manager.register_backend(DummyQuantumBackend("h1"))
        self.manager.register_backend(DummyQuantumBackend("h2"))
        health = self.manager.health_check()
        assert "h1" in health
        assert "h2" in health

    def test_get_available_backends(self) -> None:
        self.manager.register_backend(DummyQuantumBackend("avail", available=True))
        self.manager.register_backend(DummyQuantumBackend("unavail", available=False))
        available = self.manager.get_available_backends()
        assert "avail" in available
        assert "unavail" not in available

    def test_backend_count(self) -> None:
        assert self.manager.backend_count == 0
        self.manager.register_backend(DummyQuantumBackend("c1"))
        assert self.manager.backend_count == 1

    def test_create_default_backend(self) -> None:
        backend = self.manager.create_default_backend()
        assert isinstance(backend, LocalSimulatorBackend)
        assert self.manager.backend_count == 1
        assert self.manager.active_backend is backend

    def test_unregister_active_clears_active(self) -> None:
        backend = DummyQuantumBackend("the-active")
        self.manager.register_backend(backend)
        self.manager.set_active_backend("the-active")
        assert self.manager.active_backend is backend
        self.manager.unregister_backend("the-active")
        assert self.manager.active_backend is None
