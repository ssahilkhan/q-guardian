"""Response Storage — persistence for response engine state."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from q_guardian.response.data import (
    PlaybookExecution,
    QuarantineRecord,
    RecoveryResult,
    ResponseResult,
    RollbackResult,
    Timeline,
)
from q_guardian.response.exceptions import ResponseEngineError

logger = structlog.get_logger(__name__)


class ResponseStorage:
    """Stores response engine state to disk."""

    def __init__(self, storage_path: str = "response_storage") -> None:
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)

        # Sub-directories
        self._responses_path = self._storage_path / "responses"
        self._quarantines_path = self._storage_path / "quarantines"
        self._playbooks_path = self._storage_path / "playbooks"
        self._evidence_path = self._storage_path / "evidence"
        self._recovery_path = self._storage_path / "recovery"
        self._rollbacks_path = self._storage_path / "rollbacks"

        for p in [
            self._responses_path,
            self._quarantines_path,
            self._playbooks_path,
            self._evidence_path,
            self._recovery_path,
            self._rollbacks_path,
        ]:
            p.mkdir(parents=True, exist_ok=True)

    def save_response(self, result: ResponseResult) -> Path:
        path = self._responses_path / f"{result.result_id}.json"
        data = self._serialize(result)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.debug("response_saved", response_id=result.result_id, path=str(path))
        return path

    def load_response(self, response_id: str) -> dict[str, Any] | None:
        path = self._responses_path / f"{response_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_quarantine(self, record: QuarantineRecord) -> Path:
        path = self._quarantines_path / f"{record.quarantine_id}.json"
        data = self._serialize(record)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def load_quarantine(self, quarantine_id: str) -> dict[str, Any] | None:
        path = self._quarantines_path / f"{quarantine_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_playbook_execution(self, execution: PlaybookExecution) -> Path:
        path = self._playbooks_path / f"{execution.execution_id}.json"
        data = self._serialize(execution)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def save_rollback(self, result: RollbackResult) -> Path:
        path = self._rollbacks_path / f"{result.rollback_id}.json"
        data = self._serialize(result)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def save_recovery(self, result: RecoveryResult) -> Path:
        path = self._recovery_path / f"{result.result_id}.json"
        data = self._serialize(result)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def list_responses(self) -> list[str]:
        return [f.stem for f in self._responses_path.glob("*.json")]

    def list_quarantines(self) -> list[str]:
        return [f.stem for f in self._quarantines_path.glob("*.json")]

    def list_playbook_executions(self) -> list[str]:
        return [f.stem for f in self._playbooks_path.glob("*.json")]

    def delete(self, category: str, item_id: str) -> bool:
        path_map = {
            "response": self._responses_path,
            "quarantine": self._quarantines_path,
            "playbook": self._playbooks_path,
            "evidence": self._evidence_path,
            "recovery": self._recovery_path,
            "rollback": self._rollbacks_path,
        }
        base = path_map.get(category)
        if base is None:
            return False
        target = base / f"{item_id}.json"
        if target.exists():
            target.unlink()
            return True
        return False

    @staticmethod
    def _serialize(obj: Any) -> dict[str, Any]:
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        elif hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return {"value": str(obj)}
