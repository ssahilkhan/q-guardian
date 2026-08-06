"""Snapshot — captures point-in-time snapshots of agent state for evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.response.enums import EvidenceType

if TYPE_CHECKING:
    from q_guardian.response.evidence.collector import EvidenceCollector

logger = structlog.get_logger(__name__)


class EvidenceSnapshot:
    """Captures point-in-time snapshots of state."""

    def __init__(self, collector: EvidenceCollector) -> None:
        self._collector = collector
        self._snapshots: list[dict[str, Any]] = []

    def capture(
        self,
        name: str,
        state: dict[str, Any],
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Capture a snapshot of state."""
        snapshot = {
            "name": name,
            "state": state,
            "timestamp": datetime.now(UTC).isoformat(),
            "correlation_id": correlation_id,
        }
        self._snapshots.append(snapshot)

        self._collector.collect(
            evidence_type=EvidenceType.SYSTEM_STATE,
            source=f"snapshot:{name}",
            data=state,
            correlation_id=correlation_id,
            metadata={"snapshot_name": name},
        )

        logger.info("snapshot_captured", name=name, correlation_id=correlation_id)
        return snapshot

    def get_snapshots(self) -> list[dict[str, Any]]:
        return list(self._snapshots)

    def get_snapshot_by_name(self, name: str) -> dict[str, Any] | None:
        for s in self._snapshots:
            if s["name"] == name:
                return s
        return None
