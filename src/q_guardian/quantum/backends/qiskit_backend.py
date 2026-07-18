"""Qiskit backend implementation.

All Qiskit imports remain strictly inside this module.
No other package in the framework imports Qiskit directly.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from q_guardian.quantum.backends.base import QuantumBackend
from q_guardian.quantum.config import QuantumBackendConfig
from q_guardian.quantum.enums import BackendStatus, QuantumBackendType
from q_guardian.quantum.data import BackendInfo, CircuitResult
from q_guardian.quantum.exceptions import (
    BackendNotAvailableError,
    CircuitExecutionError,
    TranspilationError,
)

logger = structlog.get_logger("quantum.qiskit_backend")


class QiskitAerBackend(QuantumBackend):
    """Qiskit Aer simulator backend.

    Provides execution via Qiskit's Aer statevector and qasm simulators.
    All Qiskit-specific code is isolated within this class.
    """

    def __init__(self, config: QuantumBackendConfig | None = None) -> None:
        self._config = config or QuantumBackendConfig()
        self._provider: Any = None
        self._backend: Any = None
        self._available = False
        self._execution_count = 0

        self._try_init()

    def _try_init(self) -> None:
        try:
            from qiskit_aer import AerSimulator
            self._backend = AerSimulator()
            self._available = True
            logger.info("qiskit_aer_initialized")
        except ImportError:
            logger.warning("qiskit_aer_not_available")
        except Exception:
            logger.error("qiskit_aer_init_error", exc_info=True)

    @property
    def name(self) -> str:
        return "qiskit-aer"

    @property
    def backend_info(self) -> BackendInfo:
        num_qubits = 0
        if self._backend is not None and hasattr(self._backend, "num_qubits"):
            num_qubits = self._backend.num_qubits or 0

        return BackendInfo(
            name=self.name,
            backend_type=QuantumBackendType.QISKIT_AER,
            status=BackendStatus.HEALTHY if self._available else BackendStatus.UNAVAILABLE,
            num_qubits=num_qubits or self._config.num_qubits,
            max_shots=65536,
            supports_simulation=True,
            supports_hardware=False,
            capabilities=["statevector", "density_matrix", "matrix_product_state"],
        )

    def is_available(self) -> bool:
        return self._available

    async def execute_circuit(
        self,
        circuit: Any,
        shots: int = 1024,
        **kwargs: Any,
    ) -> CircuitResult:
        if not self._available:
            msg = "Qiskit Aer backend is not available"
            raise BackendNotAvailableError(msg)

        start = time.monotonic()

        try:
            from qiskit import transpile as qiskit_transpile

            transpiled = qiskit_transpile(
                circuit,
                self._backend,
                optimization_level=self._config.optimization_level,
            )
            job = self._backend.run(transpiled, shots=shots)
            result = job.result()
            counts = result.get_counts(transpiled)

            elapsed_ms = (time.monotonic() - start) * 1000
            self._execution_count += 1

            total = sum(counts.values()) if counts else 0
            probabilities = {k: v / total for k, v in counts.items()} if total > 0 else {}

            return CircuitResult(
                counts=counts or {},
                probabilities=probabilities,
                backend=self.name,
                shots=shots,
                execution_time_ms=round(elapsed_ms, 3),
                raw_result=result,
                metadata={"job_id": getattr(job, "job_id", lambda: "unknown")()},
            )
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            msg = f"Circuit execution failed: {e}"
            logger.error("circuit_execution_error", error=str(e), execution_time_ms=elapsed_ms)
            raise CircuitExecutionError(msg) from e

    def transpile(self, circuit: Any, optimization_level: int = 1, **kwargs: Any) -> Any:
        if not self._available:
            msg = "Qiskit Aer backend is not available"
            raise BackendNotAvailableError(msg)

        try:
            from qiskit import transpile as qiskit_transpile

            return qiskit_transpile(
                circuit,
                self._backend,
                optimization_level=optimization_level,
            )
        except Exception as e:
            msg = f"Transpilation failed: {e}"
            raise TranspilationError(msg) from e

    def health(self) -> dict[str, Any]:
        base = super().health()
        base["execution_count"] = self._execution_count
        return base


class QiskitRuntimeBackend(QuantumBackend):
    """Qiskit Runtime / IBM Quantum backend.

    Connects to IBM Quantum services for real hardware execution.
    Requires valid IBM Quantum credentials.
    """

    def __init__(self, config: QuantumBackendConfig | None = None, token: str | None = None) -> None:
        self._config = config or QuantumBackendConfig()
        self._token = token or self._config.provider_options.get("token")
        self._provider: Any = None
        self._backend: Any = None
        self._available = False
        self._execution_count = 0

        self._try_init()

    def _try_init(self) -> None:
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService

            kwargs: dict[str, Any] = {}
            if self._token:
                kwargs["token"] = self._token
            instance = self._config.provider_options.get("instance")
            if instance:
                kwargs["instance"] = instance

            self._provider = QiskitRuntimeService(**kwargs)
            backend_name = self._config.provider_options.get("backend", "ibm_brisbane")
            self._backend = self._provider.backend(backend_name)
            self._available = True
            logger.info("qiskit_runtime_initialized", backend=backend_name)
        except ImportError:
            logger.warning("qiskit_ibm_runtime_not_available")
        except Exception:
            logger.error("qiskit_runtime_init_error", exc_info=True)

    @property
    def name(self) -> str:
        return "qiskit-runtime"

    @property
    def backend_info(self) -> BackendInfo:
        num_qubits = 0
        if self._backend is not None and hasattr(self._backend, "num_qubits"):
            num_qubits = self._backend.num_qubits or 0

        return BackendInfo(
            name=self.name,
            backend_type=QuantumBackendType.QISKIT_RUNTIME,
            status=BackendStatus.HEALTHY if self._available else BackendStatus.UNAVAILABLE,
            num_qubits=num_qubits,
            max_shots=40000,
            supports_simulation=False,
            supports_hardware=True,
            capabilities=["dynamic_circuits", "error_mitigation", "runtime_jobs"],
        )

    def is_available(self) -> bool:
        return self._available

    async def execute_circuit(
        self,
        circuit: Any,
        shots: int = 1024,
        **kwargs: Any,
    ) -> CircuitResult:
        if not self._available:
            msg = "Qiskit Runtime backend is not available"
            raise BackendNotAvailableError(msg)

        start = time.monotonic()

        try:
            from qiskit import transpile as qiskit_transpile

            transpiled = qiskit_transpile(
                circuit,
                self._backend,
                optimization_level=self._config.optimization_level,
            )
            job = self._backend.run(transpiled, shots=shots)
            result = job.result()
            counts = result.get_counts(transpiled)

            elapsed_ms = (time.monotonic() - start) * 1000
            self._execution_count += 1

            total = sum(counts.values()) if counts else 0
            probabilities = {k: v / total for k, v in counts.items()} if total > 0 else {}

            return CircuitResult(
                counts=counts or {},
                probabilities=probabilities,
                backend=self.name,
                shots=shots,
                execution_time_ms=round(elapsed_ms, 3),
                raw_result=result,
                metadata={"job_id": getattr(job, "job_id", lambda: "unknown")()},
            )
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            msg = f"Runtime execution failed: {e}"
            logger.error("runtime_execution_error", error=str(e))
            raise CircuitExecutionError(msg) from e

    def transpile(self, circuit: Any, optimization_level: int = 1, **kwargs: Any) -> Any:
        if not self._available:
            msg = "Qiskit Runtime backend is not available"
            raise BackendNotAvailableError(msg)

        try:
            from qiskit import transpile as qiskit_transpile

            return qiskit_transpile(
                circuit,
                self._backend,
                optimization_level=optimization_level,
            )
        except Exception as e:
            msg = f"Transpilation failed: {e}"
            raise TranspilationError(msg) from e

    def health(self) -> dict[str, Any]:
        base = super().health()
        base["execution_count"] = self._execution_count
        if self._backend and hasattr(self._backend, "status"):
            try:
                status = self._backend.status()
                base["hardware_status"] = str(status)
            except Exception:
                base["hardware_status"] = "unknown"
        return base
