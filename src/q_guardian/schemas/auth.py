"""Request/response schemas for console authentication endpoints."""

from __future__ import annotations

import re

from pydantic import Field, field_validator

from q_guardian.schemas.base import BaseSchema

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


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


class RegisterRequestSchema(BaseSchema):
    """Request body for self-service account registration.

    Registration always creates a standard ``analyst`` account; usernames
    and passwords are validated here before they reach the service.
    """

    username: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Username (letters, digits, _ . -)",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="Plaintext password (min 8 characters, never stored)",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        """Reject usernames outside the safe character set."""
        if not _USERNAME_PATTERN.fullmatch(value):
            msg = (
                "Usernames may contain letters, digits, underscores, "
                "hyphens and periods (3-64 characters)"
            )
            raise ValueError(msg)
        return value


class RefreshRequestSchema(BaseSchema):
    """Request body for refreshing an access token."""

    refresh_token: str = Field(
        ...,
        min_length=1,
        max_length=8192,
        description="JWT refresh token previously issued by the login endpoint",
    )


class LogoutRequestSchema(BaseSchema):
    """Request body for revoking the current session.

    The access token is taken from the ``Authorization`` header; the
    optional ``refresh_token`` field revokes the refresh token too.
    """

    refresh_token: str | None = Field(
        default=None,
        max_length=8192,
        description="Optional refresh token to revoke alongside the access token",
    )


LoginRequestSchema.model_rebuild()
RegisterRequestSchema.model_rebuild()
RefreshRequestSchema.model_rebuild()
LogoutRequestSchema.model_rebuild()
