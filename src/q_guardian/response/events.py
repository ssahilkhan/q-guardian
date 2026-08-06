"""Events for the Autonomous Response & Recovery Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ResponseEvent(BaseModel):
    """Base event for the response engine."""

    event_id: str = ""
    correlation_id: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResponseInitiated(ResponseEvent):
    action: str = ""
    request_id: str = ""


class ResponseCompleted(ResponseEvent):
    action: str = ""
    status: str = ""
    execution_time_ms: float = 0.0


class ResponseFailed(ResponseEvent):
    action: str = ""
    error: str = ""


class PlaybookStarted(ResponseEvent):
    playbook_id: str = ""
    playbook_name: str = ""


class PlaybookCompleted(ResponseEvent):
    playbook_id: str = ""
    steps_executed: int = 0
    steps_failed: int = 0


class PlaybookStepCompleted(ResponseEvent):
    step_id: str = ""
    step_name: str = ""
    status: str = ""


class PlaybookStepFailed(ResponseEvent):
    step_id: str = ""
    step_name: str = ""
    error: str = ""


class QuarantineActivated(ResponseEvent):
    quarantine_id: str = ""
    target_type: str = ""
    target_id: str = ""


class QuarantineReleased(ResponseEvent):
    quarantine_id: str = ""
    released_by: str = ""


class EvidenceCollected(ResponseEvent):
    evidence_id: str = ""
    evidence_type: str = ""


class NotificationSent(ResponseEvent):
    notification_id: str = ""
    channel: str = ""
    priority: str = ""


class ApprovalRequested(ResponseEvent):
    approval_id: str = ""
    action: str = ""
    approvers: list[str] = Field(default_factory=list)


class ApprovalResolved(ResponseEvent):
    approval_id: str = ""
    status: str = ""
    resolved_by: str = ""


class RollbackInitiated(ResponseEvent):
    rollback_id: str = ""
    target: str = ""


class RollbackCompleted(ResponseEvent):
    rollback_id: str = ""
    success: bool = False


class RecoveryInitiated(ResponseEvent):
    plan_id: str = ""
    actions: list[str] = Field(default_factory=list)


class RecoveryCompleted(ResponseEvent):
    plan_id: str = ""
    success: bool = False
    actions_succeeded: int = 0
    actions_failed: int = 0


class IntegrationCalled(ResponseEvent):
    integration_type: str = ""
    integration_id: str = ""


class IntegrationCompleted(ResponseEvent):
    integration_type: str = ""
    success: bool = False
