"""Responders — individual action implementations.

Each responder handles a specific action type and executes the
corresponding response.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import structlog

from q_guardian.risk.data import ActionResult, AuditRecord, Notification, PolicyDecision
from q_guardian.risk.enums import AuditStatus, PolicyAction, Severity

logger = structlog.get_logger("risk.responders")


class BaseResponder(ABC):
    """Abstract base for action responders."""

    @property
    @abstractmethod
    def action_type(self) -> PolicyAction:
        """The action type this responder handles."""

    @abstractmethod
    def execute(
        self, decision: PolicyDecision, context: dict[str, Any] | None = None
    ) -> ActionResult:
        """Execute the action.

        Args:
            decision: The policy decision to act on.
            context: Optional execution context.

        Returns:
            ActionResult with execution details.
        """

    def health(self) -> dict[str, Any]:
        return {"responder": self.action_type.value, "status": "healthy"}


class AuditLogResponder(BaseResponder):
    """Writes an audit log entry."""

    @property
    def action_type(self) -> PolicyAction:
        return PolicyAction.ALLOW

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    @property
    def records(self) -> list[AuditRecord]:
        return list(self._records)

    def execute(
        self, decision: PolicyDecision, context: dict[str, Any] | None = None
    ) -> ActionResult:
        start = time.monotonic()

        record = AuditRecord(
            assessment_id=decision.assessment_id,
            decision_id=decision.decision_id,
            risk_score=decision.risk_score,
            severity=Severity.LOW,
            outcome=decision.outcome,
            action=decision.action,
            reasoning=decision.reasoning,
            policy_name=decision.policy_name,
            status=AuditStatus.ACTIVE,
        )
        self._records.append(record)

        elapsed = (time.monotonic() - start) * 1000
        logger.info("audit_log_written", record_id=record.record_id, outcome=decision.outcome.value)

        return ActionResult(
            decision_id=decision.decision_id,
            action_type="audit_log",
            success=True,
            message=f"Audit record {record.record_id} created",
            details={"record_id": record.record_id},
            execution_time_ms=elapsed,
        )


class AlertResponder(BaseResponder):
    """Sends an alert notification."""

    @property
    def action_type(self) -> PolicyAction:
        return PolicyAction.WARN

    def __init__(self) -> None:
        self._notifications: list[Notification] = []

    @property
    def notifications(self) -> list[Notification]:
        return list(self._notifications)

    def execute(
        self, decision: PolicyDecision, context: dict[str, Any] | None = None
    ) -> ActionResult:
        start = time.monotonic()

        severity = Severity.HIGH if decision.risk_score >= 0.7 else Severity.MEDIUM
        notification = Notification(
            title=f"Security Alert: {decision.outcome.value}",
            message=f"Risk score {decision.risk_score:.2f} triggered {decision.action.value}",
            severity=severity,
            recipient="admin",
            channel="alert",
        )
        self._notifications.append(notification)

        elapsed = (time.monotonic() - start) * 1000
        logger.info("alert_sent", notification_id=notification.notification_id)

        return ActionResult(
            decision_id=decision.decision_id,
            action_type="alert",
            success=True,
            message=f"Alert {notification.notification_id} sent",
            details={"notification_id": notification.notification_id},
            execution_time_ms=elapsed,
        )


class BlockResponder(BaseResponder):
    """Blocks the request."""

    @property
    def action_type(self) -> PolicyAction:
        return PolicyAction.BLOCK

    def execute(
        self, decision: PolicyDecision, context: dict[str, Any] | None = None
    ) -> ActionResult:
        start = time.monotonic()
        elapsed = (time.monotonic() - start) * 1000

        logger.warning(
            "request_blocked", decision_id=decision.decision_id, risk_score=decision.risk_score
        )

        return ActionResult(
            decision_id=decision.decision_id,
            action_type="block",
            success=True,
            message=f"Request blocked: risk_score={decision.risk_score:.4f}",
            details={"blocked": True, "risk_score": decision.risk_score},
            execution_time_ms=elapsed,
        )


class ContinueResponder(BaseResponder):
    """Allows the request to continue."""

    @property
    def action_type(self) -> PolicyAction:
        return PolicyAction.ALLOW

    def execute(
        self, decision: PolicyDecision, context: dict[str, Any] | None = None
    ) -> ActionResult:
        return ActionResult(
            decision_id=decision.decision_id,
            action_type="continue",
            success=True,
            message="Request allowed to continue",
            details={"allowed": True},
        )


class NotifyAdminResponder(BaseResponder):
    """Notifies the administrator."""

    @property
    def action_type(self) -> PolicyAction:
        return PolicyAction.ESCALATE

    def __init__(self) -> None:
        self._notifications: list[Notification] = []

    @property
    def notifications(self) -> list[Notification]:
        return list(self._notifications)

    def execute(
        self, decision: PolicyDecision, context: dict[str, Any] | None = None
    ) -> ActionResult:
        start = time.monotonic()

        notification = Notification(
            title=f"Escalation: {decision.outcome.value}",
            message=f"Risk score {decision.risk_score:.2f} requires administrator review",
            severity=Severity.HIGH,
            recipient="admin",
            channel="escalation",
        )
        self._notifications.append(notification)

        elapsed = (time.monotonic() - start) * 1000
        logger.info("admin_notified", notification_id=notification.notification_id)

        return ActionResult(
            decision_id=decision.decision_id,
            action_type="notify_admin",
            success=True,
            message=f"Administrator notified: {notification.notification_id}",
            details={"notification_id": notification.notification_id},
            execution_time_ms=elapsed,
        )


class WebhookResponder(BaseResponder):
    """Placeholder webhook responder (future interface)."""

    @property
    def action_type(self) -> PolicyAction:
        return PolicyAction.CUSTOM

    def execute(
        self, decision: PolicyDecision, context: dict[str, Any] | None = None
    ) -> ActionResult:
        return ActionResult(
            decision_id=decision.decision_id,
            action_type="webhook",
            success=True,
            message="Webhook interface placeholder",
            details={"placeholder": True},
        )
