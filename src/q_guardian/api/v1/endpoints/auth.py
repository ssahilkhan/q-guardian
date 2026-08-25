"""Authentication endpoints for the Q-Guardian console.

Exposes the existing JWT, authentication, and API key services through
HTTP endpoints so the web console can log in, obtain tokens, and
maintain authenticated sessions.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from q_guardian.security.auth import (
    get_authentication_service,
    get_jwt_service,
)

logger = structlog.get_logger("api.auth")

router = APIRouter()

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Request / response helpers
# ---------------------------------------------------------------------------


class _LoginRequest:
    """Minimal schema for the login body."""

    def __init__(self, username: str = "", password: str = "") -> None:
        self.username = username
        self.password = password


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login")
async def login(request: Request) -> dict[str, Any]:
    """Authenticate a user and return JWT tokens.

    Expects JSON body ``{"username": "...", "password": "..."}``.
    Returns ``{"access": "...", "refresh": "...", "username": "...", "roles": [...]}``
    on success or 401 on failure.
    """
    try:
        body = await request.json()
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid JSON body",
        ) from err

    username = body.get("username", "")
    password = body.get("password", "")

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="username and password are required",
        )

    auth_service = get_authentication_service()
    result = await auth_service.authenticate(username, password)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    logger.info("login_succeeded", username=username)
    return {
        "access": result["tokens"]["access"],
        "refresh": result["tokens"]["refresh"],
        "username": result["username"],
        "roles": result["roles"],
    }


@router.post("/refresh")
async def refresh_token(request: Request) -> dict[str, Any]:
    """Refresh an access token using a valid refresh token.

    Expects JSON body ``{"refresh": "..."}``.
    """
    try:
        body = await request.json()
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid JSON body",
        ) from err

    refresh = body.get("refresh", "")
    if not refresh:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="refresh token is required",
        )

    auth_service = get_authentication_service()
    result = await auth_service.refresh(refresh)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    return {
        "access": result["tokens"]["access"],
        "refresh": result["tokens"]["refresh"],
        "username": result["username"],
        "roles": result["roles"],
    }


@router.get("/me")
async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """Return the current authenticated user from the Bearer token.

    Returns 401 when the token is missing or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwt_service = get_jwt_service()
    try:
        payload = await jwt_service.verify_token(
            credentials.credentials, expected_type="access"
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    return {
        "username": payload.get("sub", ""),
        "roles": payload.get("roles", []),
    }
