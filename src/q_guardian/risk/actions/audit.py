"""Audit — audit trail management for risk decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.risk.data import AuditRecord, PolicyDecision, RiskAssessment
from q_guardian.risk.enums import AuditStatus, DecisionOutcome, Severity

if TYPE_CHECKING:
    from datetime import datetime

logger = structlog.get_logger("risk.audit")


class AuditTrail:
    """Manages the audit trail for all risk decisions.

    Provides immutable record-keeping for compliance and
    forensics. Records cannot be modified after creation —
    only their status can be updated.
    """

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    @property
    def record_count(self) -> int:
        return len(self._records)

    def record(
        self,
        assessment: RiskAssessment,
        decision: PolicyDecision,
    ) -> AuditRecord:
        """Create an audit record from an assessment and decision.

        Args:
            assessment: The risk assessment.
            decision: The policy decision.

        Returns:
            The created AuditRecord.
        """
        record = AuditRecord(
            assessment_id=assessment.assessment_id,
            decision_id=decision.decision_id,
            prediction_id=assessment.prediction_id,
            risk_score=assessment.risk_score,
            risk_level=assessment.risk_level,
            severity=assessment.severity.severity,
            outcome=decision.outcome,
            action=decision.action,
            contributing_sources=assessment.contributing_sources,
            reasoning=decision.reasoning,
            policy_name=decision.policy_name,
            status=AuditStatus.ACTIVE,
        )
        self._records.append(record)

        logger.info(
            "audit_record_created",
            record_id=record.record_id,
            outcome=decision.outcome.value,
            risk_score=assessment.risk_score,
        )

        return record

    def get_record(self, record_id: str) -> AuditRecord | None:
        """Get a record by ID."""
        for r in self._records:
            if r.record_id == record_id:
                return r
        return None

    def update_status(self, record_id: str, status: AuditStatus) -> bool:
        """Update a record's status.

        Returns:
            True if the record was found and updated.
        """
        record = self.get_record(record_id)
        if record is not None:
            record.status = status
            logger.info("audit_status_updated", record_id=record_id, status=status.value)
            return True
        return False

    def query(
        self,
        outcome: DecisionOutcome | None = None,
        severity: Severity | None = None,
        status: AuditStatus | None = None,
        policy_name: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """Query audit records with filters.

        Args:
            outcome: Filter by decision outcome.
            severity: Filter by severity.
            status: Filter by audit status.
            policy_name: Filter by policy name.
            since: Only return records after this datetime.
            limit: Maximum records to return.

        Returns:
            Matching audit records.
        """
        result = list(self._records)

        if outcome is not None:
            result = [r for r in result if r.outcome == outcome]
        if severity is not None:
            result = [r for r in result if r.severity == severity]
        if status is not None:
            result = [r for r in result if r.status == status]
        if policy_name is not None:
            result = [r for r in result if r.policy_name == policy_name]
        if since is not None:
            result = [r for r in result if r.created_at >= since]

        return result[-limit:]

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the audit trail."""
        outcomes: dict[str, int] = {}
        severities: dict[str, int] = {}
        for r in self._records:
            outcomes[r.outcome.value] = outcomes.get(r.outcome.value, 0) + 1
            severities[r.severity.value] = severities.get(r.severity.value, 0) + 1

        return {
            "total_records": self.record_count,
            "outcomes": outcomes,
            "severities": severities,
        }

    def clear(self) -> int:
        """Clear all audit records.

        Returns:
            Number of records cleared.
        """
        count = len(self._records)
        self._records.clear()
        return count
