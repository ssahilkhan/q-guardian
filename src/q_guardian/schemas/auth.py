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
    """Issued JWT access token."""

    access_token: str = Field(description="Encoded JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(description="Access token lifetime in seconds")


class APIKeyCreateRequest(BaseSchema):
    """API key creation request."""

    name: str = Field(min_length=1, max_length=100, description="Human-readable key name")
    expires_at: datetime | None = Field(default=None, description="Optional expiration timestamp")


class APIKeyCreatedResponse(BaseSchema):
    """API key creation response. The raw key is returned exactly once."""

    key_id: str = Field(description="Public key identifier")
    name: str = Field(description="Key name")
    prefix: str = Field(description="Key prefix for identification")
    api_key: str = Field(description="Raw API key (shown only once)")
    created_at: datetime = Field(description="Creation timestamp")
    expires_at: datetime | None = Field(default=None, description="Expiration timestamp")


class APIKeyInfoResponse(BaseSchema):
    """API key metadata. Raw key material is never included."""

    key_id: str = Field(description="Public key identifier")
    name: str = Field(description="Key name")
    prefix: str = Field(description="Key prefix for identification")
    active: bool = Field(description="Whether the key is active")
    created_at: datetime = Field(description="Creation timestamp")
    expires_at: datetime | None = Field(default=None, description="Expiration timestamp")
    last_used_at: datetime | None = Field(default=None, description="Last successful use")


class APIKeyDeleteResponse(BaseSchema):
    """API key deactivation response."""

    key_id: str = Field(description="Deactivated key identifier")
    revoked: bool = Field(description="Whether the key was deactivated")
