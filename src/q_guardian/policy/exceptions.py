"""Exceptions for the Advanced Policy Engine."""

from __future__ import annotations

from typing import Any


class PolicyEngineError(Exception):
    """Base exception for the policy engine."""

    def __init__(self, message: str = "", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


class ConditionParseError(PolicyEngineError):
    """Raised when a condition expression cannot be parsed."""

    pass


class PolicyConflictError(PolicyEngineError):
    """Raised when an unresolvable conflict is detected."""

    pass


class PolicyVersionError(PolicyEngineError):
    """Raised when a version operation fails."""

    pass


class SimulationError(PolicyEngineError):
    """Raised when a simulation fails."""

    pass


class DSLAdapterError(PolicyEngineError):
    """Raised when a DSL adapter fails to convert."""

    pass


class RBACError(PolicyEngineError):
    """Raised when an RBAC check fails."""

    pass


class PolicyNotFoundError(PolicyEngineError):
    """Raised when a policy is not found."""

    pass


class PolicyCompositionError(PolicyEngineError):
    """Raised when policy composition fails."""

    pass
