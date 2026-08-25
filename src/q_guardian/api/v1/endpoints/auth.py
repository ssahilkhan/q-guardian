"""Console authentication endpoints.

Exposes the *existing* :class:`~q_guardian.security.auth.AuthenticationService`
(username/password against the ``AUTH_USERS`` environment store) and
:class:`~q_guardian.security.auth.JWTService` refresh flow over HTTP so the
web console can obtain a JWT access token. No new security logic lives here —
credential verification, hashing and token signing/verification remain in the
security module.

These routes are intentionally registered outside the authenticated v1
router: login/refresh are the bootstrap endpoints used to *obtain*
credentials.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from q_guardian.schemas.auth import LoginRequestSchema, RefreshRequestSchema

if TYPE_CHECKING:
    from q_guardian.schemas.auth import LoginRequestSchema, RefreshRequestSchema

from q_guardian.config.settings import get_settings
from q_guardian.exceptions.base import AuthenticationError
from q_guardian.schemas.base import ResponseSchema
from q_guardian.security.auth import (
    get_authentication_service,
    get_rate_limit_service,
)

logger = structlog.get_logger("api.auth")

router = APIRouter()

FORWARDED_FOR_HEADER = "X-Forwarded-For"


def _client_identifier(request: Request) -> str:
    """Derive rate-limit key from request (IP only, respecting XFF trust setting)."""
    settings = get_settings().rate_limit
    if settings.trust_x_forwarded_for:
        forwarded = request.headers.get(FORWARDED_FOR_HEADER)
        if forwarded:
            first_hop = forwarded.split(",")[0].strip()
            if first_hop:
                return first_hop
    return request.client.host if request.client else "unknown"


_LOGIN_RATE_LIMIT = 5
_LOGIN_WINDOW_SECONDS = 900  # 15 minutes


async def _check_login_rate_limit(request: Request, username: str) -> tuple[bool, int]:
    """Check login rate limit for IP+username combo.

    Returns:
        (allowed, retry_after_seconds)
    """
    identifier = f"{_client_identifier(request)}:{username}"
    svc = get_rate_limit_service()
    allowed = await svc.check_rate_limit(
        identifier, limit=_LOGIN_RATE_LIMIT, window=_LOGIN_WINDOW_SECONDS
    )
    if not allowed:
        retry_after = svc.retry_after(identifier, window=_LOGIN_WINDOW_SECONDS)
        return False, retry_after
    return True, 0


@router.post("/login", response_model=ResponseSchema[dict[str, Any]])
async def login(request: Request, body: LoginRequestSchema) -> ResponseSchema[dict[str, Any]] | JSONResponse:
    """Authenticate a provisioned user and issue a token pair.

    Args:
        request: Incoming request (correlation ID hook).
        body: Username and plaintext password.

    Returns:
        The authenticated identity with ``tokens.access`` /
        ``tokens.refresh`` JWTs wrapped in the standard envelope.

    Raises:
        AuthenticationError: 401 when credentials are invalid or no users
            are provisioned (``AUTH_USERS`` unset).
    """
    username = body.username.strip()
    allowed, retry_after = await _check_login_rate_limit(request, username)
    if not allowed:
        logger.warning(
            "login_rate_limit_exceeded",
            username=username,
            identifier=_client_identifier(request),
            retry_after=retry_after,
        )
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMIT_ERROR",
                    "message": "Too many login attempts",
                    "details": {"retry_after_seconds": retry_after},
                }
            },
            headers={"Retry-After": str(retry_after)},
        )

    result = await get_authentication_service().authenticate(username, body.password)
    if result is None:
        # Identical response for unknown user / wrong password / no users
        # configured, so the endpoint never leaks which accounts exist.
        raise AuthenticationError(
            message="Invalid username or password",
            details={"reason": "invalid_credentials"},
        )
    logger.info("console_login_succeeded", username=result["username"])
    return ResponseSchema(
        success=True,
        message="Login succeeded",
        data=result,
    )


@router.post("/refresh", response_model=ResponseSchema[dict[str, Any]])
async def refresh(request: Request, body: RefreshRequestSchema) -> ResponseSchema[dict[str, Any]]:
    """Issue a new access token from a valid refresh token.

    Args:
        request: Incoming request (correlation ID hook).
        body: The refresh token previously issued by :endpoint:`/login`.

    Returns:
        A fresh token pair wrapped in the standard envelope.

    Raises:
        AuthenticationError: 401 when the refresh token is invalid or
            expired.
    """
    result = await get_authentication_service().refresh(body.refresh_token.strip())
    if result is None:
        raise AuthenticationError(
            message="Refresh token is invalid or expired",
            details={"reason": "invalid_refresh_token"},
        )
    return ResponseSchema(
        success=True,
        message="Token refreshed successfully",
        data=result,
    )
