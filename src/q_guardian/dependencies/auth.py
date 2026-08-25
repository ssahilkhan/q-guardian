"""FastAPI authentication dependency for Q-Guardian.

Provides ``require_auth()`` which validates Bearer tokens and yields the
decoded payload. Use in endpoint signatures to protect routes::

    @router.get("/protected")
    async def protected(user: dict = Depends(require_auth)):
        ...
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from q_guardian.security.auth import get_jwt_service

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """Validate the Bearer token and return the decoded payload.

    Raises 401 when the token is missing, expired, or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwt_service = get_jwt_service()
    try:
        return await jwt_service.verify_token(
            credentials.credentials, expected_type="access"
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err
