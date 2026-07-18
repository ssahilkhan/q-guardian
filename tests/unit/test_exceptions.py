"""Unit tests for exception handling framework."""

from __future__ import annotations

import pytest

from q_guardian.exceptions.base import (
    ApplicationException,
    AuthenticationException,
    DatabaseException,
    ExternalServiceException,
    NotFoundException,
    RateLimitException,
    SecurityException,
    ValidationException,
)


class TestApplicationException:
    """Tests for base ApplicationException."""

    def test_default_values(self) -> None:
        """Verify default exception attributes."""
        exc = ApplicationException()
        assert exc.message == "An application error occurred"
        assert exc.code == "APPLICATION_ERROR"
        assert exc.status_code == 500
        assert exc.details == {}

    def test_custom_values(self) -> None:
        """Verify custom exception attributes."""
        exc = ApplicationException(
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
        exc = ApplicationException(message="Test", code="TEST")
        result = exc.to_dict()
        assert "error" in result
        assert result["error"]["code"] == "TEST"

    def test_is_exception_subclass(self) -> None:
        """Verify inheritance from Exception."""
        assert issubclass(ApplicationException, Exception)

    def test_exception_is_catchable(self) -> None:
        """Verify exceptions can be caught."""
        with pytest.raises(ApplicationException):
            raise ApplicationException()


class TestValidationException:
    """Tests for ValidationException."""

    def test_default_values(self) -> None:
        """Verify validation exception defaults."""
        exc = ValidationException()
        assert exc.code == "VALIDATION_ERROR"
        assert exc.status_code == 422

    def test_with_details(self) -> None:
        """Verify validation exception with field errors."""
        details = {"field": "email", "reason": "invalid format"}
        exc = ValidationException(details=details)
        assert exc.details == details


class TestDatabaseException:
    """Tests for DatabaseException."""

    def test_default_values(self) -> None:
        """Verify database exception defaults."""
        exc = DatabaseException()
        assert exc.code == "DATABASE_ERROR"
        assert exc.status_code == 503


class TestSecurityException:
    """Tests for SecurityException."""

    def test_default_values(self) -> None:
        """Verify security exception defaults."""
        exc = SecurityException()
        assert exc.code == "SECURITY_ERROR"
        assert exc.status_code == 403


class TestExternalServiceException:
    """Tests for ExternalServiceException."""

    def test_with_service_name(self) -> None:
        """Verify exception includes service name."""
        exc = ExternalServiceException(service_name="quantum-service")
        assert exc.details["service"] == "quantum-service"
        assert exc.status_code == 502


class TestNotFoundException:
    """Tests for NotFoundException."""

    def test_with_resource(self) -> None:
        """Verify not found message format."""
        exc = NotFoundException(resource="Agent", resource_id="123")
        assert "Agent" in exc.message
        assert "123" in exc.message
        assert exc.status_code == 404


class TestAuthenticationException:
    """Tests for AuthenticationException."""

    def test_default_values(self) -> None:
        """Verify auth exception defaults."""
        exc = AuthenticationException()
        assert exc.code == "AUTHENTICATION_ERROR"
        assert exc.status_code == 401


class TestRateLimitException:
    """Tests for RateLimitException."""

    def test_default_values(self) -> None:
        """Verify rate limit exception defaults."""
        exc = RateLimitException()
        assert exc.code == "RATE_LIMIT_ERROR"
        assert exc.status_code == 429
