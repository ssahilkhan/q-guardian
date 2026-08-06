"""Policy Registry — manages advanced policy definitions with persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import structlog

from q_guardian.policy.data import AdvancedPolicyDefinition
from q_guardian.policy.enums import PolicyStatus
from q_guardian.policy.exceptions import PolicyNotFoundError

logger = structlog.get_logger(__name__)


class PolicyRegistry:
    """In-memory registry with optional file persistence for advanced policies."""

    def __init__(self, storage_path: str | None = None) -> None:
        self._policies: dict[str, AdvancedPolicyDefinition] = {}
        self._storage_path = storage_path
        if storage_path:
            self._load_from_file()

    def register(self, policy: AdvancedPolicyDefinition) -> None:
        if policy.policy_id in self._policies:
            raise ValueError(f"Policy already registered: {policy.name} ({policy.policy_id})")
        self._policies[policy.policy_id] = policy
        logger.info("policy_registered", policy_id=policy.policy_id, name=policy.name)
        self._persist()

    def unregister(self, policy_id: str) -> bool:
        if policy_id not in self._policies:
            return False
        del self._policies[policy_id]
        logger.info("policy_unregistered", policy_id=policy_id)
        self._persist()
        return True

    def get(self, policy_id: str) -> AdvancedPolicyDefinition:
        if policy_id not in self._policies:
            raise PolicyNotFoundError(f"Policy not found: {policy_id}")
        return self._policies[policy_id]

    def get_by_name(self, name: str) -> AdvancedPolicyDefinition | None:
        for p in self._policies.values():
            if p.name == name:
                return p
        return None

    def has(self, policy_id: str) -> bool:
        return policy_id in self._policies

    def list_policies(self) -> list[AdvancedPolicyDefinition]:
        return list(self._policies.values())

    def list_by_status(self, status: PolicyStatus) -> list[AdvancedPolicyDefinition]:
        return [p for p in self._policies.values() if p.status == status]

    def list_active(self) -> list[AdvancedPolicyDefinition]:
        return self.list_by_status(PolicyStatus.ACTIVE)

    def update(self, policy: AdvancedPolicyDefinition) -> None:
        policy.updated_at = datetime.now(UTC)
        self._policies[policy.policy_id] = policy
        logger.info("policy_updated", policy_id=policy.policy_id, name=policy.name)
        self._persist()

    def activate(self, policy_id: str) -> None:
        policy = self.get(policy_id)
        policy.status = PolicyStatus.ACTIVE
        policy.updated_at = datetime.now(UTC)
        logger.info("policy_activated", policy_id=policy_id)
        self._persist()

    def deactivate(self, policy_id: str) -> None:
        policy = self.get(policy_id)
        policy.status = PolicyStatus.SUSPENDED
        policy.updated_at = datetime.now(UTC)
        logger.info("policy_deactivated", policy_id=policy_id)
        self._persist()

    def count(self) -> int:
        return len(self._policies)

    def clear(self) -> None:
        self._policies.clear()
        self._persist()

    def _persist(self) -> None:
        if not self._storage_path:
            return
        try:
            data = {pid: p.model_dump(mode="json") for pid, p in self._policies.items()}
            Path(self._storage_path).parent.mkdir(parents=True, exist_ok=True)
            Path(self._storage_path).write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error("policy_persist_error", error=str(e))

    def _load_from_file(self) -> None:
        if not self._storage_path:
            return
        path = Path(self._storage_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            for pid, pdata in data.items():
                self._policies[pid] = AdvancedPolicyDefinition(**pdata)
            logger.info("policies_loaded", count=len(self._policies))
        except Exception as e:
            logger.error("policy_load_error", error=str(e))
