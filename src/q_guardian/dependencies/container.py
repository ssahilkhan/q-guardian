"""Dependency injection container for Q-Guardian.

Centralizes all dependency providers for FastAPI's DI system.
Future modules register their services here.
"""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.security.auth import (
    APIKeyService,
    AuthenticationService,
    AuthorizationService,
    JWTService,
    RateLimitService,
)

logger = structlog.get_logger("dependencies.container")

# Canonical service registry keys.
JWT_SERVICE = "jwt_service"
AUTH_SERVICE = "auth_service"
AUTHZ_SERVICE = "authz_service"
API_KEY_SERVICE = "api_key_service"
RATE_LIMIT_SERVICE = "rate_limit_service"
HISTORY_REPOSITORY = "history_repository"
SCAN_SERVICE = "scan_service"


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


def _register_defaults() -> None:
    """Register the default security services on the container."""
    container = get_container()
    if not container.has(JWT_SERVICE):
        container.register(JWT_SERVICE, JWTService())
    if not container.has(AUTH_SERVICE):
        container.register(AUTH_SERVICE, AuthenticationService())
    if not container.has(AUTHZ_SERVICE):
        container.register(AUTHZ_SERVICE, AuthorizationService())
    if not container.has(API_KEY_SERVICE):
        container.register(API_KEY_SERVICE, APIKeyService())
    if not container.has(RATE_LIMIT_SERVICE):
        container.register(RATE_LIMIT_SERVICE, RateLimitService())


def get_jwt_service() -> JWTService:
    """Get the singleton JWT service.

    Returns:
        The global JWTService instance.
    """
    _register_defaults()
    jwt_service: JWTService = get_container().resolve(JWT_SERVICE)
    return jwt_service


def get_auth_service() -> AuthenticationService:
    """Get the singleton authentication service.

    Returns:
        The global AuthenticationService instance.
    """
    _register_defaults()
    auth_service: AuthenticationService = get_container().resolve(AUTH_SERVICE)
    return auth_service


def get_authorization_service() -> AuthorizationService:
    """Get the singleton authorization service.

    Returns:
        The global AuthorizationService instance.
    """
    _register_defaults()
    authz_service: AuthorizationService = get_container().resolve(AUTHZ_SERVICE)
    return authz_service


def get_api_key_service() -> APIKeyService:
    """Get the singleton API key service.

    Returns:
        The global APIKeyService instance.
    """
    _register_defaults()
    api_key_service: APIKeyService = get_container().resolve(API_KEY_SERVICE)
    return api_key_service


def get_rate_limit_service() -> RateLimitService:
    """Get the singleton rate limit service.

    Returns:
        The global RateLimitService instance.
    """
    _register_defaults()
    rate_limit_service: RateLimitService = get_container().resolve(RATE_LIMIT_SERVICE)
    return rate_limit_service
