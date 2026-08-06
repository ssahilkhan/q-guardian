"""Alert escalation management for Q-Guardian Observability."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from q_guardian.observability.enums import AlertSeverity, AlertState
from q_guardian.utils.uuid_utils import generate_uuid

if TYPE_CHECKING:
    from q_guardian.observability.data import Alert

logger = structlog.get_logger(__name__)


class EscalationPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    policy_id: str = Field(default_factory=generate_uuid)
    name: str
    severity: AlertSeverity
    escalation_steps: list[dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True


class EscalationManager:
    def __init__(self, timeout_seconds: int = 600) -> None:
        self._policies: dict[str, EscalationPolicy] = {}
        self._timeout_seconds = timeout_seconds
        self._alert_start_times: dict[str, datetime] = {}
        self._alert_step_indices: dict[str, int] = {}
        logger.info("escalation_manager_initialized", timeout_seconds=timeout_seconds)

    def add_policy(self, policy: EscalationPolicy) -> None:
        self._policies[policy.policy_id] = policy
        logger.info(
            "escalation_policy_added",
            policy_id=policy.policy_id,
            policy_name=policy.name,
        )

    def remove_policy(self, policy_id: str) -> bool:
        if policy_id in self._policies:
            removed = self._policies.pop(policy_id)
            logger.info(
                "escalation_policy_removed",
                policy_id=policy_id,
                policy_name=removed.name,
            )
            return True
        logger.warning("escalation_policy_remove_not_found", policy_id=policy_id)
        return False

    def get_policy(self, policy_id: str) -> EscalationPolicy | None:
        return self._policies.get(policy_id)

    def list_policies(self) -> list[EscalationPolicy]:
        return list(self._policies.values())

    def should_escalate(self, alert: Alert) -> bool:
        if alert.state in (AlertState.RESOLVED, AlertState.SUPPRESSED):
            return False
        if alert.severity == AlertSeverity.INFO:
            return False
        start_time = self._alert_start_times.get(alert.alert_id)
        if start_time is None:
            return False
        elapsed = (datetime.now(UTC) - start_time).total_seconds()
        return elapsed >= self._timeout_seconds

    def get_escalation_step(self, policy: EscalationPolicy, alert: Alert) -> dict[str, Any] | None:
        if not policy.escalation_steps:
            return None
        step_index = self._alert_step_indices.get(alert.alert_id, 0)
        if step_index >= len(policy.escalation_steps):
            return policy.escalation_steps[-1]
        return policy.escalation_steps[step_index]

    def escalate(self, alert: Alert) -> dict[str, Any] | None:
        policy = self._find_matching_policy(alert)
        if policy is None:
            logger.warning(
                "escalation_no_matching_policy",
                alert_id=alert.alert_id,
                severity=alert.severity.value,
            )
            return None
        if alert.alert_id not in self._alert_start_times:
            self._alert_start_times[alert.alert_id] = alert.created_at
        if not self.should_escalate(alert):
            return None
        current_step = self._alert_step_indices.get(alert.alert_id, 0)
        if current_step >= len(policy.escalation_steps):
            return None
        step = policy.escalation_steps[current_step]
        self._alert_step_indices[alert.alert_id] = current_step + 1
        alert.escalate()
        logger.info(
            "alert_escalated",
            alert_id=alert.alert_id,
            step=current_step + 1,
            policy_id=policy.policy_id,
        )
        return step

    def create_default_policy(self, severity: AlertSeverity) -> EscalationPolicy:
        if severity == AlertSeverity.CRITICAL:
            steps = [
                {"delay_seconds": 0, "channels": ["log"], "message": "Critical alert fired"},
                {
                    "delay_seconds": 60,
                    "channels": ["log", "webhook"],
                    "message": "Critical alert escalation",
                },
                {
                    "delay_seconds": 300,
                    "channels": ["log", "webhook"],
                    "message": "Critical alert final escalation",
                },
            ]
        elif severity == AlertSeverity.HIGH:
            steps = [
                {"delay_seconds": 0, "channels": ["log"], "message": "High severity alert fired"},
                {
                    "delay_seconds": 120,
                    "channels": ["log", "webhook"],
                    "message": "High severity alert escalation",
                },
            ]
        elif severity == AlertSeverity.MEDIUM:
            steps = [
                {"delay_seconds": 0, "channels": ["log"], "message": "Medium severity alert fired"},
                {
                    "delay_seconds": 300,
                    "channels": ["log"],
                    "message": "Medium severity alert escalation",
                },
            ]
        else:
            steps = [
                {
                    "delay_seconds": 0,
                    "channels": ["log"],
                    "message": f"{severity.value} severity alert fired",
                },
            ]
        policy = EscalationPolicy(
            name=f"Default {severity.value} escalation",
            severity=severity,
            escalation_steps=steps,
        )
        self.add_policy(policy)
        return policy

    def _find_matching_policy(self, alert: Alert) -> EscalationPolicy | None:
        for policy in self._policies.values():
            if policy.enabled and policy.severity == alert.severity:
                return policy
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeout_seconds": self._timeout_seconds,
            "total_policies": len(self._policies),
            "policies": [p.model_dump(mode="json") for p in self._policies.values()],
            "tracked_alerts": len(self._alert_start_times),
        }
