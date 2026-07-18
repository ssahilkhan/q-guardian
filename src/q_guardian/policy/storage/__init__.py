"""Policy Storage — JSON file persistence for policies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from q_guardian.policy.data import AdvancedPolicyDefinition

logger = structlog.get_logger(__name__)


class PolicyStorage:
    """JSON file-based persistence for policies."""

    def __init__(self, storage_path: str = "policy_store.json") -> None:
        self._path = Path(storage_path)
        self._policies: dict[str, dict[str, Any]] = {}
        self._load()

    def save(self, policy: AdvancedPolicyDefinition) -> None:
        self._policies[policy.policy_id] = policy.model_dump(mode="json")
        self._persist()

    def save_all(self, policies: list[AdvancedPolicyDefinition]) -> None:
        for p in policies:
            self._policies[p.policy_id] = p.model_dump(mode="json")
        self._persist()

    def load(self, policy_id: str) -> AdvancedPolicyDefinition | None:
        data = self._policies.get(policy_id)
        if data is None:
            return None
        return AdvancedPolicyDefinition(**data)

    def load_all(self) -> list[AdvancedPolicyDefinition]:
        return [AdvancedPolicyDefinition(**d) for d in self._policies.values()]

    def delete(self, policy_id: str) -> bool:
        if policy_id in self._policies:
            del self._policies[policy_id]
            self._persist()
            return True
        return False

    def exists(self, policy_id: str) -> bool:
        return policy_id in self._policies

    def count(self) -> int:
        return len(self._policies)

    def clear(self) -> None:
        self._policies.clear()
        self._persist()

    def _persist(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._policies, indent=2, default=str)
            )
        except Exception as e:
            logger.error("storage_persist_error", error=str(e))

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            self._policies = json.loads(self._path.read_text())
            logger.info("storage_loaded", count=len(self._policies))
        except Exception as e:
            logger.error("storage_load_error", error=str(e))
            self._policies = {}
