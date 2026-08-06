"""BackendManager — manages quantum backend lifecycle and selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from q_guardian.quantum.config import QuantumBackendConfig
from q_guardian.quantum.exceptions import BackendNotAvailableError

if TYPE_CHECKING:
    from q_guardian.quantum.backends.base import QuantumBackend

logger = structlog.get_logger("quantum.backend_manager")


class BackendManager:
    """Manages registration, selection, and health of quantum backends.

    Provides backend discovery, lazy initialization, health monitoring,
    and fallback strategies when preferred backends are unavailable.
    """

    def __init__(self, config: QuantumBackendConfig | None = None) -> None:
        self._config = config or QuantumBackendConfig()
        self._backends: dict[str, QuantumBackend] = {}
        self._active_backend: QuantumBackend | None = None
        self._fallback_order: list[str] = []

    @property
    def active_backend(self) -> QuantumBackend | None:
        """Return the currently active backend."""
        return self._active_backend

    @property
    def backend_count(self) -> int:
        """Return the number of registered backends."""
        return len(self._backends)

    @property
    def config(self) -> QuantumBackendConfig:
        """Return the backend configuration."""
        return self._config

    def register_backend(self, backend: QuantumBackend) -> None:
        """Register a quantum backend.

        Args:
            backend: The backend to register.
        """
        self._backends[backend.name] = backend
        logger.info("backend_registered", backend=backend.name)

    def unregister_backend(self, name: str) -> bool:
        """Unregister a backend by name.

        Args:
            name: Backend name.

        Returns:
            True if the backend was found and removed.
        """
        if name in self._backends:
            del self._backends[name]
            if self._active_backend and self._active_backend.name == name:
                self._active_backend = None
            logger.info("backend_unregistered", backend=name)
            return True
        return False

    def get_backend(self, name: str) -> QuantumBackend | None:
        """Get a backend by name.

        Args:
            name: Backend name.

        Returns:
            The backend instance, or None if not found.
        """
        return self._backends.get(name)

    def list_backends(self) -> list[str]:
        """List all registered backend names.

        Returns:
            List of backend names.
        """
        return list(self._backends.keys())

    def set_active_backend(self, name: str) -> None:
        """Set the active backend by name.

        Args:
            name: Backend name to activate.

        Raises:
            BackendNotAvailableError: If the backend is not registered.
        """
        backend = self._backends.get(name)
        if backend is None:
            msg = f"Backend '{name}' is not registered"
            raise BackendNotAvailableError(msg)
        self._active_backend = backend
        logger.info("active_backend_set", backend=name)

    def get_active_or_fallback(self) -> QuantumBackend:
        """Get the active backend, or find an available fallback.

        Returns:
            An available quantum backend.

        Raises:
            BackendNotAvailableError: If no backends are available.
        """
        if self._active_backend and self._active_backend.is_available():
            return self._active_backend

        for name in self._fallback_order:
            backend = self._backends.get(name)
            if backend and backend.is_available():
                self._active_backend = backend
                logger.info("fallback_backend_selected", backend=name)
                return backend

        for name, backend in self._backends.items():
            if backend.is_available():
                self._active_backend = backend
                logger.info("auto_selected_backend", backend=name)
                return backend

        msg = "No quantum backends are available"
        raise BackendNotAvailableError(msg)

    def set_fallback_order(self, names: list[str]) -> None:
        """Set the fallback order for backend selection.

        Args:
            names: Ordered list of backend names to try as fallback.
        """
        self._fallback_order = list(names)

    def health_check(self) -> dict[str, dict[str, object]]:
        """Check health of all registered backends.

        Returns:
            Dictionary mapping backend names to health status.
        """
        results: dict[str, dict[str, object]] = {}
        for name, backend in self._backends.items():
            results[name] = backend.health()
        return results

    def get_available_backends(self) -> list[str]:
        """Get names of all currently available backends.

        Returns:
            List of available backend names.
        """
        return [name for name, backend in self._backends.items() if backend.is_available()]

    def create_default_backend(self) -> QuantumBackend:
        """Create and register a default simulator backend.

        Returns:
            The newly created backend.
        """
        from q_guardian.quantum.backends.simulator import LocalSimulatorBackend

        backend = LocalSimulatorBackend(num_qubits=self._config.num_qubits)
        self.register_backend(backend)
        if self._active_backend is None:
            self._active_backend = backend
        return backend
