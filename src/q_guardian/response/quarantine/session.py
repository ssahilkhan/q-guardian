"""Session quarantine support."""

from __future__ import annotations

from typing import TYPE_CHECKING

from q_guardian.response.enums import QuarantineType

if TYPE_CHECKING:
    from q_guardian.response.data import QuarantineRecord
    from q_guardian.response.quarantine.quarantine_manager import QuarantineManager


class SessionQuarantine:
    """Convenience wrapper for session quarantine operations."""

    def __init__(self, manager: QuarantineManager) -> None:
        self._manager = manager

    def quarantine_session(
        self,
        session_id: str,
        reason: str = "",
        correlation_id: str = "",
        duration_seconds: float | None = None,
    ) -> QuarantineRecord:
        return self._manager.quarantine(
            target_type=QuarantineType.SESSION,
            target_id=session_id,
            reason=reason,
            correlation_id=correlation_id,
            duration_seconds=duration_seconds,
            actions_blocked=["send_message", "execute_tool", "access_memory"],
        )

    def is_session_quarantined(self, session_id: str) -> bool:
        return self._manager.is_quarantined(QuarantineType.SESSION, session_id)

    def release_session(self, quarantine_id: str, released_by: str = "system") -> QuarantineRecord:
        return self._manager.release(quarantine_id, released_by)
