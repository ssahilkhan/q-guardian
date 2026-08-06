"""Dependency injection container for Q-Guardian.

Centralizes all dependency providers for FastAPI's DI system.
Future modules register their services here.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger("dependencies.container")


class DependencyContainer:
    """Central dependency injection container.

    Manages singleton and scoped dependencies. Services register
    themselves here and are resolved through FastAPI's dependency
    injection system.
    """

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}

    def register(self, name: str, service: Any) -> None:
        """Register a service instance.

        Args:
            name: The service identifier.
            service: The service instance to register.
        """
        self._services[name] = service
        logger.debug("service_registered", service=name)

    def resolve(self, name: str) -> Any:
        """Resolve a registered service by name.

        Args:
            name: The service identifier.

        Returns:
            The registered service instance.

        Raises:
            KeyError: If the service is not registered.
        """
        if name not in self._services:
            msg = f"Service '{name}' is not registered"
            raise KeyError(msg)
        return self._services[name]

    def has(self, name: str) -> bool:
        """Check if a service is registered.

        Args:
            name: The service identifier.

        Returns:
            True if the service is registered.
        """
        return name in self._services

    def clear(self) -> None:
        """Clear all registered services. Used in testing."""
        self._services.clear()


_container: DependencyContainer | None = None


def get_container() -> DependencyContainer:
    """Get the singleton dependency container.

    Returns:
        The global DependencyContainer instance.
    """
    global _container
    if _container is None:
        _container = DependencyContainer()
    return _container
