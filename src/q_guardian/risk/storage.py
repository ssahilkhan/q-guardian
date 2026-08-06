"""RiskStorage — persistence for risk assessment data.

Handles serialization and storage of audit records, assessments,
and explanations. Uses JSON file-based storage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.risk.exceptions import RiskError

if TYPE_CHECKING:
    from q_guardian.risk.data import AuditRecord, Explanation, RiskAssessment

logger = structlog.get_logger("risk.storage")


class RiskStorage:
    """File-based persistence for risk module data.

    Directory layout:
      storage_root/
        assessments/
        audit/
        explanations/
    """

    def __init__(self, storage_root: str | Path | None = None) -> None:
        if storage_root is None:
            storage_root = Path("risk_storage")
        self._root = Path(storage_root)
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "assessments").mkdir(exist_ok=True)
        (self._root / "audit").mkdir(exist_ok=True)
        (self._root / "explanations").mkdir(exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def save_assessment(self, assessment: RiskAssessment) -> Path:
        """Save a risk assessment to disk."""
        path = self._root / "assessments" / f"{assessment.assessment_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(assessment.model_dump(mode="json"), f, indent=2, default=str)
        logger.debug("assessment_saved", assessment_id=assessment.assessment_id)
        return path

    def load_assessment(self, assessment_id: str) -> dict[str, Any]:
        """Load a risk assessment from disk."""
        path = self._root / "assessments" / f"{assessment_id}.json"
        if not path.exists():
            raise RiskError(f"Assessment not found: {assessment_id}")
        with open(path, encoding="utf-8") as f:
            assessment: dict[str, Any] = json.load(f)
            return assessment

    def save_audit_record(self, record: AuditRecord) -> Path:
        """Save an audit record to disk."""
        path = self._root / "audit" / f"{record.record_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record.model_dump(mode="json"), f, indent=2, default=str)
        logger.debug("audit_record_saved", record_id=record.record_id)
        return path

    def save_explanation(self, explanation: Explanation) -> Path:
        """Save an explanation to disk."""
        path = self._root / "explanations" / f"{explanation.explanation_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(explanation.model_dump(mode="json"), f, indent=2, default=str)
        logger.debug("explanation_saved", explanation_id=explanation.explanation_id)
        return path

    def list_assessments(self) -> list[str]:
        """List stored assessment IDs."""
        dir_path = self._root / "assessments"
        return [f.stem for f in dir_path.glob("*.json")]

    def list_audit_records(self) -> list[str]:
        """List stored audit record IDs."""
        dir_path = self._root / "audit"
        return [f.stem for f in dir_path.glob("*.json")]

    def delete_assessment(self, assessment_id: str) -> bool:
        """Delete a stored assessment."""
        path = self._root / "assessments" / f"{assessment_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        assessment_count = len(list((self._root / "assessments").glob("*.json")))
        audit_count = len(list((self._root / "audit").glob("*.json")))
        explanation_count = len(list((self._root / "explanations").glob("*.json")))

        total_size = sum(f.stat().st_size for f in self._root.rglob("*.json") if f.is_file())

        return {
            "storage_root": str(self._root),
            "assessment_count": assessment_count,
            "audit_count": audit_count,
            "explanation_count": explanation_count,
            "total_size_bytes": total_size,
        }
