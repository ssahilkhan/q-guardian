"""Built-in playbook templates."""

from __future__ import annotations

from q_guardian.response.data import PlaybookDefinition, PlaybookStep
from q_guardian.response.enums import FailureStrategy, StepType


def _step(
    name: str,
    action: str,
    step_type: StepType = StepType.ACTION,
    failure: FailureStrategy = FailureStrategy.STOP,
    **kwargs: object,
) -> PlaybookStep:
    return PlaybookStep(
        name=name,
        step_type=step_type,
        action=action,
        parameters={k: v for k, v in kwargs.items() if k != "depends_on"},
        failure_strategy=failure,
        depends_on=kwargs.get("depends_on", []),
    )


def create_block_threat_playbook() -> PlaybookDefinition:
    """Block an identified threat."""
    return PlaybookDefinition(
        name="block-threat",
        description="Block an identified security threat",
        triggers=["threat_detected", "prompt_injection", "jailbreak"],
        steps=[
            _step("collect-evidence", "collect_evidence"),
            _step("quarantine-target", "quarantine", depends_on=["collect-evidence"]),
            _step("block-session", "block", depends_on=["quarantine-target"]),
            _step("notify-admin", "notify", depends_on=["block-session"]),
            _step("generate-report", "generate_report", depends_on=["notify-admin"]),
        ],
        tags=["security", "block", "threat"],
    )


def create_quarantine_playbook() -> PlaybookDefinition:
    """Quarantine a suspicious agent or session."""
    return PlaybookDefinition(
        name="quarantine-agent",
        description="Quarantine a suspicious agent pending investigation",
        triggers=["suspicious_behavior", "anomaly_detected"],
        steps=[
            _step("collect-evidence", "collect_evidence"),
            _step("quarantine-agent", "quarantine", depends_on=["collect-evidence"]),
            _step("request-approval", "request_approval",
                  step_type=StepType.APPROVAL,
                  depends_on=["quarantine-agent"],
                  timeout=600),
            _step("notify-team", "notify", depends_on=["request-approval"]),
        ],
        tags=["security", "quarantine", "investigation"],
    )


def create_escalation_playbook() -> PlaybookDefinition:
    """Escalate a high-severity incident."""
    return PlaybookDefinition(
        name="escalate-incident",
        description="Escalate a high-severity security incident",
        triggers=["high_severity", "critical_risk"],
        steps=[
            _step("collect-evidence", "collect_evidence"),
            _step("escalate", "escalate", depends_on=["collect-evidence"]),
            _step("notify-ops", "notify",
                  parameters={"channel": "pagerduty", "priority": "critical"},
                  depends_on=["escalate"]),
            _step("create-ticket", "create_ticket", depends_on=["notify-ops"]),
        ],
        tags=["security", "escalation", "incident"],
    )


def create_rollback_playbook() -> PlaybookDefinition:
    """Rollback after a failed deployment or policy change."""
    return PlaybookDefinition(
        name="rollback-operation",
        description="Rollback after a failed operation",
        triggers=["deployment_failed", "policy_error"],
        steps=[
            _step("capture-state", "capture_checkpoint"),
            _step("rollback", "rollback", depends_on=["capture-state"]),
            _step("verify-restore", "verify", depends_on=["rollback"]),
            _step("notify", "notify", depends_on=["verify-restore"]),
        ],
        tags=["recovery", "rollback"],
    )


BUILTIN_PLAYBOOKS: dict[str, callable] = {
    "block-threat": create_block_threat_playbook,
    "quarantine-agent": create_quarantine_playbook,
    "escalate-incident": create_escalation_playbook,
    "rollback-operation": create_rollback_playbook,
}
