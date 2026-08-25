"""Request/response schemas for console authentication endpoints."""

from __future__ import annotations

from pydantic import Field

from q_guardian.schemas.base import BaseSchema


class LoginRequestSchema(BaseSchema):
    """Request body for username/password login."""

    username: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Provisioned username",
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Plaintext password (never logged or persisted)",
    )


class RefreshRequestSchema(BaseSchema):
    """Request body for refreshing an access token."""

    refresh_token: str = Field(
        ...,
        min_length=1,
        max_length=8192,
        description="JWT refresh token previously issued by the login endpoint",
    )


LoginRequestSchema.model_rebuild()
RefreshRequestSchema.model_rebuild()
