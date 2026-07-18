"""Exceptions for the Autonomous Response & Recovery Engine."""

from __future__ import annotations


class ResponseEngineError(Exception):
    """Base exception for the response engine."""

    def __init__(self, message: str = "", details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class PlaybookError(ResponseEngineError):
    """Raised when playbook execution fails."""

    pass


class PlaybookValidationError(ResponseEngineError):
    """Raised when a playbook fails validation."""

    pass


class QuarantineError(ResponseEngineError):
    """Raised when a quarantine operation fails."""

    pass


class EvidenceError(ResponseEngineError):
    """Raised when evidence collection fails."""

    pass


class NotificationError(ResponseEngineError):
    """Raised when notification delivery fails."""

    pass


class ApprovalError(ResponseEngineError):
    """Raised when an approval operation fails."""

    pass


class RollbackError(ResponseEngineError):
    """Raised when a rollback operation fails."""

    pass


class RecoveryError(ResponseEngineError):
    """Raised when a recovery operation fails."""

    pass


class IntegrationError(ResponseEngineError):
    """Raised when a SOAR integration call fails."""

    pass


class OrchestrationError(ResponseEngineError):
    """Raised when orchestration fails."""

    pass


class TimeoutError(ResponseEngineError):
    """Raised when an operation times out."""

    pass


class CorrelationError(ResponseEngineError):
    """Raised when correlation tracking fails."""

    pass
