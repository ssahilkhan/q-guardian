"""QuantumAnalysisPlugin — orchestrates quantum threat analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.plugins.base import Plugin
from q_guardian.quantum.backends.manager import BackendManager
from q_guardian.quantum.config import QuantumConfig
from q_guardian.quantum.execution.executor import CircuitExecutor

if TYPE_CHECKING:
    from q_guardian.framework.context import FrameworkContext
    from q_guardian.quantum.models.base import BaseQuantumModel

logger = structlog.get_logger("quantum.plugin")


class QuantumAnalysisPlugin(Plugin):
    """Quantum analysis plugin that provides quantum-enhanced threat detection.

    Integrates with the framework as a plugin, providing:
    - Quantum backend management
    - Quantum model registration and execution
    - Circuit execution abstraction
    - Integration with ThreatAnalysisPlugin

    This plugin does NOT replace classical ML — it complements it.
    """

    def __init__(self, config: QuantumConfig | None = None) -> None:
        self._config = config or QuantumConfig()
        self._backend_manager = BackendManager(self._config.backend)
        self._executor = CircuitExecutor(self._backend_manager, self._config.backend)
        self._models: dict[str, BaseQuantumModel] = {}
        self._context: FrameworkContext | None = None
        self._scan_count: int = 0

    @property
    def name(self) -> str:
        return "quantum-analysis"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def author(self) -> str:
        return "Q-Guardian"

    @property
    def description(self) -> str:
        return "Quantum-enhanced threat analysis for prompt security"

    @property
    def interfaces(self) -> list[str]:
        return ["quantum_analyzer"]

    @property
    def backend_manager(self) -> BackendManager:
        return self._backend_manager

    @property
    def executor(self) -> CircuitExecutor:
        return self._executor

    @property
    def config(self) -> QuantumConfig:
        return self._config

    def register_model(self, model: BaseQuantumModel) -> None:
        """Register a quantum model.

        Args:
            model: The quantum model to register.
        """
        self._models[model.name] = model
        logger.info("quantum_model_registered", model=model.name)

    def unregister_model(self, name: str) -> bool:
        """Unregister a quantum model by name.

        Args:
            name: Model name.

        Returns:
            True if the model was found and removed.
        """
        if name in self._models:
            del self._models[name]
            logger.info("quantum_model_unregistered", model=name)
            return True
        return False

    def get_model(self, name: str) -> BaseQuantumModel | None:
        """Get a registered quantum model by name.

        Args:
            name: Model name.

        Returns:
            The model instance, or None if not found.
        """
        return self._models.get(name)

    def list_models(self) -> list[str]:
        """List all registered quantum model names.

        Returns:
            List of model names.
        """
        return list(self._models.keys())

    async def initialize(self, context: FrameworkContext) -> None:
        """Initialize the plugin with framework context."""
        self._context = context
        if self._config.enabled and self._backend_manager.backend_count == 0:
            self._backend_manager.create_default_backend()
        logger.info(
            "quantum_plugin_initialized",
            enabled=self._config.enabled,
            backends=self._backend_manager.backend_count,
        )

    async def start(self) -> None:
        """Start the plugin."""
        logger.info(
            "quantum_plugin_started",
            models=len(self._models),
            backends=self._backend_manager.list_backends(),
        )

    async def stop(self) -> None:
        """Stop the plugin."""
        logger.info(
            "quantum_plugin_stopped",
            scans=self._scan_count,
            models=len(self._models),
        )

    def health(self) -> dict[str, Any]:
        """Return plugin health status."""
        return {
            "status": "healthy",
            "plugin": self.name,
            "enabled": self._config.enabled,
            "models": len(self._models),
            "backends": self._backend_manager.list_backends(),
            "executor": self._executor.health(),
        }

    def configuration(self) -> dict[str, Any]:
        """Return plugin configuration."""
        return self._config.model_dump()
