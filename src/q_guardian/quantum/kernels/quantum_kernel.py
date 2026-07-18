"""Quantum kernel implementation using feature map overlap."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import structlog

from q_guardian.quantum.backends.base import QuantumBackend
from q_guardian.quantum.data import QuantumCircuitInfo
from q_guardian.quantum.enums import CircuitType
from q_guardian.quantum.feature_maps.base import QuantumFeatureMap
from q_guardian.quantum.kernels.base import QuantumKernel

logger = structlog.get_logger("quantum.kernel")


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
        X1: list[list[float]],
        X2: list[list[float]] | None = None,
    ) -> list[list[float]]:
        if X2 is None:
            X2 = X1

        n1, n2 = len(X1), len(X2)
        matrix = np.zeros((n1, n2), dtype=np.float64)

        for i in range(n1):
            for j in range(n2):
                k_val = self.evaluate(X1[i], X2[j])
                matrix[i][j] = k_val

        return matrix.tolist()

    def evaluate(self, x1: list[float], x2: list[float]) -> float:
        cache_key = (id(x1) if len(x1) < 50 else hash(tuple(x1)),
                     id(x2) if len(x2) < 50 else hash(tuple(x2)))
        if cache_key in self._cache:
            return self._cache[cache_key]

        encoded1 = self._feature_map.encode(x1)
        encoded2 = self._feature_map.encode(x2)

        combined_circuit = self._build_kernel_circuit(encoded1.circuit, encoded2.circuit)
        result = self._execute_kernel_circuit(combined_circuit)

        k_value = result.get("0" * combined_circuit.get("num_qubits", self.num_qubits * 2), 0.0)
        k_value = max(0.0, min(1.0, k_value))

        self._cache[cache_key] = k_value
        return k_value

    def _build_kernel_circuit(
        self,
        circuit1: dict[str, Any],
        circuit2: dict[str, Any],
    ) -> dict[str, Any]:
        n = self._feature_map.num_qubits
        total_qubits = n * 2

        gates: list[dict[str, Any]] = []

        for gate in circuit1.get("gates", []):
            new_qubits = [q for q in gate["qubits"]]
            gates.append({"type": gate["type"], "qubits": new_qubits, "params": gate.get("params", [])})

        for gate in circuit2.get("gates", []):
            new_qubits = [q + n for q in gate["qubits"]]
            gates.append({"type": gate["type"], "qubits": new_qubits, "params": gate.get("params", [])})

        gates.append({"type": "h", "qubits": [0], "params": []})

        for i in range(n):
            gates.append({"type": "cx", "qubits": [i, i + n], "params": []})

        gates.append({"type": "h", "qubits": [0], "params": []})

        return {
            "num_qubits": total_qubits,
            "gates": gates,
            "measurements": list(range(total_qubits)),
        }

    def _execute_kernel_circuit(self, circuit: dict[str, Any]) -> dict[str, float]:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self._backend.execute_circuit(circuit, shots=self._shots),
                )
                result = future.result(timeout=30.0)
        except RuntimeError:
            result = asyncio.run(
                self._backend.execute_circuit(circuit, shots=self._shots)
            )

        return result.probabilities

    def get_circuit_info(self) -> QuantumCircuitInfo:
        n = self._feature_map.num_qubits
        return QuantumCircuitInfo(
            name=self.name,
            circuit_type=CircuitType.KERNEL,
            num_qubits=n * 2,
            depth=n * 2,
            gate_count=n * 4,
        )

    def clear_cache(self) -> None:
        """Clear the kernel evaluation cache."""
        self._cache.clear()
