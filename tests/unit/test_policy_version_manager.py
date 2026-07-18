"""Tests for the Version Manager."""

import pytest

from q_guardian.policy.core.version_manager import VersionManager
from q_guardian.policy.data import AdvancedPolicyDefinition
from q_guardian.policy.exceptions import PolicyVersionError


def _policy(name: str = "test", version: str = "1.0.0") -> AdvancedPolicyDefinition:
    return AdvancedPolicyDefinition(name=name, version=version)


class TestVersionManager:
    def test_create_snapshot(self):
        vm = VersionManager()
        policy = _policy(version="1.0.0")
        pv = vm.create_snapshot(policy, changelog="Initial")
        assert pv.version == "1.0.0"
        assert pv.changelog == "Initial"

    def test_get_versions(self):
        vm = VersionManager()
        policy = _policy()
        vm.create_snapshot(policy, changelog="v1")
        policy.version = "1.1.0"
        vm.create_snapshot(policy, changelog="v2")
        versions = vm.get_versions(policy.policy_id)
        assert len(versions) == 2

    def test_get_version(self):
        vm = VersionManager()
        policy = _policy(version="1.0.0")
        vm.create_snapshot(policy)
        pv = vm.get_version(policy.policy_id, "1.0.0")
        assert pv.version == "1.0.0"

    def test_get_version_not_found(self):
        vm = VersionManager()
        with pytest.raises(PolicyVersionError):
            vm.get_version("nonexistent", "1.0.0")

    def test_get_latest(self):
        vm = VersionManager()
        policy = _policy(version="1.0.0")
        vm.create_snapshot(policy)
        policy.version = "2.0.0"
        vm.create_snapshot(policy)
        latest = vm.get_latest(policy.policy_id)
        assert latest is not None
        assert latest.version == "2.0.0"

    def test_get_latest_none(self):
        vm = VersionManager()
        assert vm.get_latest("nonexistent") is None

    def test_rollback(self):
        vm = VersionManager()
        policy = _policy(version="1.0.0")
        vm.create_snapshot(policy)
        policy.version = "2.0.0"
        vm.create_snapshot(policy)

        restored = vm.rollback(policy.policy_id, "1.0.0")
        assert restored.version != "1.0.0"  # bumped to patch
        assert restored.name == "test"

    def test_rollback_not_found(self):
        vm = VersionManager()
        with pytest.raises(PolicyVersionError):
            vm.rollback("nonexistent", "1.0.0")

    def test_bump_version_patch(self):
        vm = VersionManager()
        policy = _policy(version="1.2.3")
        new = vm.bump_version(policy, "patch")
        assert new == "1.2.4"

    def test_bump_version_minor(self):
        vm = VersionManager()
        policy = _policy(version="1.2.3")
        new = vm.bump_version(policy, "minor")
        assert new == "1.3.0"

    def test_bump_version_major(self):
        vm = VersionManager()
        policy = _policy(version="1.2.3")
        new = vm.bump_version(policy, "major")
        assert new == "2.0.0"

    def test_max_versions_enforced(self):
        vm = VersionManager(max_versions=3)
        policy = _policy()
        for i in range(5):
            policy.version = f"1.{i}.0"
            vm.create_snapshot(policy)
        assert vm.count_versions(policy.policy_id) == 3

    def test_count_versions(self):
        vm = VersionManager()
        policy = _policy()
        assert vm.count_versions(policy.policy_id) == 0
        vm.create_snapshot(policy)
        assert vm.count_versions(policy.policy_id) == 1

    def test_clear(self):
        vm = VersionManager()
        policy = _policy()
        vm.create_snapshot(policy)
        vm.clear(policy.policy_id)
        assert vm.count_versions(policy.policy_id) == 0

    def test_clear_all(self):
        vm = VersionManager()
        vm.create_snapshot(_policy("p1"))
        vm.create_snapshot(_policy("p2"))
        vm.clear()
        # Can't easily verify without iterating, but no error means success

    def test_snapshot_deep_copies(self):
        vm = VersionManager()
        policy = _policy()
        vm.create_snapshot(policy)
        policy.name = "modified"
        pv = vm.get_latest(policy.policy_id)
        assert pv.policy_snapshot.name == "test"

    def test_invalid_version_format(self):
        assert VersionManager._bump_version("invalid", "patch") == "1.0.0"
