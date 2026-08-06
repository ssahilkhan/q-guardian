"""Exceptions for the Observability & Operations Platform."""

from __future__ import annotations

from typing import Any

from q_guardian.exceptions.base import ApplicationError


class ObservabilityError(ApplicationError):
    """Base exception for all observability errors."""

    def __init__(
        self,
        message: str = "Observability error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="OBSERVABILITY_ERROR",
            status_code=500,
            details=details,
        )


class MetricError(ObservabilityError):
    """Raised when a metric operation fails."""

    def __init__(
        self,
        message: str = "Metric operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "METRIC_ERROR"


class TraceError(ObservabilityError):
    """Raised when a tracing operation fails."""

    def __init__(
        self,
        message: str = "Trace operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "TRACE_ERROR"


class HealthError(ObservabilityError):
    """Raised when a health check operation fails."""

    def __init__(
        self,
        message: str = "Health check failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "HEALTH_ERROR"


class AnalyticsError(ObservabilityError):
    """Raised when an analytics operation fails."""

    def __init__(
        self,
        message: str = "Analytics operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "ANALYTICS_ERROR"


class AlertError(ObservabilityError):
    """Raised when an alert operation fails."""

    def __init__(
        self,
        message: str = "Alert operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "ALERT_ERROR"


class ExporterError(ObservabilityError):
    """Raised when an exporter operation fails."""

    def __init__(
        self,
        message: str = "Exporter operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "EXPORTER_ERROR"


class DashboardError(ObservabilityError):
    """Raised when a dashboard operation fails."""

    def __init__(
        self,
        message: str = "Dashboard operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "DASHBOARD_ERROR"


class StorageError(ObservabilityError):
    """Raised when an observability storage operation fails."""

    def __init__(
        self,
        message: str = "Storage operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "OBSERVABILITY_STORAGE_ERROR"


class ConfigurationError(ObservabilityError):
    """Raised when configuration validation fails."""

    def __init__(
        self,
        message: str = "Configuration error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "CONFIGURATION_ERROR"
