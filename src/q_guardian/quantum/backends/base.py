"""Abstract base class for quantum backend implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from q_guardian.quantum.data import BackendInfo, CircuitResult


class QuantumBackend(ABC):
    """Abstract base class for quantum computing backends.

    Every quantum backend (Qiskit Aer, PennyLane, CUDA-Q, IBM Runtime,
    etc.) must implement this interface. This ensures the rest of the
    framework never directly imports any quantum SDK.

    Integration point:
      BackendManager manages backend lifecycle.
      CircuitExecutor delegates execution to the active backend.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the backend name identifier."""

    @property
    @abstractmethod
    def backend_info(self) -> BackendInfo:
        """Return backend information and capabilities."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is currently available.

        Returns:
            True if the backend can accept circuit executions.
        """

    @abstractmethod
    async def execute_circuit(
        self,
        circuit: Any,
        shots: int = 1024,
        **kwargs: Any,
    ) -> CircuitResult:
        """Execute a quantum circuit and return measurement results.

        Args:
            circuit: The quantum circuit to execute (backend-specific type).
            shots: Number of measurement shots.
            **kwargs: Additional backend-specific execution options.

        Returns:
            CircuitResult with measurement outcomes.
        """

    @abstractmethod
    def transpile(
        self,
        circuit: Any,
        optimization_level: int = 1,
        **kwargs: Any,
    ) -> Any:
        """Compile/transpile a circuit for this backend.

        Args:
            circuit: The quantum circuit to transpile.
            optimization_level: Optimization level (0-3).
            **kwargs: Additional transpiler options.

        Returns:
            Transpiled circuit ready for execution.
        """

    def health(self) -> dict[str, Any]:
        """Return backend health status.

        Returns:
            Dictionary with health information.
        """
        info = self.backend_info
        return {
            "status": info.status.value,
            "backend": self.name,
            "num_qubits": info.num_qubits,
            "available": self.is_available(),
        }

    def supports_operation(self, operation: str) -> bool:
        """Check if the backend supports a specific operation.

        Args:
            operation: The operation name to check.

        Returns:
            True if the operation is supported.
        """
        return True
