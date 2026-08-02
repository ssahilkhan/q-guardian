"""Tests for quantum kernels."""

from __future__ import annotations

import pytest

from q_guardian.quantum.kernels.base import QuantumKernel
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.data import QuantumCircuitInfo


class DummyKernel(QuantumKernel):
    """Minimal concrete kernel for testing ABC contract."""

    @property
    def name(self) -> str:
        return "dummy-kernel"

    @property
    def num_qubits(self) -> int:
        return 4

    def compute_kernel_matrix(
        self, X1: list[list[float]], X2: list[list[float]] | None = None
    ) -> list[list[float]]:
        n = len(X1)
        return [[1.0 if i == j else 0.5 for j in range(n)] for i in range(n)]

    def evaluate(self, x1: list[float], x2: list[float]) -> float:
        return 1.0 if x1 == x2 else 0.5

    def get_circuit_info(self) -> QuantumCircuitInfo:
        return QuantumCircuitInfo(
            circuit_type="kernel",
            num_qubits=self.num_qubits,
        )


class TestQuantumKernelABC:
    def test_interface_contract(self) -> None:
        kernel = DummyKernel()
        assert kernel.name == "dummy-kernel"
        assert kernel.num_qubits == 4

    def test_compute_kernel_matrix(self) -> None:
        kernel = DummyKernel()
        X = [[1.0, 2.0], [3.0, 4.0]]
        matrix = kernel.compute_kernel_matrix(X)
        assert len(matrix) == 2
        assert len(matrix[0]) == 2
        assert matrix[0][0] == 1.0
        assert matrix[0][1] == 0.5

    def test_evaluate(self) -> None:
        kernel = DummyKernel()
        assert kernel.evaluate([1.0], [1.0]) == 1.0
        assert kernel.evaluate([1.0], [2.0]) == 0.5

    def test_health(self) -> None:
        kernel = DummyKernel()
        h = kernel.health()
        assert h["status"] == "healthy"
        assert h["kernel"] == "dummy-kernel"


class TestQuantumKernelEstimator:
    def setup_method(self) -> None:
        self.backend = LocalSimulatorBackend(num_qubits=8)
        self.feature_map = AngleEncodingMap(num_qubits=3)

    def test_name(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        assert "angle-encoding" in kernel.name

    def test_num_qubits(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        assert kernel.num_qubits == 3

    def test_evaluate_same_vector(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        k_val = kernel.evaluate([0.5, 1.0, 1.5], [0.5, 1.0, 1.5])
        assert 0.0 <= k_val <= 1.0

    def test_evaluate_different_vectors(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        k_val = kernel.evaluate([0.5, 1.0, 1.5], [2.0, 0.5, 0.1])
        assert 0.0 <= k_val <= 1.0

    def test_compute_kernel_matrix_symmetric(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        X = [[0.5, 1.0, 1.5], [2.0, 0.5, 0.1]]
        matrix = kernel.compute_kernel_matrix(X)
        assert len(matrix) == 2
        assert len(matrix[0]) == 2
        assert abs(matrix[0][1] - matrix[1][0]) < 0.01

    def test_compute_kernel_matrix_diagonal(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        X = [[0.5, 1.0, 1.5], [2.0, 0.5, 0.1]]
        matrix = kernel.compute_kernel_matrix(X)
        for i in range(2):
            assert matrix[i][i] >= 0.0

    def test_compute_kernel_matrix_with_X2(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        X1 = [[0.5, 1.0, 1.5]]
        X2 = [[2.0, 0.5, 0.1], [0.5, 1.0, 1.5]]
        matrix = kernel.compute_kernel_matrix(X1, X2)
        assert len(matrix) == 1
        assert len(matrix[0]) == 2

    def test_get_circuit_info(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        info = kernel.get_circuit_info()
        # SWAP test: 2n data qubits + 1 ancilla.
        assert info.num_qubits == 7
        assert info.circuit_type.value == "kernel"

    def test_clear_cache(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        kernel.evaluate([0.5, 1.0, 1.5], [0.5, 1.0, 1.5])
        assert len(kernel._cache) > 0
        kernel.clear_cache()
        assert len(kernel._cache) == 0

    def test_health(self) -> None:
        kernel = QuantumKernelEstimator(self.feature_map, self.backend)
        h = kernel.health()
        assert h["status"] == "healthy"
