"""Authentication and API key API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from q_guardian.schemas.base import BaseSchema


class TokenRequest(BaseSchema):
    """Credential exchange request for JWT issuance."""

    username: str = Field(min_length=1, description="Account username")
    password: str = Field(min_length=1, description="Account password")


class TokenResponse(BaseSchema):
    """Issued JWT token pair."""

    access_token: str = Field(description="Encoded JWT access token")
    refresh_token: str = Field(description="Encoded JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(description="Access token lifetime in seconds")


class RefreshTokenRequest(BaseSchema):
    """Refresh-token exchange request for a new access token."""

    refresh_token: str = Field(min_length=1, description="Previously issued refresh token")


class RefreshedTokenResponse(BaseSchema):
    """Newly issued access token from a refresh flow."""

    access_token: str = Field(description="New encoded JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(description="Access token lifetime in seconds")


class APIKeyCreateRequest(BaseSchema):
    """API key creation request."""

    name: str = Field(min_length=1, max_length=100, description="Human-readable key name")
    owner: str = Field(min_length=1, max_length=100, description="Owner/principal for audit")
    roles: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Roles granted to this key's principal",
    )
    ttl_days: int | None = Field(
        default=None, ge=1, le=3650, description="Optional expiry window in days"
    )


class APIKeyCreatedResponse(BaseSchema):
    """API key creation response. The raw key is returned exactly once."""

    key_id: str = Field(description="Public key identifier")
    name: str = Field(description="Key name")
    key_prefix: str = Field(description="Key prefix for identification")
    api_key: str = Field(description="Raw API key (shown only once)")
    owner: str = Field(description="Key owner/principal")
    created_at: datetime = Field(description="Creation timestamp")
    expires_at: datetime | None = Field(default=None, description="Expiration timestamp")


class APIKeyInfoResponse(BaseSchema):
    """API key metadata. Raw key material and hashes are never included."""

    key_id: str = Field(description="Public key identifier")
    key_prefix: str = Field(description="Key prefix for identification")
    name: str = Field(description="Key name")
    owner: str = Field(description="Key owner/principal")
    revoked: bool = Field(description="Whether the key has been revoked")
    created_at: datetime = Field(description="Creation timestamp")
    expires_at: datetime | None = Field(default=None, description="Expiration timestamp")


class APIKeyDeleteResponse(BaseSchema):
    """API key revocation response."""

    key_id: str = Field(description="Revoked key identifier")
    revoked: bool = Field(description="Whether the key was revoked")
