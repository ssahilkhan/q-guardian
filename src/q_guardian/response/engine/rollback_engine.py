"""Rollback Engine — checkpoint-based rollback for policy, session, plugin, config, runtime."""

from __future__ import annotations

import time
from typing import Any

import structlog

from q_guardian.response.data import Checkpoint, RollbackResult
from q_guardian.response.enums import RollbackTarget
from q_guardian.response.exceptions import RollbackError

logger = structlog.get_logger(__name__)


class RollbackEngine:
    """Checkpoint-based rollback engine.

    Supports rolling back policy, session, plugin, configuration,
    and runtime state. Every checkpoint is an immutable snapshot.
    """

    def __init__(self, max_checkpoints: int = 50) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}
        self._results: dict[str, RollbackResult] = {}
        self._max_checkpoints = max_checkpoints

    def create_checkpoint(
        self,
        target: RollbackTarget,
        state: dict[str, Any],
        correlation_id: str = "",
        description: str = "",
    ) -> Checkpoint:
        """Create a checkpoint of the current state."""
        checkpoint = Checkpoint(
            correlation_id=correlation_id,
            target=target,
            snapshot=state.copy(),
            description=description,
        )
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint

        # Enforce max checkpoints per target
        target_checkpoints = [
            c
            for c in self._checkpoints.values()
            if c.target == target
        ]
        if len(target_checkpoints) > self._max_checkpoints:
            oldest = target_checkpoints[0]
            del self._checkpoints[oldest.checkpoint_id]

        logger.info(
            "checkpoint_created",
            checkpoint_id=checkpoint.checkpoint_id,
            target=target.value,
        )
        return checkpoint

    def rollback(
        self,
        checkpoint_id: str,
    ) -> RollbackResult:
        """Rollback to a specific checkpoint."""
        start = time.monotonic()

        checkpoint = self._checkpoints.get(checkpoint_id)
        if checkpoint is None:
            return RollbackResult(
                success=False,
                error=f"Checkpoint not found: {checkpoint_id}",
            )

        result = RollbackResult(
            correlation_id=checkpoint.correlation_id,
            checkpoint_id=checkpoint_id,
            target=checkpoint.target,
            success=True,
            restored_state=checkpoint.snapshot.copy(),
            execution_time_ms=(time.monotonic() - start) * 1000,
        )

        self._results[result.rollback_id] = result
        logger.info(
            "rollback_completed",
            rollback_id=result.rollback_id,
            target=checkpoint.target.value,
        )
        return result

    def rollback_latest(self, target: RollbackTarget) -> RollbackResult:
        """Rollback to the most recent checkpoint for a given target."""
        target_checkpoints = [
            c
            for c in self._checkpoints.values()
            if c.target == target
        ]
        if not target_checkpoints:
            return RollbackResult(
                success=False,
                error=f"No checkpoints found for target: {target.value}",
            )
        latest = target_checkpoints[-1]
        return self.rollback(latest.checkpoint_id)

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        return self._checkpoints.get(checkpoint_id)

    def list_checkpoints(
        self, target: RollbackTarget | None = None
    ) -> list[Checkpoint]:
        if target:
            return [c for c in self._checkpoints.values() if c.target == target]
        return list(self._checkpoints.values())

    def get_result(self, rollback_id: str) -> RollbackResult | None:
        return self._results.get(rollback_id)

    def list_results(self) -> list[RollbackResult]:
        return list(self._results.values())

    def clear(self, target: RollbackTarget | None = None) -> None:
        if target:
            to_remove = [
                cid
                for cid, c in self._checkpoints.items()
                if c.target == target
            ]
            for cid in to_remove:
                del self._checkpoints[cid]
        else:
            self._checkpoints.clear()
