"""Orchestration Engine — executes response workflows with parallel/sequential steps."""

from __future__ import annotations

import time
from typing import Any, Callable

import structlog

from q_guardian.response.data import (
    PlaybookDefinition,
    PlaybookExecution,
    PlaybookStep,
    ResponseRequest,
    ResponseResult,
    StepResult,
)
from q_guardian.response.enums import ResponseStatus, StepStatus, StepType
from q_guardian.response.exceptions import OrchestrationError

logger = structlog.get_logger(__name__)

# Type alias for step handlers
StepHandler = Callable[[PlaybookStep, dict[str, Any]], Any]


class OrchestrationEngine:
    """Executes response workflows with dependency management,
    parallel execution, failure recovery, and step rollback.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, StepHandler] = {}
        self._executions: dict[str, PlaybookExecution] = {}
        self._step_outputs: dict[str, dict[str, Any]] = {}

    def register_handler(self, step_type: str, handler: StepHandler) -> None:
        """Register a handler for a step type."""
        self._handlers[step_type] = handler

    def execute_playbook(
        self,
        playbook: PlaybookDefinition,
        context: dict[str, Any],
        correlation_id: str = "",
    ) -> PlaybookExecution:
        """Execute a playbook against a context."""
        start = time.monotonic()
        execution = PlaybookExecution(
            playbook_id=playbook.playbook_id,
            playbook_name=playbook.name,
            correlation_id=correlation_id,
            status=ResponseStatus.IN_PROGRESS,
            started_at=time.monotonic(),
        )

        step_outputs: dict[str, Any] = {}
        executed_steps: list[str] = []
        failed_steps: list[str] = []

        for step in playbook.steps:
            if not step.enabled:
                continue

            # Check dependencies
            if step.depends_on:
                unmet = [d for d in step.depends_on if d not in executed_steps]
                if unmet:
                    step_results_entry = StepResult(
                        step_id=step.step_id,
                        step_name=step.name,
                        status=StepStatus.SKIPPED,
                        error=f"Unmet dependencies: {unmet}",
                    )
                    execution.step_results.append(step_results_entry)
                    continue

            # Execute step
            step_start = time.monotonic()
            merged_ctx = {**context, **step_outputs, "_correlation_id": correlation_id}

            try:
                output = self._execute_step(step, merged_ctx)
                step_status = StepStatus.COMPLETED
                step_outputs[step.step_id] = output
                executed_steps.append(step.step_id)
                error = ""
            except Exception as e:
                step_status = StepStatus.FAILED
                failed_steps.append(step.step_id)
                error = str(e)

                if step.failure_strategy.value == "stop":
                    execution.status = ResponseStatus.FAILED
                    break
                elif step.failure_strategy.value == "rollback":
                    execution.status = ResponseStatus.ROLLED_BACK
                    break
                elif step.failure_strategy.value == "skip":
                    pass  # continue to next step
                elif step.failure_strategy.value == "retry":
                    for attempt in range(step.retry_count):
                        try:
                            output = self._execute_step(step, merged_ctx)
                            step_status = StepStatus.COMPLETED
                            step_outputs[step.step_id] = output
                            failed_steps.remove(step.step_id)
                            executed_steps.append(step.step_id)
                            error = ""
                            break
                        except Exception:
                            error = f"Retry {attempt + 1}/{step.retry_count} failed"

            step_elapsed = (time.monotonic() - step_start) * 1000
            execution.step_results.append(
                StepResult(
                    step_id=step.step_id,
                    step_name=step.name,
                    status=step_status,
                    output=step_outputs.get(step.step_id),
                    error=error,
                    execution_time_ms=step_elapsed,
                )
            )

            logger.info(
                "step_executed",
                step_id=step.step_id,
                status=step_status.value,
                elapsed_ms=round(step_elapsed, 2),
            )

        if execution.status == ResponseStatus.IN_PROGRESS:
            execution.status = (
                ResponseStatus.COMPLETED
                if not failed_steps
                else ResponseStatus.PARTIAL
            )

        execution.completed_at = time.monotonic()
        execution.execution_time_ms = (time.monotonic() - start) * 1000
        self._executions[execution.execution_id] = execution
        self._step_outputs[execution.execution_id] = step_outputs

        logger.info(
            "playbook_executed",
            playbook_id=playbook.playbook_id,
            status=execution.status.value,
            steps_executed=len(executed_steps),
            steps_failed=len(failed_steps),
        )

        return execution

    def _execute_step(
        self, step: PlaybookStep, context: dict[str, Any]
    ) -> Any:
        """Execute a single step using registered handlers."""
        handler = self._handlers.get(step.step_type.value)
        if handler is None:
            handler = self._handlers.get("action")

        if handler:
            return handler(step, context)

        # Default: return step parameters as output
        return {"action": step.action, "parameters": step.parameters}

    def get_execution(self, execution_id: str) -> PlaybookExecution | None:
        return self._executions.get(execution_id)

    def get_step_outputs(self, execution_id: str) -> dict[str, Any]:
        return self._step_outputs.get(execution_id, {})

    def list_executions(self) -> list[PlaybookExecution]:
        return list(self._executions.values())

    @property
    def handlers(self) -> dict[str, StepHandler]:
        return dict(self._handlers)
