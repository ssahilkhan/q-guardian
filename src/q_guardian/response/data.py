"""Data models for the Autonomous Response & Recovery Engine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from q_guardian.response.enums import (
    ApprovalStatus,
    ApprovalType,
    EvidenceType,
    FailureStrategy,
    IntegrationType,
    NotificationChannel,
    NotificationPriority,
    QuarantineStatus,
    QuarantineType,
    RecoveryAction,
    ResponseAction,
    ResponseStatus,
    RollbackTarget,
    StepStatus,
    StepType,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Input models (source-agnostic)
# ---------------------------------------------------------------------------


class PolicyDecision(BaseModel):
    """Source-agnostic policy decision input."""

    decision_id: str = Field(default_factory=_uuid)
    outcome: str = "allow"
    action: str = "allow"
    severity: str = "low"
    risk_score: float = 0.0
    matched_rules: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)


class RiskAssessment(BaseModel):
    """Source-agnostic risk assessment input."""

    assessment_id: str = Field(default_factory=_uuid)
    risk_score: float = 0.0
    risk_level: str = "low"
    threat_level: str = "none"
    confidence: float = 1.0
    severity: str = "low"
    contributing_sources: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)


class ActionPlan(BaseModel):
    """Source-agnostic action plan."""

    plan_id: str = Field(default_factory=_uuid)
    actions: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    timeout_seconds: float = 30.0
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ResponseRequest(BaseModel):
    """A request for the response engine to process."""

    request_id: str = Field(default_factory=_uuid)
    correlation_id: str = Field(default_factory=_uuid)
    policy_decision: PolicyDecision | None = None
    risk_assessment: RiskAssessment | None = None
    action_plan: ActionPlan | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)


class ResponseResult(BaseModel):
    """Result of a response execution."""

    result_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    request_id: str = ""
    action: ResponseAction = ResponseAction.ALLOW
    status: ResponseStatus = ResponseStatus.PENDING
    steps_executed: list[str] = Field(default_factory=list)
    steps_failed: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    notification_ids: list[str] = Field(default_factory=list)
    quarantine_id: str = ""
    rollback_id: str = ""
    reasoning: list[str] = Field(default_factory=list)
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Playbook models
# ---------------------------------------------------------------------------


class PlaybookStep(BaseModel):
    """A single step in a playbook."""

    step_id: str = Field(default_factory=_uuid)
    name: str = ""
    step_type: StepType = StepType.ACTION
    action: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    timeout_seconds: float = 30.0
    retry_count: int = 0
    retry_delay_seconds: float = 1.0
    failure_strategy: FailureStrategy = FailureStrategy.STOP
    depends_on: list[str] = Field(default_factory=list)
    on_success: str = ""
    on_failure: str = ""
    rollback_step: str = ""
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlaybookDefinition(BaseModel):
    """A complete playbook definition."""

    playbook_id: str = Field(default_factory=_uuid)
    name: str
    description: str = ""
    version: str = "1.0.0"
    steps: list[PlaybookStep] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    timeout_seconds: float = 300.0
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class PlaybookExecution(BaseModel):
    """Tracks execution of a playbook."""

    execution_id: str = Field(default_factory=_uuid)
    playbook_id: str = ""
    playbook_name: str = ""
    correlation_id: str = ""
    status: ResponseStatus = ResponseStatus.PENDING
    step_results: list[StepResult] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class StepResult(BaseModel):
    """Result of a single step execution."""

    step_id: str = ""
    step_name: str = ""
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: str = ""
    execution_time_ms: float = 0.0
    retry_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Quarantine models
# ---------------------------------------------------------------------------


class QuarantineRecord(BaseModel):
    """Record of a quarantine action."""

    quarantine_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    target_type: QuarantineType = QuarantineType.AGENT
    target_id: str = ""
    status: QuarantineStatus = QuarantineStatus.ACTIVE
    reason: str = ""
    actions_blocked: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime | None = None
    released_at: datetime | None = None
    released_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Evidence models
# ---------------------------------------------------------------------------


class EvidenceRecord(BaseModel):
    """An immutable evidence artifact."""

    evidence_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    evidence_type: EvidenceType = EvidenceType.CUSTOM
    content: dict[str, Any] = Field(default_factory=dict)
    hash: str = ""
    immutable: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(BaseModel):
    """A single event in an incident timeline."""

    event_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)
    event_type: str = ""
    source: str = ""
    description: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    severity: str = "info"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Timeline(BaseModel):
    """Complete incident timeline."""

    timeline_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    events: list[TimelineEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Notification models
# ---------------------------------------------------------------------------


class NotificationRecord(BaseModel):
    """Record of a sent notification."""

    notification_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    channel: NotificationChannel = NotificationChannel.LOG
    priority: NotificationPriority = NotificationPriority.MEDIUM
    subject: str = ""
    body: str = ""
    recipients: list[str] = Field(default_factory=list)
    status: str = ""
    sent_at: datetime | None = None
    delivered: bool = False
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Approval models
# ---------------------------------------------------------------------------


class ApprovalRequest(BaseModel):
    """An approval request."""

    request_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    approval_type: ApprovalType = ApprovalType.MANUAL
    status: ApprovalStatus = ApprovalStatus.PENDING
    action: str = ""
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    approvers: list[str] = Field(default_factory=list)
    approvals_received: list[str] = Field(default_factory=list)
    required_approvals: int = 1
    timeout_seconds: float = 300.0
    created_at: datetime = Field(default_factory=_utcnow)
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Rollback models
# ---------------------------------------------------------------------------


class Checkpoint(BaseModel):
    """A rollback checkpoint."""

    checkpoint_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    target: RollbackTarget = RollbackTarget.CONFIGURATION
    snapshot: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackResult(BaseModel):
    """Result of a rollback operation."""

    rollback_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    checkpoint_id: str = ""
    target: RollbackTarget = RollbackTarget.CONFIGURATION
    success: bool = False
    restored_state: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    execution_time_ms: float = 0.0
    timestamp: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Recovery models
# ---------------------------------------------------------------------------


class RecoveryPlan(BaseModel):
    """A plan for recovering from an incident."""

    plan_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    actions: list[RecoveryAction] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    timeout_seconds: float = 60.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecoveryResult(BaseModel):
    """Result of a recovery operation."""

    result_id: str = Field(default_factory=_uuid)
    correlation_id: str = ""
    plan_id: str = ""
    actions_attempted: list[str] = Field(default_factory=list)
    actions_succeeded: list[str] = Field(default_factory=list)
    actions_failed: list[str] = Field(default_factory=list)
    success: bool = False
    error: str = ""
    execution_time_ms: float = 0.0
    timestamp: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Integration models
# ---------------------------------------------------------------------------


class IntegrationConfig(BaseModel):
    """Configuration for a SOAR integration."""

    integration_id: str = Field(default_factory=_uuid)
    integration_type: IntegrationType = IntegrationType.CUSTOM
    name: str = ""
    endpoint: str = ""
    api_key: str = ""
    enabled: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationResult(BaseModel):
    """Result of a SOAR integration call."""

    result_id: str = Field(default_factory=_uuid)
    integration_id: str = ""
    integration_type: IntegrationType = IntegrationType.CUSTOM
    status: str = ""
    correlation_id: str = ""
    request_id: str = ""
    success: bool = False
    response: dict[str, Any] = Field(default_factory=dict)
    response_data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)
