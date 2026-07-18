"""Recovery Engine — resume sessions, restore runtime/plugins/memory, retry requests."""

from __future__ import annotations

import time
from typing import Any, Callable

import structlog

from q_guardian.response.data import RecoveryPlan, RecoveryResult
from q_guardian.response.enums import RecoveryAction
from q_guardian.response.exceptions import RecoveryError

logger = structlog.get_logger(__name__)

RecoveryHandler = Callable[[RecoveryAction, dict[str, Any]], Any]


class RecoveryEngine:
    """Executes recovery plans after security incidents."""

    def __init__(self, max_attempts: int = 3) -> None:
        self._handlers: dict[str, RecoveryHandler] = {}
        self._results: dict[str, RecoveryResult] = {}
        self._max_attempts = max_attempts
        self._init_default_handlers()

    def _init_default_handlers(self) -> None:
        """Register default recovery action handlers."""
        self._handlers[RecoveryAction.RESUME_SESSION.value] = self._handle_resume_session
        self._handlers[RecoveryAction.RESTORE_RUNTIME.value] = self._handle_restore_runtime
        self._handlers[RecoveryAction.RESTORE_PLUGINS.value] = self._handle_restore_plugins
        self._handlers[RecoveryAction.RESTORE_MEMORY.value] = self._handle_restore_memory
        self._handlers[RecoveryAction.RETRY_REQUEST.value] = self._handle_retry_request
        self._handlers[RecoveryAction.RESTORE_POLICY.value] = self._handle_restore_policy
        self._handlers[RecoveryAction.RESTART_AGENT.value] = self._handle_restart_agent

    def register_handler(self, action: str, handler: RecoveryHandler) -> None:
        self._handlers[action] = handler

    def execute_plan(
        self,
        plan: RecoveryPlan,
        context: dict[str, Any] | None = None,
    ) -> RecoveryResult:
        """Execute a recovery plan."""
        start = time.monotonic()
        ctx = context or {}
        attempted: list[str] = []
        succeeded: list[str] = []
        failed: list[str] = []

        for action in plan.actions:
            attempted.append(action.value)
            handler = self._handlers.get(action.value)

            if handler is None:
                failed.append(action.value)
                logger.warning("recovery_handler_missing", action=action.value)
                continue

            for attempt in range(self._max_attempts):
                try:
                    handler(action, {**ctx, **plan.parameters})
                    succeeded.append(action.value)
                    logger.info(
                        "recovery_action_succeeded",
                        action=action.value,
                        attempt=attempt + 1,
                    )
                    break
                except Exception as e:
                    if attempt == self._max_attempts - 1:
                        failed.append(action.value)
                        logger.error(
                            "recovery_action_failed",
                            action=action.value,
                            error=str(e),
                            attempts=self._max_attempts,
                        )

        success = len(failed) == 0
        result = RecoveryResult(
            correlation_id=plan.correlation_id,
            plan_id=plan.plan_id,
            actions_attempted=attempted,
            actions_succeeded=succeeded,
            actions_failed=failed,
            success=success,
            execution_time_ms=(time.monotonic() - start) * 1000,
        )
        self._results[result.result_id] = result
        return result

    def get_result(self, result_id: str) -> RecoveryResult | None:
        return self._results.get(result_id)

    def list_results(self) -> list[RecoveryResult]:
        return list(self._results.values())

    # ------------------------------------------------------------------
    # Default handlers (stubs — in production these would call real systems)
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_resume_session(action: RecoveryAction, context: dict[str, Any]) -> Any:
        session_id = context.get("session_id", "unknown")
        logger.info("session_resumed", session_id=session_id)
        return {"resumed": True, "session_id": session_id}

    @staticmethod
    def _handle_restore_runtime(action: RecoveryAction, context: dict[str, Any]) -> Any:
        logger.info("runtime_restored")
        return {"restored": True}

    @staticmethod
    def _handle_restore_plugins(action: RecoveryAction, context: dict[str, Any]) -> Any:
        plugins = context.get("plugins", [])
        logger.info("plugins_restored", count=len(plugins))
        return {"restored": True, "plugins": plugins}

    @staticmethod
    def _handle_restore_memory(action: RecoveryAction, context: dict[str, Any]) -> Any:
        logger.info("memory_restored")
        return {"restored": True}

    @staticmethod
    def _handle_retry_request(action: RecoveryAction, context: dict[str, Any]) -> Any:
        request_id = context.get("request_id", "unknown")
        logger.info("request_retried", request_id=request_id)
        return {"retried": True, "request_id": request_id}

    @staticmethod
    def _handle_restore_policy(action: RecoveryAction, context: dict[str, Any]) -> Any:
        version = context.get("policy_version", "unknown")
        logger.info("policy_restored", version=version)
        return {"restored": True, "version": version}

    @staticmethod
    def _handle_restart_agent(action: RecoveryAction, context: dict[str, Any]) -> Any:
        agent_id = context.get("agent_id", "unknown")
        logger.info("agent_restarted", agent_id=agent_id)
        return {"restarted": True, "agent_id": agent_id}
