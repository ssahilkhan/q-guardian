"""Unit tests for exception handling framework."""

from __future__ import annotations

import pytest

from q_guardian.exceptions.base import (
    ApplicationError,
    AuthenticationError,
    DatabaseError,
    ExternalServiceError,
    NotFoundError,
    RateLimitError,
    SecurityError,
    ValidationError,
)


class TestApplicationError:
    """Tests for base ApplicationError."""

    def test_default_values(self) -> None:
        """Verify default exception attributes."""
        exc = ApplicationError()
        assert exc.message == "An application error occurred"
        assert exc.code == "APPLICATION_ERROR"
        assert exc.status_code == 500
        assert exc.details == {}

    def test_custom_values(self) -> None:
        """Verify custom exception attributes."""
        exc = ApplicationError(
            message="Custom error",
            code="CUSTOM_ERROR",
            status_code=400,
            details={"key": "value"},
        )
        assert exc.message == "Custom error"
        assert exc.code == "CUSTOM_ERROR"
        assert exc.status_code == 400
        assert exc.details == {"key": "value"}

    def test_to_dict(self) -> None:
        """Verify dictionary serialization."""
        exc = ApplicationError(message="Test", code="TEST")
        result = exc.to_dict()
        assert "error" in result
        assert result["error"]["code"] == "TEST"

    def test_is_exception_subclass(self) -> None:
        """Verify inheritance from Exception."""
        assert issubclass(ApplicationError, Exception)

    def test_exception_is_catchable(self) -> None:
        """Verify exceptions can be caught."""
        with pytest.raises(ApplicationError):
            raise ApplicationError()


class TestValidationError:
    """Tests for ValidationError."""

    def test_default_values(self) -> None:
        """Verify validation exception defaults."""
        exc = ValidationError()
        assert exc.code == "VALIDATION_ERROR"
        assert exc.status_code == 422

    def test_with_details(self) -> None:
        """Verify validation exception with field errors."""
        details = {"field": "email", "reason": "invalid format"}
        exc = ValidationError(details=details)
        assert exc.details == details


class TestDatabaseError:
    """Tests for DatabaseError."""

    def test_default_values(self) -> None:
        """Verify database exception defaults."""
        exc = DatabaseError()
        assert exc.code == "DATABASE_ERROR"
        assert exc.status_code == 503


class TestSecurityError:
    """Tests for SecurityError."""

    def test_default_values(self) -> None:
        """Verify security exception defaults."""
        exc = SecurityError()
        assert exc.code == "SECURITY_ERROR"
        assert exc.status_code == 403


class TestExternalServiceError:
    """Tests for ExternalServiceError."""

    def test_with_service_name(self) -> None:
        """Verify exception includes service name."""
        exc = ExternalServiceError(service_name="quantum-service")
        assert exc.details["service"] == "quantum-service"
        assert exc.status_code == 502


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_with_resource(self) -> None:
        """Verify not found message format."""
        exc = NotFoundError(resource="Agent", resource_id="123")
        assert "Agent" in exc.message
        assert "123" in exc.message
        assert exc.status_code == 404


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_default_values(self) -> None:
        """Verify auth exception defaults."""
        exc = AuthenticationError()
        assert exc.code == "AUTHENTICATION_ERROR"
        assert exc.status_code == 401


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_default_values(self) -> None:
        """Verify rate limit exception defaults."""
        exc = RateLimitError()
        assert exc.code == "RATE_LIMIT_ERROR"
        assert exc.status_code == 429
