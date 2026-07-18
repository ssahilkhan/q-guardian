"""Memory quarantine support."""

from __future__ import annotations

from q_guardian.response.data import QuarantineRecord
from q_guardian.response.enums import QuarantineType
from q_guardian.response.quarantine.quarantine_manager import QuarantineManager


class MemoryQuarantine:
    """Convenience wrapper for memory quarantine operations."""

    def __init__(self, manager: QuarantineManager) -> None:
        self._manager = manager

    def quarantine_memory(
        self, memory_id: str, reason: str = "", correlation_id: str = "",
        duration_seconds: float | None = None,
    ) -> QuarantineRecord:
        return self._manager.quarantine(
            target_type=QuarantineType.MEMORY,
            target_id=memory_id,
            reason=reason,
            correlation_id=correlation_id,
            duration_seconds=duration_seconds,
            actions_blocked=["read", "write", "delete"],
        )

    def is_memory_quarantined(self, memory_id: str) -> bool:
        return self._manager.is_quarantined(QuarantineType.MEMORY, memory_id)

    def release_memory(self, quarantine_id: str, released_by: str = "system") -> QuarantineRecord:
        return self._manager.release(quarantine_id, released_by)
