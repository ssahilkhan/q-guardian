"""ActionEngine — orchestrates action execution based on policy decisions."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.risk.actions.audit import AuditTrail
from q_guardian.risk.actions.notifier import Notifier
from q_guardian.risk.actions.responders import (
    AlertResponder,
    AuditLogResponder,
    BaseResponder,
    BlockResponder,
    ContinueResponder,
    NotifyAdminResponder,
    WebhookResponder,
)
from q_guardian.risk.enums import PolicyAction
from q_guardian.risk.exceptions import ActionError

if TYPE_CHECKING:
    from q_guardian.risk.data import ActionResult, PolicyDecision, RiskAssessment

logger = structlog.get_logger("risk.action_engine")


class ActionEngine:
    """Orchestrates action execution based on policy decisions.

    Maintains a registry of responders for each action type.
    When a PolicyDecision is received, the engine dispatches to
    the appropriate responder.
    """

    def __init__(self) -> None:
        self._responders: dict[PolicyAction, BaseResponder] = {}
        self._audit_trail = AuditTrail()
        self._notifier = Notifier()
        self._execution_count = 0
        self._action_history: list[ActionResult] = []

        self._register_defaults()

    @property
    def audit_trail(self) -> AuditTrail:
        return self._audit_trail

    @property
    def notifier(self) -> Notifier:
        return self._notifier

    @property
    def execution_count(self) -> int:
        return self._execution_count

    @property
    def action_history(self) -> list[ActionResult]:
        return list(self._action_history)

    def register_responder(self, action: PolicyAction, responder: BaseResponder) -> None:
        """Register a custom responder for an action type.

        Args:
            action: The action type to handle.
            responder: The responder implementation.
        """
        self._responders[action] = responder
        logger.info("responder_registered", action=action.value)

    def execute(
        self,
        decision: PolicyDecision,
        assessment: RiskAssessment | None = None,
        context: dict[str, Any] | None = None,
    ) -> ActionResult:
        """Execute the action prescribed by a policy decision.

        Args:
            decision: The policy decision.
            assessment: Optional risk assessment for audit trail.
            context: Optional execution context.

        Returns:
            ActionResult.
        """
        start = time.monotonic()
        self._execution_count += 1

        if assessment is not None:
            self._audit_trail.record(assessment, decision)

        responder = self._responders.get(decision.action)
        if responder is None:
            responder = self._responders.get(PolicyAction.ALLOW)
        if responder is None:
            raise ActionError(f"No responder registered for action: {decision.action}")

        result = responder.execute(decision, context)

        elapsed = (time.monotonic() - start) * 1000
        result.execution_time_ms = elapsed

        self._action_history.append(result)

        logger.info(
            "action_executed",
            action_type=decision.action.value,
            success=result.success,
            execution_time_ms=elapsed,
        )

        return result

    def execute_batch(
        self,
        decisions: list[PolicyDecision],
        assessments: list[RiskAssessment] | None = None,
    ) -> list[ActionResult]:
        """Execute a batch of decisions."""
        results: list[ActionResult] = []
        for i, decision in enumerate(decisions):
            assessment = assessments[i] if assessments and i < len(assessments) else None
            results.append(self.execute(decision, assessment))
        return results

    def get_responder(self, action: PolicyAction) -> BaseResponder | None:
        """Get the responder for an action type."""
        return self._responders.get(action)

    def list_responders(self) -> dict[str, str]:
        """List registered responders."""
        return {action.value: type(r).__name__ for action, r in self._responders.items()}

    def _register_defaults(self) -> None:
        """Register default responders."""
        self._responders[PolicyAction.ALLOW] = ContinueResponder()
        self._responders[PolicyAction.WARN] = AlertResponder()
        self._responders[PolicyAction.LOG] = AuditLogResponder()
        self._responders[PolicyAction.REVIEW] = AuditLogResponder()
        self._responders[PolicyAction.BLOCK] = BlockResponder()
        self._responders[PolicyAction.QUARANTINE] = BlockResponder()
        self._responders[PolicyAction.ESCALATE] = NotifyAdminResponder()
        self._responders[PolicyAction.TERMINATE_SESSION] = BlockResponder()
        self._responders[PolicyAction.CUSTOM] = WebhookResponder()
