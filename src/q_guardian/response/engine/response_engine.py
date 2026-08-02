"""Response Engine — consumes PolicyDecision/RiskAssessment and produces ResponseResult."""

from __future__ import annotations

import time
from typing import Any

import structlog

from q_guardian.response.config import ResponseEngineConfig
from q_guardian.response.data import (
    PolicyDecision,
    ResponseRequest,
    ResponseResult,
    RiskAssessment,
)
from q_guardian.response.enums import ResponseAction, ResponseStatus
from q_guardian.response.exceptions import ResponseEngineError

logger = structlog.get_logger(__name__)

# Map policy action strings to ResponseAction
_ACTION_MAP: dict[str, ResponseAction] = {
    "allow": ResponseAction.ALLOW,
    "block": ResponseAction.BLOCK,
    "warn": ResponseAction.WARN,
    "quarantine": ResponseAction.QUARANTINE,
    "terminate": ResponseAction.TERMINATE,
    "escalate": ResponseAction.ESCALATE,
    "monitor": ResponseAction.MONITOR,
    "manual_approval": ResponseAction.MANUAL_APPROVAL,
    "delayed_action": ResponseAction.DELAYED_ACTION,
    "retry": ResponseAction.RETRY,
    "rollback": ResponseAction.ROLLBACK,
    "review": ResponseAction.WARN,
    "log": ResponseAction.LOG_ONLY,
    "log_only": ResponseAction.LOG_ONLY,
    "notify": ResponseAction.NOTIFY,
    "isolate": ResponseAction.ISOLATE,
    "restore": ResponseAction.RESTORE,
}


class ResponseEngine:
    """Source-agnostic response engine.

    Consumes PolicyDecision / RiskAssessment / ActionPlan
    and produces ResponseResult. Knows nothing about rule engines,
    ML, quantum, or fusion.
    """

    def __init__(self, config: ResponseEngineConfig | None = None) -> None:
        self._config = config or ResponseEngineConfig()
        self._executed: dict[str, ResponseResult] = {}
        self._idempotency_cache: dict[str, ResponseResult] = {}

    def process(self, request: ResponseRequest) -> ResponseResult:
        """Process a response request and return a ResponseResult."""
        start = time.monotonic()
        cid = request.correlation_id

        # Idempotency check
        if self._config.enable_idempotency and request.request_id in self._idempotency_cache:
            cached = self._idempotency_cache[request.request_id]
            logger.info("response_idempotent_hit", request_id=request.request_id)
            return cached

        reasoning: list[str] = []
        action = self._resolve_action(request, reasoning)

        result = ResponseResult(
            correlation_id=cid,
            request_id=request.request_id,
            action=action,
            status=ResponseStatus.COMPLETED,
            reasoning=reasoning,
            execution_time_ms=(time.monotonic() - start) * 1000,
        )

        self._executed[cid] = result
        if self._config.enable_idempotency:
            self._idempotency_cache[request.request_id] = result

        logger.info(
            "response_processed",
            correlation_id=cid,
            action=action.value,
            elapsed_ms=round(result.execution_time_ms, 2),
        )
        return result

    def _resolve_action(
        self, request: ResponseRequest, reasoning: list[str]
    ) -> ResponseAction:
        """Determine the response action from inputs."""
        # Priority: action_plan > policy_decision > risk_assessment
        if request.action_plan and request.action_plan.actions:
            primary = request.action_plan.actions[0]
            action = _ACTION_MAP.get(primary, ResponseAction.ALLOW)
            reasoning.append(f"Action from plan: {primary}")
            return action

        if request.policy_decision:
            pd = request.policy_decision
            action = _ACTION_MAP.get(pd.action, ResponseAction.ALLOW)
            reasoning.append(
                f"Action from policy '{pd.outcome}': {pd.action} "
                f"(risk_score={pd.risk_score})"
            )
            return action

        if request.risk_assessment:
            ra = request.risk_assessment
            action = self._risk_to_action(ra, reasoning)
            return action

        reasoning.append("No inputs provided, defaulting to ALLOW")
        return ResponseAction.ALLOW

    @staticmethod
    def _risk_to_action(
        ra: RiskAssessment, reasoning: list[str]
    ) -> ResponseAction:
        """Map a risk assessment to a response action."""
        if ra.risk_level in ("critical",) or ra.threat_level in ("critical",):
            reasoning.append(f"Critical risk/threat -> BLOCK")
            return ResponseAction.BLOCK
        if ra.risk_level in ("severe", "high") or ra.threat_level in ("high",):
            reasoning.append(f"High risk/threat -> ESCALATE")
            return ResponseAction.ESCALATE
        if ra.risk_level in ("moderate",) or ra.threat_level in ("medium",):
            reasoning.append(f"Moderate risk -> WARN")
            return ResponseAction.WARN
        reasoning.append(f"Low risk -> ALLOW")
        return ResponseAction.ALLOW

    def get_result(self, correlation_id: str) -> ResponseResult | None:
        return self._executed.get(correlation_id)

    def get_all_results(self) -> list[ResponseResult]:
        return list(self._executed.values())

    def clear(self) -> None:
        self._executed.clear()
        self._idempotency_cache.clear()

    @property
    def config(self) -> ResponseEngineConfig:
        return self._config
