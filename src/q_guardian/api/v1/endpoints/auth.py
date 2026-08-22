"""Authentication endpoints for Q-Guardian.

Provides JWT token issuance and API key lifecycle management.
Token issuance is intentionally public; every other route in this
router requires an authenticated principal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from q_guardian.api.dependencies import AuthPrincipal, require_auth
from q_guardian.config.settings import get_settings
from q_guardian.dependencies.container import (
    get_api_key_service,
    get_auth_service,
    get_authorization_service,
    get_jwt_service,
)
from q_guardian.exceptions.base import (
    AuthenticationError,
    NotFoundError,
    SecurityError,
)
from q_guardian.schemas.auth import (
    APIKeyCreateRequest,
    APIKeyCreatedResponse,
    APIKeyDeleteResponse,
    APIKeyInfoResponse,
    TokenRequest,
    TokenResponse,
)
from q_guardian.schemas.base import ResponseSchema

public_router = APIRouter()
router = APIRouter(dependencies=[Depends(require_auth)])


@public_router.post(
    "/token",
    response_model=ResponseSchema[TokenResponse],
    status_code=status.HTTP_200_OK,
)
async def create_token(request: TokenRequest) -> ResponseSchema[TokenResponse]:
    """Exchange credentials for a JWT access token.

    Args:
        request: The credential pair.

    Returns:
        Standard envelope containing the access token.

    Raises:
        AuthenticationError: When the credentials are invalid.
    """
    principal = await get_auth_service().authenticate(request.username, request.password)
    if principal is None:
        raise AuthenticationError("Invalid username or password")
    settings = get_settings().security
    expires_minutes = settings.jwt_expiration_minutes
    token = await get_jwt_service().create_access_token(principal, expires_minutes=expires_minutes)
    return ResponseSchema(
        success=True,
        message="Access token issued",
        data=TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_minutes * 60,
        ),
    )


@router.post(
    "/api-keys",
    response_model=ResponseSchema[APIKeyCreatedResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    request: APIKeyCreateRequest,
    principal: AuthPrincipal = Depends(require_auth),
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
    record, raw_key = await get_api_key_service().generate_api_key(
        name=request.name,
        expires_at=request.expires_at,
        metadata={"created_by": principal.subject},
    )
    return ResponseSchema(
        success=True,
        message="API key created",
        data=APIKeyCreatedResponse(
            key_id=record.key_id,
            name=record.name,
            prefix=record.prefix,
            api_key=raw_key,
            created_at=record.created_at,
            expires_at=record.expires_at,
        ),
    )


@router.get(
    "/api-keys",
    response_model=ResponseSchema[list[APIKeyInfoResponse]],
)
async def list_api_keys(
    principal: AuthPrincipal = Depends(require_auth),
) -> ResponseSchema[list[APIKeyInfoResponse]]:
    """List API keys registered with the service. Requires admin role.

    Args:
        principal: The authenticated caller.

    Returns:
        Standard envelope containing key metadata (no secrets).
    """
    await _require_admin(principal)
    records = await get_api_key_service().list_api_keys()
    return ResponseSchema(
        success=True,
        message="API keys retrieved",
        data=[
            APIKeyInfoResponse(
                key_id=r.key_id,
                name=r.name,
                prefix=r.prefix,
                active=r.active,
                created_at=r.created_at,
                expires_at=r.expires_at,
                last_used_at=r.last_used_at,
            )
            for r in records
        ],
    )


@router.delete(
    "/api-keys/{key_id}",
    response_model=ResponseSchema[APIKeyDeleteResponse],
)
async def revoke_api_key(
    key_id: str,
    principal: AuthPrincipal = Depends(require_auth),
) -> ResponseSchema[APIKeyDeleteResponse]:
    """Deactivate an API key by id. Requires admin role.

    Args:
        key_id: The public key identifier.
        principal: The authenticated caller.

    Returns:
        Standard envelope confirming revocation.

    Raises:
        NotFoundError: When no key matches the identifier.
    """
    await _require_admin(principal)
    deactivated = await get_api_key_service().deactivate_api_key(key_id)
    if not deactivated:
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
    allowed = await get_authorization_service().check_permission(
        principal.subject, resource="api-keys", action="manage"
    )
    if not allowed:
        raise SecurityError(message="Admin role required for this operation")
