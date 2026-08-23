"""FastAPI authentication dependencies for Q-Guardian.

Resolves the caller's identity from either a Bearer JWT or an API key
and enforces authentication on protected endpoints.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import Request  # noqa: TC002 - resolved by FastAPI DI at runtime
from pydantic import BaseModel, Field

from q_guardian.config.settings import get_settings
from q_guardian.exceptions.base import AuthenticationError
from q_guardian.security.auth import (
    JWTService,
    get_api_key_service,
    get_jwt_service,
)

logger = structlog.get_logger("api.dependencies")

BEARER_PREFIX = "bearer "


class AuthPrincipal(BaseModel):
    """Authenticated caller identity attached to a request."""

    subject: str = Field(description="Principal identifier (user or key id)")
    auth_method: str = Field(description="Authentication method used: jwt or api_key")
    roles: list[str] = Field(default_factory=list, description="Granted roles")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional claims")


async def require_auth(request: Request) -> AuthPrincipal:
    """Require a valid Bearer JWT or API key on the request.

    Resolution order:
    1. ``Authorization: Bearer <jwt>`` header.
    2. Configured API key header (default ``X-API-Key``).

    Args:
        request: The incoming HTTP request.

    Returns:
        The authenticated principal.

    Raises:
        AuthenticationError: If credentials are missing, invalid, or
            the API key is revoked/expired.
    """
    principal = await _resolve_bearer(request)
    if principal is None:
        principal = await _resolve_api_key(request)
    if principal is None:
        raise AuthenticationError(message="Missing authentication credentials")
    return principal


async def _resolve_bearer(request: Request) -> AuthPrincipal | None:
    """Authenticate via the Authorization Bearer header.

    Args:
        request: The incoming HTTP request.

    Returns:
        Principal when a Bearer token is present and valid; None when
        no Bearer header is supplied.

    Raises:
        AuthenticationError: When a Bearer token is present but invalid.
    """
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.lower().startswith(BEARER_PREFIX):
        return None
    token = authorization[len(BEARER_PREFIX) :].strip()
    if not token:
        raise AuthenticationError(message="Empty bearer token")
    claims = await get_jwt_service().verify_token(
        token, expected_type=JWTService.ACCESS_TOKEN_TYPE
    )
    return AuthPrincipal(
        subject=str(claims.get("sub", "")),
        auth_method="jwt",
        roles=[str(r) for r in claims.get("roles", [])],
        details={"jti": claims.get("jti", "")},
    )


async def _resolve_api_key(request: Request) -> AuthPrincipal | None:
    """Authenticate via the configured API key header.

    Args:
        request: The incoming HTTP request.

    Returns:
        Principal when the header is present and the key is active;
        None when no API key header is supplied.

    Raises:
        AuthenticationError: When the API key is invalid or inactive.
    """
    header_name = get_settings().security.api_key_header
    raw_key = request.headers.get(header_name)
    if not raw_key:
        return None
    record = get_api_key_service().authenticate_api_key(raw_key)
    if record is None:
        logger.warning("api_key_rejected", prefix=raw_key[:8])
        raise AuthenticationError(message="Invalid or inactive API key")
    return AuthPrincipal(
        subject=record.key_id,
        auth_method="api_key",
        roles=list(record.roles),
        details={"key_name": record.name},
    )
