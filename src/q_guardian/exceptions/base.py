"""Base exception classes for Q-Guardian.

Defines the exception hierarchy that all application exceptions inherit from.
Each exception carries structured metadata for logging and API responses.
"""

from __future__ import annotations

from typing import Any


class ApplicationException(Exception):
    """Base exception for all Q-Guardian application errors.

    Attributes:
        message: Human-readable error description.
        code: Machine-readable error code.
        status_code: HTTP status code for API responses.
        details: Additional context about the error.
    """

    def __init__(
        self,
        message: str = "An application error occurred",
        code: str = "APPLICATION_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize exception to dictionary for API responses."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ValidationException(ApplicationException):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str = "Validation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class DatabaseException(ApplicationException):
    """Raised when a database operation fails."""

    def __init__(
        self,
        message: str = "Database operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=503,
            details=details,
        )


class SecurityException(ApplicationException):
    """Raised when a security constraint is violated."""

    def __init__(
        self,
        message: str = "Security violation",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="SECURITY_ERROR",
            status_code=403,
            details=details,
        )


class ExternalServiceException(ApplicationException):
    """Raised when an external service call fails."""

    def __init__(
        self,
        message: str = "External service error",
        service_name: str = "unknown",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = {"service": service_name, **(details or {})}
        super().__init__(
            message=message,
            code="EXTERNAL_SERVICE_ERROR",
            status_code=502,
            details=merged_details,
        )


class NotFoundException(ApplicationException):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        resource: str = "Resource",
        resource_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} with id '{resource_id}' not found"
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404,
            details=details,
        )


class AuthenticationException(ApplicationException):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str = "Authentication required",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=401,
            details=details,
        )


class RateLimitException(ApplicationException):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="RATE_LIMIT_ERROR",
            status_code=429,
            details=details,
        )
