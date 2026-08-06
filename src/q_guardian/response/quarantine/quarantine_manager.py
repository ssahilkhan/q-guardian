"""Quarantine Manager — manages quarantine lifecycle for agents, sessions,
plugins, memory, tools."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from q_guardian.response.data import QuarantineRecord
from q_guardian.response.enums import QuarantineStatus, QuarantineType
from q_guardian.response.exceptions import QuarantineError

logger = structlog.get_logger(__name__)


class QuarantineManager:
    """Manages quarantine lifecycle with timed release and manual release."""

    def __init__(
        self,
        default_duration_seconds: float = 3600.0,
        max_duration_seconds: float = 86400.0,
    ) -> None:
        self._quarantines: dict[str, QuarantineRecord] = {}
        self._default_duration = default_duration_seconds
        self._max_duration = max_duration_seconds

    def quarantine(
        self,
        target_type: QuarantineType,
        target_id: str,
        reason: str = "",
        correlation_id: str = "",
        duration_seconds: float | None = None,
        actions_blocked: list[str] | None = None,
    ) -> QuarantineRecord:
        """Place a target in quarantine."""
        duration = duration_seconds or self._default_duration
        duration = min(duration, self._max_duration)

        record = QuarantineRecord(
            correlation_id=correlation_id,
            target_type=target_type,
            target_id=target_id,
            status=QuarantineStatus.ACTIVE,
            reason=reason,
            actions_blocked=actions_blocked or [],
            expires_at=datetime.now(UTC) + timedelta(seconds=duration),
        )
        self._quarantines[record.quarantine_id] = record

        logger.info(
            "quarantine_activated",
            quarantine_id=record.quarantine_id,
            target_type=target_type.value,
            target_id=target_id,
            duration_seconds=duration,
        )
        return record

    def release(
        self,
        quarantine_id: str,
        released_by: str = "system",
    ) -> QuarantineRecord:
        """Manually release a quarantine."""
        record = self._get(quarantine_id)
        if record.status != QuarantineStatus.ACTIVE:
            raise QuarantineError(
                f"Quarantine {quarantine_id} is not active (status={record.status.value})"
            )
        record.status = QuarantineStatus.MANUALLY_RELEASED
        record.released_at = datetime.now(UTC)
        record.released_by = released_by
        logger.info(
            "quarantine_released",
            quarantine_id=quarantine_id,
            released_by=released_by,
        )
        return record

    def check_expired(self) -> list[QuarantineRecord]:
        """Check and auto-release expired quarantines."""
        now = datetime.now(UTC)
        expired: list[QuarantineRecord] = []
        for record in self._quarantines.values():
            if record.status != QuarantineStatus.ACTIVE:
                continue
            if record.expires_at and now >= record.expires_at:
                record.status = QuarantineStatus.AUTO_RELEASED
                record.released_at = now
                record.released_by = "system-auto-release"
                expired.append(record)
                logger.info(
                    "quarantine_auto_released",
                    quarantine_id=record.quarantine_id,
                )
        return expired

    def is_quarantined(
        self,
        target_type: QuarantineType,
        target_id: str,
    ) -> bool:
        """Check if a target is currently quarantined."""
        for record in self._quarantines.values():
            if (
                record.target_type == target_type
                and record.target_id == target_id
                and record.status == QuarantineStatus.ACTIVE
            ):
                return True
        return False

    def get(self, quarantine_id: str) -> QuarantineRecord | None:
        return self._quarantines.get(quarantine_id)

    def get_active(self) -> list[QuarantineRecord]:
        return [r for r in self._quarantines.values() if r.status == QuarantineStatus.ACTIVE]

    def get_by_target(self, target_type: QuarantineType, target_id: str) -> list[QuarantineRecord]:
        return [
            r
            for r in self._quarantines.values()
            if r.target_type == target_type and r.target_id == target_id
        ]

    def list_all(self) -> list[QuarantineRecord]:
        return list(self._quarantines.values())

    def count_active(self) -> int:
        return len(self.get_active())

    def _get(self, quarantine_id: str) -> QuarantineRecord:
        record = self._quarantines.get(quarantine_id)
        if record is None:
            raise QuarantineError(f"Quarantine not found: {quarantine_id}")
        return record
