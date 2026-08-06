"""Abstract base class for quantum kernels."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from q_guardian.quantum.data import QuantumCircuitInfo


class QuantumKernel(ABC):
    """Abstract base class for quantum kernel computation.

    Quantum kernels compute similarity between data points by
    measuring overlap in quantum feature space. They are used
    by QSVM and kernel-based classifiers.

    Integration point:
      QSVMModel uses QuantumKernel to compute kernel matrices.
      KernelTrainer trains kernel hyperparameters.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the kernel name."""

    @property
    @abstractmethod
    def num_qubits(self) -> int:
        """Return the number of qubits used by the kernel."""

    @abstractmethod
    def compute_kernel_matrix(
        self,
        x1: list[list[float]],
        x2: list[list[float]] | None = None,
    ) -> list[list[float]]:
        """Compute the kernel matrix between two sets of data points.

        Args:
            x1: First set of feature vectors.
            x2: Second set of feature vectors. If None, computes x1 vs x1.

        Returns:
            Kernel matrix as nested list.
        """

    @abstractmethod
    def evaluate(self, x1: list[float], x2: list[float]) -> float:
        """Compute the kernel value between two data points.

        Args:
            x1: First feature vector.
            x2: Second feature vector.

        Returns:
            Kernel similarity score.
        """

    @abstractmethod
    def get_circuit_info(self) -> QuantumCircuitInfo:
        """Return information about the kernel circuit."""

    def health(self) -> dict[str, Any]:
        """Return kernel health status."""
        return {
            "status": "healthy",
            "kernel": self.name,
            "num_qubits": self.num_qubits,
        }
