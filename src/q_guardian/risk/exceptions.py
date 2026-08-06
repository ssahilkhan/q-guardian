"""Exceptions for the Risk & Decision Intelligence Engine."""

from __future__ import annotations

from typing import Any

from q_guardian.exceptions.base import ApplicationError


class RiskError(ApplicationError):
    """Base exception for risk module errors."""

    def __init__(
        self,
        message: str = "Risk engine error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="RISK_ERROR",
            status_code=500,
            details=details,
        )


class AssessmentError(RiskError):
    """Error during risk assessment."""

    def __init__(
        self,
        message: str = "Risk assessment failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "ASSESSMENT_ERROR"


class PolicyError(RiskError):
    """Error during policy evaluation."""

    def __init__(
        self,
        message: str = "Policy evaluation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "POLICY_ERROR"


class PolicyNotFoundError(RiskError):
    """Raised when a requested policy does not exist."""

    def __init__(
        self,
        policy_name: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        message = f"Policy not found: {policy_name}" if policy_name else "Policy not found"
        merged = {"policy_name": policy_name, **(details or {})}
        super().__init__(message=message, details=merged)
        self.code = "POLICY_NOT_FOUND"


class ActionError(RiskError):
    """Error during action execution."""

    def __init__(
        self,
        message: str = "Action execution failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "ACTION_ERROR"


class ExplanationError(RiskError):
    """Error during explanation generation."""

    def __init__(
        self,
        message: str = "Explanation generation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "EXPLANATION_ERROR"


class TrustError(RiskError):
    """Error during trust calculation."""

    def __init__(
        self,
        message: str = "Trust calculation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "TRUST_ERROR"


class ConfigurationError(RiskError):
    """Invalid risk module configuration."""

    def __init__(
        self,
        message: str = "Invalid risk configuration",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.code = "RISK_CONFIGURATION_ERROR"
