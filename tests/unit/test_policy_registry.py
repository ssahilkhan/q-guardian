"""Tests for the Policy Registry."""

import pytest
import tempfile
import os

from q_guardian.policy.core.registry import PolicyRegistry
from q_guardian.policy.data import AdvancedPolicyDefinition, AdvancedRule, Condition
from q_guardian.policy.enums import ComparisonOperator, PolicyStatus
from q_guardian.policy.exceptions import PolicyNotFoundError


def _make_policy(name: str = "test-policy", **kwargs) -> AdvancedPolicyDefinition:
    return AdvancedPolicyDefinition(
        name=name,
        rules=[
            AdvancedRule(
                name=f"{name}-rule",
                condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                action="block",
            )
        ],
        **kwargs,
    )


class TestRegistry:
    def test_register_and_get(self):
        reg = PolicyRegistry()
        policy = _make_policy("p1")
        reg.register(policy)
        assert reg.get(policy.policy_id).name == "p1"

    def test_register_duplicate_raises(self):
        reg = PolicyRegistry()
        policy = _make_policy("p1")
        reg.register(policy)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(policy)

    def test_unregister(self):
        reg = PolicyRegistry()
        policy = _make_policy("p1")
        reg.register(policy)
        assert reg.unregister(policy.policy_id) is True
        assert reg.has(policy.policy_id) is False

    def test_unregister_nonexistent(self):
        reg = PolicyRegistry()
        assert reg.unregister("nonexistent") is False

    def test_get_nonexistent_raises(self):
        reg = PolicyRegistry()
        with pytest.raises(PolicyNotFoundError):
            reg.get("nonexistent")

    def test_get_by_name(self):
        reg = PolicyRegistry()
        policy = _make_policy("unique-name")
        reg.register(policy)
        found = reg.get_by_name("unique-name")
        assert found is not None
        assert found.name == "unique-name"

    def test_get_by_name_not_found(self):
        reg = PolicyRegistry()
        assert reg.get_by_name("nonexistent") is None

    def test_list_policies(self):
        reg = PolicyRegistry()
        reg.register(_make_policy("p1"))
        reg.register(_make_policy("p2"))
        assert len(reg.list_policies()) == 2

    def test_list_by_status(self):
        reg = PolicyRegistry()
        reg.register(_make_policy("p1", status=PolicyStatus.ACTIVE))
        reg.register(_make_policy("p2", status=PolicyStatus.DRAFT))
        assert len(reg.list_by_status(PolicyStatus.ACTIVE)) == 1
        assert len(reg.list_by_status(PolicyStatus.DRAFT)) == 1

    def test_list_active(self):
        reg = PolicyRegistry()
        reg.register(_make_policy("p1", status=PolicyStatus.ACTIVE))
        reg.register(_make_policy("p2", status=PolicyStatus.DRAFT))
        assert len(reg.list_active()) == 1

    def test_activate_deactivate(self):
        reg = PolicyRegistry()
        policy = _make_policy("p1")
        reg.register(policy)
        reg.activate(policy.policy_id)
        assert reg.get(policy.policy_id).status == PolicyStatus.ACTIVE
        reg.deactivate(policy.policy_id)
        assert reg.get(policy.policy_id).status == PolicyStatus.SUSPENDED

    def test_activate_nonexistent_raises(self):
        reg = PolicyRegistry()
        with pytest.raises(PolicyNotFoundError):
            reg.activate("nonexistent")

    def test_update(self):
        reg = PolicyRegistry()
        policy = _make_policy("p1")
        reg.register(policy)
        policy.description = "updated"
        reg.update(policy)
        assert reg.get(policy.policy_id).description == "updated"

    def test_count(self):
        reg = PolicyRegistry()
        assert reg.count() == 0
        reg.register(_make_policy("p1"))
        assert reg.count() == 1

    def test_clear(self):
        reg = PolicyRegistry()
        reg.register(_make_policy("p1"))
        reg.register(_make_policy("p2"))
        reg.clear()
        assert reg.count() == 0

    def test_has(self):
        reg = PolicyRegistry()
        policy = _make_policy("p1")
        assert reg.has(policy.policy_id) is False
        reg.register(policy)
        assert reg.has(policy.policy_id) is True


class TestRegistryPersistence:
    def test_persist_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_policies.json")
            reg1 = PolicyRegistry(storage_path=path)
            policy = _make_policy("persistent-policy")
            reg1.register(policy)
            del reg1

            reg2 = PolicyRegistry(storage_path=path)
            assert reg2.count() == 1
            assert reg2.get_by_name("persistent-policy") is not None

    def test_load_nonexistent_file(self):
        reg = PolicyRegistry(storage_path="/nonexistent/path/policies.json")
        assert reg.count() == 0

    def test_persist_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.json")
            reg = PolicyRegistry(storage_path=path)
            reg.register(_make_policy("p1"))
            reg.clear()
            reg2 = PolicyRegistry(storage_path=path)
            assert reg2.count() == 0
