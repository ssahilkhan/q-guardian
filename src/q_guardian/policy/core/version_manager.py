"""Version Manager — manages policy versions with snapshot, rollback, and changelog."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from q_guardian.policy.data import AdvancedPolicyDefinition, PolicyVersion
from q_guardian.policy.exceptions import PolicyVersionError

logger = structlog.get_logger(__name__)


class VersionManager:
    """Manages policy version lifecycle with snapshots and rollback."""

    def __init__(self, max_versions: int = 50) -> None:
        self._versions: dict[str, list[PolicyVersion]] = {}  # policy_id -> versions
        self._max_versions = max_versions

    def create_snapshot(
        self,
        policy: AdvancedPolicyDefinition,
        changelog: str = "",
        created_by: str = "",
    ) -> PolicyVersion:
        """Create a version snapshot of the current policy state."""
        snapshot = PolicyVersion(
            policy_id=policy.policy_id,
            version=policy.version,
            policy_snapshot=policy.model_copy(deep=True),
            changelog=changelog,
            created_by=created_by,
        )

        if policy.policy_id not in self._versions:
            self._versions[policy.policy_id] = []

        versions = self._versions[policy.policy_id]
        versions.append(snapshot)

        # Enforce max versions
        if len(versions) > self._max_versions:
            self._versions[policy.policy_id] = versions[-self._max_versions :]

        logger.info(
            "version_snapshot_created",
            policy_id=policy.policy_id,
            version=policy.version,
        )
        return snapshot

    def get_versions(self, policy_id: str) -> list[PolicyVersion]:
        return self._versions.get(policy_id, [])

    def get_version(self, policy_id: str, version: str) -> PolicyVersion:
        for v in self._versions.get(policy_id, []):
            if v.version == version:
                return v
        raise PolicyVersionError(f"Version '{version}' not found for policy {policy_id}")

    def get_latest(self, policy_id: str) -> PolicyVersion | None:
        versions = self._versions.get(policy_id, [])
        return versions[-1] if versions else None

    def rollback(
        self,
        policy_id: str,
        target_version: str,
    ) -> AdvancedPolicyDefinition:
        """Rollback a policy to a previous version. Returns the restored policy."""
        pv = self.get_version(policy_id, target_version)
        restored = pv.policy_snapshot.model_copy(deep=True)
        # Bump the version to indicate a new version was created from rollback
        restored.version = self._bump_version(restored.version, "patch")
        restored.updated_at = datetime.now(UTC)
        logger.info(
            "version_rollback",
            policy_id=policy_id,
            from_version=pv.version,
            to_version=restored.version,
        )
        return restored

    def bump_version(
        self,
        policy: AdvancedPolicyDefinition,
        level: str = "patch",
    ) -> str:
        """Bump the policy version. Returns the new version string."""
        new_version = self._bump_version(policy.version, level)
        policy.version = new_version
        policy.updated_at = datetime.now(UTC)
        return new_version

    @staticmethod
    def _bump_version(current: str, level: str) -> str:
        parts = current.split(".")
        if len(parts) != 3:
            return "1.0.0"
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        if level == "major":
            return f"{major + 1}.0.0"
        if level == "minor":
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}"

    def count_versions(self, policy_id: str) -> int:
        return len(self._versions.get(policy_id, []))

    def clear(self, policy_id: str | None = None) -> None:
        if policy_id:
            self._versions.pop(policy_id, None)
        else:
            self._versions.clear()
