"""Events for the Advanced Policy Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PolicyEvent(BaseModel):
    """Base event for the policy engine."""

    event_id: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyRegistered(PolicyEvent):
    """Emitted when a policy is registered."""

    policy_id: str = ""
    policy_name: str = ""
    version: str = ""


class PolicyUpdated(PolicyEvent):
    """Emitted when a policy is updated."""

    policy_id: str = ""
    policy_name: str = ""
    old_version: str = ""
    new_version: str = ""


class PolicyEvaluated(PolicyEvent):
    """Emitted when a policy is evaluated."""

    policy_id: str = ""
    policy_name: str = ""
    action: str = ""
    matched_rules: list[str] = Field(default_factory=list)
    execution_time_ms: float = 0.0


class PolicyConflictDetected(PolicyEvent):
    """Emitted when a conflict is detected between rules."""

    conflict_type: str = ""
    rule_id_a: str = ""
    rule_id_b: str = ""
    policy_id_a: str = ""
    policy_id_b: str = ""


class PolicySimulated(PolicyEvent):
    """Emitted when a simulation is performed."""

    policy_id: str = ""
    policy_name: str = ""
    action: str = ""
    would_execute: bool = True


class PolicyActivated(PolicyEvent):
    """Emitted when a policy is activated."""

    policy_id: str = ""
    policy_name: str = ""
    version: str = ""


class PolicyDeactivated(PolicyEvent):
    """Emitted when a policy is deactivated."""

    policy_id: str = ""
    policy_name: str = ""
    reason: str = ""
