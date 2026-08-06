"""Agent quarantine support."""

from __future__ import annotations

from typing import TYPE_CHECKING

from q_guardian.response.enums import QuarantineType

if TYPE_CHECKING:
    from q_guardian.response.data import QuarantineRecord
    from q_guardian.response.quarantine.quarantine_manager import QuarantineManager


class AgentQuarantine:
    """Convenience wrapper for agent quarantine operations."""

    def __init__(self, manager: QuarantineManager) -> None:
        self._manager = manager

    def quarantine_agent(
        self,
        agent_id: str,
        reason: str = "",
        correlation_id: str = "",
        duration_seconds: float | None = None,
    ) -> QuarantineRecord:
        return self._manager.quarantine(
            target_type=QuarantineType.AGENT,
            target_id=agent_id,
            reason=reason,
            correlation_id=correlation_id,
            duration_seconds=duration_seconds,
            actions_blocked=["all"],
        )

    def is_agent_quarantined(self, agent_id: str) -> bool:
        return self._manager.is_quarantined(QuarantineType.AGENT, agent_id)

    def release_agent(self, quarantine_id: str, released_by: str = "system") -> QuarantineRecord:
        return self._manager.release(quarantine_id, released_by)
