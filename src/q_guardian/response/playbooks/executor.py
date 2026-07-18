"""Playbook Executor — executes playbooks through the orchestration engine."""

from __future__ import annotations

import time
from typing import Any, Callable

import structlog

from q_guardian.response.data import PlaybookDefinition, PlaybookExecution
from q_guardian.response.engine.orchestration_engine import OrchestrationEngine
from q_guardian.response.exceptions import PlaybookError

logger = structlog.get_logger(__name__)


class PlaybookExecutor:
    """Executes playbooks using the orchestration engine."""

    def __init__(self, orchestration_engine: OrchestrationEngine | None = None) -> None:
        self._engine = orchestration_engine or OrchestrationEngine()
        self._executions: list[PlaybookExecution] = []

    def execute(
        self,
        playbook: PlaybookDefinition,
        context: dict[str, Any],
        correlation_id: str = "",
    ) -> PlaybookExecution:
        """Execute a playbook."""
        if not playbook.enabled:
            raise PlaybookError(f"Playbook '{playbook.name}' is disabled")

        if not playbook.steps:
            raise PlaybookError(f"Playbook '{playbook.name}' has no steps")

        execution = self._engine.execute_playbook(
            playbook, context, correlation_id=correlation_id
        )
        self._executions.append(execution)
        return execution

    def execute_by_trigger(
        self,
        trigger: str,
        context: dict[str, Any],
        registry: Any,
        correlation_id: str = "",
    ) -> PlaybookExecution | None:
        """Find and execute a playbook by trigger."""
        playbook = registry.get_by_trigger(trigger)
        if playbook is None:
            logger.warning("no_playbook_for_trigger", trigger=trigger)
            return None
        return self.execute(playbook, context, correlation_id=correlation_id)

    @property
    def engine(self) -> OrchestrationEngine:
        return self._engine

    def list_executions(self) -> list[PlaybookExecution]:
        return list(self._executions)
