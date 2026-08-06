"""Local statevector simulator backend (no external dependencies)."""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np
import structlog

from q_guardian.quantum.backends.base import QuantumBackend
from q_guardian.quantum.data import BackendInfo, CircuitResult
from q_guardian.quantum.enums import BackendStatus, QuantumBackendType

logger = structlog.get_logger("quantum.local_simulator")


class _LocalCircuit:
    """Minimal internal circuit representation for the local simulator.

    Stores gates as a list of (gate_type, qubits, params) tuples
    and measurements as a list of qubit indices.
    """

    def __init__(self, num_qubits: int) -> None:
        self.num_qubits = num_qubits
        self.gates: list[tuple[str, list[int], list[float]]] = []
        self.measurements: list[int] = []
        self._depth = 0

    def add_gate(
        self, gate_type: str, qubits: list[int], params: list[float] | None = None
    ) -> None:
        self.gates.append((gate_type, qubits, params or []))
        self._depth += 1

    def add_measurement(self, qubits: list[int]) -> None:
        self.measurements.extend(qubits)

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def gate_count(self) -> int:
        return len(self.gates)


class LocalSimulatorBackend(QuantumBackend):
    """Pure-Python statevector simulator backend.

    No external quantum SDK required. Provides deterministic simulation
    of quantum circuits for development, testing, and CI environments.

    Supports: H, X, Y, Z, Rx, Ry, Rz, CX, CZ, Measure.
    """

    def __init__(self, num_qubits: int = 5, shots: int = 1024) -> None:
        self._num_qubits = num_qubits
        self._shots = shots
        self._available = True
        self._execution_count = 0

    @property
    def name(self) -> str:
        return "local-simulator"

    @property
    def backend_info(self) -> BackendInfo:
        return BackendInfo(
            name=self.name,
            backend_type=QuantumBackendType.LOCAL,
            status=BackendStatus.HEALTHY if self._available else BackendStatus.UNAVAILABLE,
            num_qubits=self._num_qubits,
            max_shots=65536,
            supports_simulation=True,
            supports_hardware=False,
            capabilities=["statevector", "measurements", "expectation_values"],
        )

    def is_available(self) -> bool:
        return self._available

    def set_availability(self, available: bool) -> None:
        """Set backend availability (for testing)."""
        self._available = available

    async def execute_circuit(
        self,
        circuit: Any,
        shots: int = 1024,
        **kwargs: Any,
    ) -> CircuitResult:
        start = time.monotonic()

        if isinstance(circuit, _LocalCircuit):
            local_circuit = circuit
        elif isinstance(circuit, dict):
            local_circuit = self._from_dict(circuit)
        else:
            local_circuit = (
                self._from_dict(circuit) if hasattr(circuit, "__dict__") else self._from_dict({})
            )

        actual_shots = min(shots, 65536)
        counts = self._simulate(local_circuit, actual_shots)
        total = sum(counts.values())
        probabilities = {k: v / total for k, v in counts.items()} if total > 0 else {}

        elapsed_ms = (time.monotonic() - start) * 1000
        self._execution_count += 1

        return CircuitResult(
            counts=counts,
            probabilities=probabilities,
            backend=self.name,
            shots=actual_shots,
            execution_time_ms=round(elapsed_ms, 3),
            metadata={
                "num_qubits": local_circuit.num_qubits,
                "circuit_depth": local_circuit.depth,
                "gate_count": local_circuit.gate_count,
            },
        )

    def transpile(self, circuit: Any, optimization_level: int = 1, **kwargs: Any) -> Any:
        return circuit

    def _simulate(self, circuit: _LocalCircuit, shots: int) -> dict[str, int]:
        n = circuit.num_qubits
        state = np.zeros(2**n, dtype=complex)
        state[0] = 1.0

        for gate_type, qubits, params in circuit.gates:
            state = self._apply_gate(state, gate_type, qubits, params, n)

        probs = np.abs(state) ** 2
        counts_array = np.random.choice(2**n, size=shots, p=probs)
        counts: dict[str, int] = {}
        for idx in counts_array:
            key = format(int(idx), f"0{n}b")
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _apply_gate(
        self,
        state: np.ndarray,
        gate_type: str,
        qubits: list[int],
        params: list[float],
        num_qubits: int,
    ) -> np.ndarray:
        if gate_type == "h":
            return self._apply_single(state, self._hadamard(), qubits[0], num_qubits)
        elif gate_type == "x":
            return self._apply_single(state, self._pauli_x(), qubits[0], num_qubits)
        elif gate_type == "y":
            return self._apply_single(state, self._pauli_y(), qubits[0], num_qubits)
        elif gate_type == "z":
            return self._apply_single(state, self._pauli_z(), qubits[0], num_qubits)
        elif gate_type == "rx":
            return self._apply_single(state, self._rx(params[0]), qubits[0], num_qubits)
        elif gate_type == "ry":
            return self._apply_single(state, self._ry(params[0]), qubits[0], num_qubits)
        elif gate_type == "rz":
            return self._apply_single(state, self._rz(params[0]), qubits[0], num_qubits)
        elif gate_type == "cx":
            return self._apply_cx(state, qubits[0], qubits[1], num_qubits)
        elif gate_type == "cz":
            return self._apply_cz(state, qubits[0], qubits[1], num_qubits)
        elif gate_type == "swap":
            return self._apply_swap(state, qubits[0], qubits[1], num_qubits)
        elif gate_type == "cswap":
            return self._apply_cswap(state, qubits[0], qubits[1], qubits[2], num_qubits)
        return state

    @staticmethod
    def _hadamard() -> np.ndarray:
        return np.array([[1, 1], [1, -1]], dtype=complex) / math.sqrt(2)

    @staticmethod
    def _pauli_x() -> np.ndarray:
        return np.array([[0, 1], [1, 0]], dtype=complex)

    @staticmethod
    def _pauli_y() -> np.ndarray:
        return np.array([[0, -1j], [1j, 0]], dtype=complex)

    @staticmethod
    def _pauli_z() -> np.ndarray:
        return np.array([[1, 0], [0, -1]], dtype=complex)

    @staticmethod
    def _rx(theta: float) -> np.ndarray:
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        return np.array([[c, -1j * s], [-1j * s, c]], dtype=complex)

    @staticmethod
    def _ry(theta: float) -> np.ndarray:
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        return np.array([[c, -s], [s, c]], dtype=complex)

    @staticmethod
    def _rz(theta: float) -> np.ndarray:
        return np.array(
            [
                [complex(math.cos(theta / 2), -math.sin(theta / 2)), 0],
                [0, complex(math.cos(theta / 2), math.sin(theta / 2))],
            ],
            dtype=complex,
        )

    @staticmethod
    def _apply_single(
        state: np.ndarray, matrix: np.ndarray, qubit: int, num_qubits: int
    ) -> np.ndarray:
        # Qubit q corresponds to index bit (num_qubits-1-q). Reshape so that
        # bit is the middle axis: reshape(2^qubit, 2, 2^(num_qubits-1-qubit)).
        bit = num_qubits - 1 - qubit
        a = state.reshape(2**qubit, 2, 2**bit)
        s0 = a[:, 0, :]
        s1 = a[:, 1, :]
        out = np.empty_like(state)
        b = out.reshape(2**qubit, 2, 2**bit)
        b[:, 0, :] = matrix[0, 0] * s0 + matrix[0, 1] * s1
        b[:, 1, :] = matrix[1, 0] * s0 + matrix[1, 1] * s1
        return out

    @staticmethod
    def _apply_cx(state: np.ndarray, control: int, target: int, num_qubits: int) -> np.ndarray:
        c = num_qubits - 1 - control
        t = num_qubits - 1 - target
        idx = np.arange(state.shape[0])
        cbit = (idx >> c) & 1
        mapped = idx ^ (1 << t)
        return state[np.where(cbit == 1, mapped, idx)]

    @staticmethod
    def _apply_swap(state: np.ndarray, q0: int, q1: int, num_qubits: int) -> np.ndarray:
        b0 = num_qubits - 1 - q0
        b1 = num_qubits - 1 - q1
        idx = np.arange(state.shape[0])
        i0 = (idx >> b0) & 1
        i1 = (idx >> b1) & 1
        mapped = idx & ~(1 << b0) & ~(1 << b1)
        mapped |= i1 << b0
        mapped |= i0 << b1
        result: np.ndarray = state[mapped]
        return result

    @staticmethod
    def _apply_cswap(
        state: np.ndarray, control: int, q1: int, q2: int, num_qubits: int
    ) -> np.ndarray:
        cb = num_qubits - 1 - control
        b1 = num_qubits - 1 - q1
        b2 = num_qubits - 1 - q2
        idx = np.arange(state.shape[0])
        cbit = (idx >> cb) & 1
        i1 = (idx >> b1) & 1
        i2 = (idx >> b2) & 1
        mapped = idx & ~(1 << b1) & ~(1 << b2)
        mapped |= i2 << b1
        mapped |= i1 << b2
        return state[np.where(cbit == 1, mapped, idx)]

    @staticmethod
    def _apply_cz(state: np.ndarray, qubit1: int, qubit2: int, num_qubits: int) -> np.ndarray:
        out = state.copy()
        c = num_qubits - 1 - qubit1
        t = num_qubits - 1 - qubit2
        idx = np.arange(state.shape[0])
        mask = ((idx >> c) & 1) & ((idx >> t) & 1)
        out[mask] *= -1
        return out

    def _from_dict(self, data: Any) -> _LocalCircuit:
        if isinstance(data, dict) and "num_qubits" in data:
            c = _LocalCircuit(data["num_qubits"])
            for gate in data.get("gates", []):
                c.add_gate(gate["type"], gate["qubits"], gate.get("params"))
            if "measurements" in data:
                c.add_measurement(data["measurements"])
            return c
        return _LocalCircuit(self._num_qubits)

    def create_circuit(self, num_qubits: int | None = None) -> _LocalCircuit:
        """Create an empty local circuit.

        Args:
            num_qubits: Number of qubits (defaults to backend num_qubits).

        Returns:
            A new _LocalCircuit instance.
        """
        return _LocalCircuit(num_qubits or self._num_qubits)
