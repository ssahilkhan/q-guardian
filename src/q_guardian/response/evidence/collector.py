"""Evidence Collector — collects and records security evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.response.data import EvidenceRecord

if TYPE_CHECKING:
    from q_guardian.response.enums import EvidenceType

logger = structlog.get_logger(__name__)


class EvidenceCollector:
    """Collects evidence records for security incidents."""

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    def collect(
        self,
        evidence_type: EvidenceType,
        source: str,
        data: dict[str, Any] | str = "",
        correlation_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceRecord:
        """Collect a piece of evidence."""
        merged_meta = {**(metadata or {}), "source": source}
        content = data if isinstance(data, dict) else {"value": data}
        record = EvidenceRecord(
            correlation_id=correlation_id,
            evidence_type=evidence_type,
            content=content,
            metadata=merged_meta,
        )
        self._records[record.evidence_id] = record
        logger.info(
            "evidence_collected",
            evidence_id=record.evidence_id,
            type=evidence_type.value,
            source=source,
        )
        return record

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self._records.get(evidence_id)

    def get_by_correlation(self, correlation_id: str) -> list[EvidenceRecord]:
        return [r for r in self._records.values() if r.correlation_id == correlation_id]

    def get_by_type(self, evidence_type: EvidenceType) -> list[EvidenceRecord]:
        return [r for r in self._records.values() if r.evidence_type == evidence_type]

    def list_all(self) -> list[EvidenceRecord]:
        return list(self._records.values())

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()
