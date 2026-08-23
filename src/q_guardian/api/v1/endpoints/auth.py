"""Authentication endpoints for Q-Guardian.

Provides JWT token issuance/refresh and API key lifecycle management.
Token issuance is intentionally public; every other route in this
router requires an authenticated principal.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from q_guardian.api.dependencies import AuthPrincipal, require_auth
from q_guardian.config.settings import get_settings
from q_guardian.exceptions.base import AuthenticationError, NotFoundError, SecurityError
from q_guardian.schemas.auth import (
    APIKeyCreatedResponse,
    APIKeyCreateRequest,
    APIKeyDeleteResponse,
    APIKeyInfoResponse,
    RefreshedTokenResponse,
    RefreshTokenRequest,
    TokenRequest,
    TokenResponse,
)
from q_guardian.schemas.base import ResponseSchema
from q_guardian.security.auth import (
    get_api_key_service,
    get_authentication_service,
    get_authorization_service,
)

public_router = APIRouter()
router = APIRouter(dependencies=[Depends(require_auth)])

ADMIN_RESOURCE = "api-keys"
ADMIN_ACTION = "manage"

AuthenticatedPrincipal = Annotated[AuthPrincipal, Depends(require_auth)]

ADMIN_RESOURCE = "api-keys"
ADMIN_ACTION = "manage"


@public_router.post(
    "/token",
    response_model=ResponseSchema[TokenResponse],
    status_code=status.HTTP_200_OK,
)
async def create_token(request: TokenRequest) -> ResponseSchema[TokenResponse]:
    """Exchange credentials for a JWT access/refresh token pair.

    Args:
        request: The credential pair.

    Returns:
        Standard envelope containing the issued tokens.

    Raises:
        AuthenticationError: When the credentials are invalid or no
            users are provisioned.
    """
    result = await get_authentication_service().authenticate(
        request.username, request.password
    )
    if result is None:
        raise AuthenticationError(message="Invalid username or password")
    expires_in = get_settings().security.jwt_expiration_minutes * 60
    return ResponseSchema(
        success=True,
        message="Access token issued",
        data=TokenResponse(
            access_token=result["tokens"]["access"],
            refresh_token=result["tokens"]["refresh"],
            expires_in=expires_in,
        ),
    )


@public_router.post(
    "/token/refresh",
    response_model=ResponseSchema[RefreshedTokenResponse],
    status_code=status.HTTP_200_OK,
)
async def refresh_token(
    request: RefreshTokenRequest,
) -> ResponseSchema[RefreshedTokenResponse]:
    """Exchange a valid refresh token for a new access token.

    Args:
        request: The previously issued refresh token.

    Returns:
        Standard envelope containing the new access token.

    Raises:
        AuthenticationError: When the refresh token is invalid, expired,
            or of the wrong type.
    """
    result = await get_authentication_service().refresh(request.refresh_token)
    if result is None:
        raise AuthenticationError(message="Invalid or expired refresh token")
    expires_in = get_settings().security.jwt_expiration_minutes * 60
    return ResponseSchema(
        success=True,
        message="Access token refreshed",
        data=RefreshedTokenResponse(
            access_token=result["tokens"]["access"],
            expires_in=expires_in,
        ),
    )


@router.post(
    "/api-keys",
    response_model=ResponseSchema[APIKeyCreatedResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    request: APIKeyCreateRequest,
    principal: AuthenticatedPrincipal,
) -> ResponseSchema[APIKeyCreatedResponse]:
    """Create a new API key. Requires admin role.

    Args:
        request: The key creation parameters.
        principal: The authenticated caller.

    Returns:
        Standard envelope containing the key metadata and raw secret.

    Raises:
        SecurityError: When the caller lacks the admin role.
    """
    await _require_admin(principal)
    raw_key, record = get_api_key_service().generate_api_key(
        name=request.name,
        owner=request.owner,
        roles=request.roles,
        ttl_days=request.ttl_days,
    )
    return ResponseSchema(
        success=True,
        message="API key created",
        data=APIKeyCreatedResponse(
            key_id=record.key_id,
            name=record.name,
            key_prefix=record.key_prefix,
            api_key=raw_key,
            owner=record.owner,
            created_at=record.created_at,
            expires_at=record.expires_at,
        ),
    )


@router.get(
    "/api-keys",
    response_model=ResponseSchema[list[APIKeyInfoResponse]],
)
async def list_api_keys(
    principal: AuthenticatedPrincipal,
) -> ResponseSchema[list[APIKeyInfoResponse]]:
    """List API keys registered with the service. Requires admin role.

    Args:
        principal: The authenticated caller.

    Returns:
        Standard envelope containing key metadata (no secrets).
    """
    await _require_admin(principal)
    return ResponseSchema(
        success=True,
        message="API keys retrieved",
        data=[
            APIKeyInfoResponse(
                key_id=entry["key_id"],
                key_prefix=entry["key_prefix"],
                name=entry["name"],
                owner=entry["owner"],
                revoked=entry["revoked"],
                created_at=entry["created_at"],
                expires_at=entry["expires_at"],
            )
            for entry in get_api_key_service().list_api_keys()
        ],
    )


@router.delete(
    "/api-keys/{key_id}",
    response_model=ResponseSchema[APIKeyDeleteResponse],
)
async def revoke_api_key(
    key_id: str,
    principal: AuthenticatedPrincipal,
) -> ResponseSchema[APIKeyDeleteResponse]:
    """Revoke an API key by id. Requires admin role.

    Args:
        key_id: The public key identifier.
        principal: The authenticated caller.

    Returns:
        Standard envelope confirming revocation.

    Raises:
        NotFoundError: When no key matches the identifier.
        SecurityError: When the caller lacks the admin role.
    """
    await _require_admin(principal)
    revoked = get_api_key_service().revoke_api_key(key_id)
    if not revoked:
        raise NotFoundError(resource="API key", resource_id=key_id)
    return ResponseSchema(
        success=True,
        message="API key revoked",
        data=APIKeyDeleteResponse(key_id=key_id, revoked=True),
    )


async def _require_admin(principal: AuthPrincipal) -> None:
    """Assert the caller holds the admin role.

    Args:
        principal: The authenticated caller.

    Raises:
        SecurityError: When the caller is not an admin.
    """
    allowed = await get_authorization_service().check_permission_for_roles(
        principal.roles, resource=ADMIN_RESOURCE, action=ADMIN_ACTION
    )
    if not allowed:
        raise SecurityError(message="Admin role required for this operation")
