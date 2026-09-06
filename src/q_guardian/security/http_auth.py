"""HTTP authentication for Q-Guardian API.

FastAPI dependency that authenticates requests using either:
- ``Authorization: Bearer <JWT>`` (access tokens issued by JWTService), or
- the configured API key header (default ``X-API-Key``) validated by
  APIKeyService.

Unauthenticated or invalid requests raise AuthenticationError, which is
converted to a structured 401 response by the global exception handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

# Runtime import is required: FastAPI resolves dependency annotations
# through typing.get_type_hints, which cannot see TYPE_CHECKING-only names.
from starlette.requests import Request  # noqa: TC002

from q_guardian.config.settings import get_settings
from q_guardian.exceptions.base import AuthenticationError
from q_guardian.security.auth import (
    JWTService,
    get_api_key_service,
    get_jwt_service,
    get_token_blocklist,
)

logger = structlog.get_logger("security.http_auth")

BEARER_SCHEME = "bearer"


@dataclass(frozen=True)
class Principal:
    """Authenticated identity attached to a request."""

    auth_type: str
    subject: str
    roles: list[str] = field(default_factory=list)
    jti: str = ""


def _unauthorized(reason: str) -> AuthenticationError:
    """Build a 401 error with a stable machine-readable reason."""
    return AuthenticationError(
        message="Authentication required",
        details={"reason": reason},
    )


async def authenticate_bearer(token: str) -> Principal:
    """Resolve a Bearer JWT to a principal (access tokens only).

    Args:
        token: The raw bearer token string.

    Returns:
        The authenticated principal.

    Raises:
        AuthenticationError: If the token is invalid, expired, or not an
            access token.
    """
    try:
        payload = await get_jwt_service().verify_token(
            token, expected_type=JWTService.ACCESS_TOKEN_TYPE
        )
    except AuthenticationError as exc:
        reason = str(exc.details.get("reason", "token_invalid"))
        raise _unauthorized(reason) from exc
    roles = [str(r) for r in payload.get("roles", [])]
    return Principal(
        auth_type="jwt",
        subject=str(payload.get("sub", "")),
        roles=roles,
        jti=str(payload.get("jti", "")),
    )


def authenticate_api_key(raw_key: str) -> Principal:
    """Resolve an API key to a principal.

    Args:
        raw_key: The raw key material from the API key header.

    Returns:
        The authenticated principal.

    Raises:
        AuthenticationError: If the key is unknown, revoked, or expired.
    """
    record = get_api_key_service().authenticate_api_key(raw_key)
    if record is None:
        raise _unauthorized("invalid_api_key")
    return Principal(auth_type="api_key", subject=record.owner, roles=list(record.roles))


async def get_current_principal(request: Request) -> Principal:
    """FastAPI dependency enforcing authentication on every request.

    Accepts credentials in this order of precedence:

    1. ``Authorization: Bearer <token>`` — verified as a JWT access token.
    2. The configured API key header (``X-API-Key`` by default).

    Args:
        request: The incoming HTTP request.

    Returns:
        The authenticated principal for downstream handlers.

    Raises:
        AuthenticationError: When no valid credentials are presented.
    """
    authorization = request.headers.get("authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != BEARER_SCHEME or not token.strip():
            raise _unauthorized("malformed_authorization_header")
        principal = await authenticate_bearer(token.strip())
        if principal.jti and await get_token_blocklist().is_token_blocked(principal.jti):
            logger.info("access_token_revoked", subject=principal.subject)
            raise _unauthorized("token_revoked")
        return principal

    api_key = request.headers.get(get_settings().security.api_key_header)
    if api_key:
        return authenticate_api_key(api_key.strip())

    logger.info("authentication_missing")
    raise _unauthorized("missing_credentials")
