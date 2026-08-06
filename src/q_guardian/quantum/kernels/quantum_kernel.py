"""Quantum kernel implementation using feature map overlap."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

from q_guardian.quantum.data import QuantumCircuitInfo
from q_guardian.quantum.enums import CircuitType
from q_guardian.quantum.kernels.base import QuantumKernel

if TYPE_CHECKING:
    from q_guardian.quantum.backends.base import QuantumBackend
    from q_guardian.quantum.feature_maps.base import QuantumFeatureMap

logger = structlog.get_logger("quantum.kernel")

# Process-wide background event loop used to run the (async) backend from
# synchronous kernel calls. Creating a fresh event loop per kernel
# evaluation exhausts Windows event-loop resources and deadlocks after
# thousands of evaluations (observed during K-fold benchmark ablation), so
# a single background loop is shared for the lifetime of the process.
_KERNEL_LOOP_LOCK = threading.Lock()
_KERNEL_LOOP: asyncio.AbstractEventLoop | None = None
_KERNEL_THREAD: threading.Thread | None = None


def _kernel_loop() -> asyncio.AbstractEventLoop:
    """Return the shared background event loop, starting it on demand."""
    global _KERNEL_LOOP, _KERNEL_THREAD
    with _KERNEL_LOOP_LOCK:
        if _KERNEL_LOOP is None or _KERNEL_LOOP.is_closed():
            _KERNEL_LOOP = asyncio.new_event_loop()
            _KERNEL_THREAD = threading.Thread(
                target=_KERNEL_LOOP.run_forever,
                name="quantum-kernel-loop",
                daemon=True,
            )
            _KERNEL_THREAD.start()
        return _KERNEL_LOOP


class QuantumKernelEstimator(QuantumKernel):
    """Quantum kernel estimator using feature map overlap.

    Computes the quantum kernel by encoding data points into quantum
    circuits and measuring the overlap (fidelity) between encoded states.

    K(x1, x2) = |<φ(x1)|φ(x2)>|²

    This is computed via the SWAP test or by running the combined
    circuit and measuring probability of the all-zero outcome.
    """

    def __init__(
        self,
        feature_map: QuantumFeatureMap,
        backend: QuantumBackend,
        shots: int = 4096,
    ) -> None:
        self._feature_map = feature_map
        self._backend = backend
        self._shots = shots
        self._cache: dict[tuple[int, int], float] = {}

    @property
    def name(self) -> str:
        return f"quantum-kernel-{self._feature_map.name}"

    @property
    def num_qubits(self) -> int:
        return self._feature_map.num_qubits

    @property
    def feature_map(self) -> QuantumFeatureMap:
        return self._feature_map

    @property
    def backend(self) -> QuantumBackend:
        return self._backend

    def compute_kernel_matrix(
        self,
        x1: list[list[float]],
        x2: list[list[float]] | None = None,
    ) -> list[list[float]]:
        symmetric = x2 is None
        if x2 is None:
            x2 = x1

        n1, n2 = len(x1), len(x2)
        matrix = np.zeros((n1, n2), dtype=np.float64)

        for i in range(n1):
            start = i if symmetric else 0
            for j in range(start, n2):
                k_val = self.evaluate(x1[i], x2[j])
                matrix[i][j] = k_val
                if symmetric and i != j:
                    matrix[j][i] = k_val

        return matrix.tolist()

    def evaluate(self, x1: list[float], x2: list[float]) -> float:
        cache_key = (
            id(x1) if len(x1) < 50 else hash(tuple(x1)),
            id(x2) if len(x2) < 50 else hash(tuple(x2)),
        )
        if cache_key in self._cache:
            return self._cache[cache_key]

        encoded1 = self._feature_map.encode(x1)
        encoded2 = self._feature_map.encode(x2)

        combined_circuit = self._build_kernel_circuit(encoded1.circuit, encoded2.circuit)
        result = self._execute_kernel_circuit(combined_circuit)

        # SWAP test: only the ancilla is measured. The local simulator
        # samples every qubit, so sum the probabilities of the outcomes
        # where the ancilla (the most significant bit, qubit 0) is 0:
        #   P(ancilla=0) = (1 + |<phi(x1)|phi(x2)>|^2) / 2
        prob0 = sum(v for k, v in result.items() if k.startswith("0"))
        k_value = max(0.0, min(1.0, 2.0 * prob0 - 1.0))

        self._cache[cache_key] = k_value
        return k_value

    def _build_kernel_circuit(
        self,
        circuit1: dict[str, Any],
        circuit2: dict[str, Any],
    ) -> dict[str, Any]:
        n = self._feature_map.num_qubits
        ancilla = 0
        # Register A on qubits 1..n, register B on qubits n+1..2n.
        total_qubits = n * 2 + 1

        gates: list[dict[str, Any]] = []

        for gate in circuit1.get("gates", []):
            new_qubits = [q + 1 for q in gate["qubits"]]
            gates.append(
                {"type": gate["type"], "qubits": new_qubits, "params": gate.get("params", [])}
            )

        for gate in circuit2.get("gates", []):
            new_qubits = [q + 1 + n for q in gate["qubits"]]
            gates.append(
                {"type": gate["type"], "qubits": new_qubits, "params": gate.get("params", [])}
            )

        # Swap test: H on ancilla, controlled-swap between the two
        # registers, then H on ancilla again.
        gates.append({"type": "h", "qubits": [ancilla], "params": []})
        for i in range(n):
            gates.append({"type": "cswap", "qubits": [ancilla, 1 + i, 1 + n + i], "params": []})
        gates.append({"type": "h", "qubits": [ancilla], "params": []})

        return {
            "num_qubits": total_qubits,
            "gates": gates,
            "measurements": [ancilla],
        }

    def _execute_kernel_circuit(self, circuit: dict[str, Any]) -> dict[str, float]:
        coro = self._backend.execute_circuit(circuit, shots=self._shots)
        future = asyncio.run_coroutine_threadsafe(coro, _kernel_loop())
        result = future.result(timeout=30.0)
        return result.probabilities

    def get_circuit_info(self) -> QuantumCircuitInfo:
        n = self._feature_map.num_qubits
        return QuantumCircuitInfo(
            name=self.name,
            circuit_type=CircuitType.KERNEL,
            num_qubits=n * 2 + 1,
            depth=n * 2 + 3,
            gate_count=n * 2 + 2 + n,
        )

    def clear_cache(self) -> None:
        """Clear the kernel evaluation cache."""
        self._cache.clear()
