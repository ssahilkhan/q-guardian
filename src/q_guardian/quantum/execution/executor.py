"""CircuitExecutor — manages quantum circuit execution across backends."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.quantum.backends.manager import BackendManager
from q_guardian.quantum.config import QuantumBackendConfig
from q_guardian.quantum.exceptions import CircuitExecutionError

if TYPE_CHECKING:
    from q_guardian.quantum.backends.base import QuantumBackend
    from q_guardian.quantum.data import CircuitResult

logger = structlog.get_logger("quantum.executor")


class CircuitExecutor:
    """Orchestrates quantum circuit execution across backends.

    Provides a unified interface for executing circuits, with
    automatic backend selection, timeout handling, and result logging.
    """

    def __init__(
        self,
        backend_manager: BackendManager | None = None,
        config: QuantumBackendConfig | None = None,
    ) -> None:
        self._backend_manager = backend_manager or BackendManager(config)
        self._config = config or QuantumBackendConfig()
        self._execution_count = 0
        self._total_execution_time_ms = 0.0

    @property
    def backend_manager(self) -> BackendManager:
        return self._backend_manager

    @property
    def execution_count(self) -> int:
        return self._execution_count

    @property
    def average_execution_time_ms(self) -> float:
        if self._execution_count == 0:
            return 0.0
        return self._total_execution_time_ms / self._execution_count

    async def execute(
        self,
        circuit: Any,
        shots: int | None = None,
        backend_name: str | None = None,
        **kwargs: Any,
    ) -> CircuitResult:
        """Execute a quantum circuit.

        Args:
            circuit: The circuit to execute.
            shots: Number of measurement shots.
            backend_name: Specific backend to use (None = auto-select).
            **kwargs: Additional execution options.

        Returns:
            CircuitResult with measurement outcomes.

        Raises:
            CircuitExecutionError: If execution fails.
        """
        actual_shots = shots or self._config.shots

        if backend_name:
            backend = self._backend_manager.get_backend(backend_name)
            if backend is None:
                msg = f"Backend '{backend_name}' not found"
                raise CircuitExecutionError(msg)
        else:
            backend = self._backend_manager.get_active_or_fallback()

        start = time.monotonic()

        try:
            result = await backend.execute_circuit(circuit, shots=actual_shots, **kwargs)
            elapsed_ms = (time.monotonic() - start) * 1000

            self._execution_count += 1
            self._total_execution_time_ms += elapsed_ms

            logger.info(
                "circuit_executed",
                backend=backend.name,
                shots=actual_shots,
                execution_time_ms=round(elapsed_ms, 3),
            )
            return result
        except CircuitExecutionError:
            raise
        except Exception as e:
            msg = f"Circuit execution failed: {e}"
            logger.error("circuit_execution_error", error=str(e))
            raise CircuitExecutionError(msg) from e

    def get_backend_for_model(
        self,
        num_qubits: int,
        needs_hardware: bool = False,
    ) -> QuantumBackend:
        """Select the best backend for a given model requirement.

        Args:
            num_qubits: Number of qubits needed.
            needs_hardware: Whether real quantum hardware is required.

        Returns:
            The most suitable available backend.
        """
        available = self._backend_manager.get_available_backends()
        if not available:
            msg = "No quantum backends available"
            raise CircuitExecutionError(msg)

        for name in available:
            backend = self._backend_manager.get_backend(name)
            if backend is None:
                continue
            info = backend.backend_info
            if info.num_qubits >= num_qubits:
                if needs_hardware and not info.supports_hardware:
                    continue
                return backend

        return self._backend_manager.get_active_or_fallback()

    def health(self) -> dict[str, Any]:
        """Return executor health status."""
        return {
            "status": "healthy",
            "execution_count": self._execution_count,
            "average_execution_time_ms": round(self.average_execution_time_ms, 3),
            "backends_available": len(self._backend_manager.get_available_backends()),
        }
