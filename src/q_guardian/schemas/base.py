"""Base schemas for API request/response models.

Provides common schema patterns with validation and serialization.
"""

from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.utils.datetime_utils import get_utc_now

T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=True,
        from_attributes=True,
    )


class ResponseSchema[T](BaseSchema):
    """Standard API response envelope.

    All API responses should follow this structure for consistency.
    """

    success: bool = Field(default=True, description="Whether the request succeeded")
    message: str = Field(default="Success", description="Response message")
    data: T | None = Field(default=None, description="Response payload")
    timestamp: datetime = Field(default_factory=get_utc_now, description="Response timestamp")
    correlation_id: str | None = Field(default=None, description="Request correlation ID")


class PaginatedResponseSchema[T](BaseSchema):
    """Paginated list response schema."""

    success: bool = Field(default=True)
    message: str = Field(default="Success")
    data: list[T] = Field(default_factory=list)
    total: int = Field(default=0, description="Total number of items")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=10, description="Items per page")
    total_pages: int = Field(default=0, description="Total number of pages")
    timestamp: datetime = Field(default_factory=get_utc_now)


class HealthResponseSchema(BaseSchema):
    """Health check response schema."""

    status: str = Field(description="Overall health status")
    application: str = Field(description="Application name")
    version: str = Field(description="Application version")
    environment: str = Field(description="Current environment")
    timestamp: datetime = Field(description="Check timestamp")
    database: dict[str, Any] | None = Field(default=None, description="Database health status")


class ErrorResponseSchema(BaseSchema):
    """Error response schema."""

    success: bool = Field(default=False)
    error: dict[str, Any] = Field(description="Error details")
    timestamp: datetime = Field(default_factory=get_utc_now)
    correlation_id: str | None = Field(default=None)


class VersionResponseSchema(BaseSchema):
    """Version endpoint response schema."""

    application: str = Field(description="Application name")
    version: str = Field(description="Application version")
    environment: str = Field(description="Current environment")
    python_version: str = Field(description="Python version")
    timestamp: datetime = Field(default_factory=get_utc_now)
