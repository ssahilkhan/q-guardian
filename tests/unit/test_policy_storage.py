"""Tests for Policy Storage."""

import pytest
import tempfile
import os

from q_guardian.policy.storage import PolicyStorage
from q_guardian.policy.data import AdvancedPolicyDefinition, AdvancedRule, Condition
from q_guardian.policy.enums import ComparisonOperator


def _policy(name: str = "test") -> AdvancedPolicyDefinition:
    return AdvancedPolicyDefinition(
        name=name,
        rules=[
            AdvancedRule(
                condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                action="block",
            )
        ],
    )


class TestPolicyStorage:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            policy = _policy("saved")
            storage.save(policy)
            loaded = storage.load(policy.policy_id)
            assert loaded is not None
            assert loaded.name == "saved"

    def test_save_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            policies = [_policy("p1"), _policy("p2")]
            storage.save_all(policies)
            assert storage.count() == 2

    def test_load_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            storage.save(_policy("p1"))
            storage.save(_policy("p2"))
            all_policies = storage.load_all()
            assert len(all_policies) == 2

    def test_load_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            assert storage.load("nonexistent") is None

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            policy = _policy("to-delete")
            storage.save(policy)
            assert storage.delete(policy.policy_id) is True
            assert storage.load(policy.policy_id) is None

    def test_delete_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            assert storage.delete("nonexistent") is False

    def test_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            policy = _policy("exists-test")
            assert storage.exists(policy.policy_id) is False
            storage.save(policy)
            assert storage.exists(policy.policy_id) is True

    def test_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            assert storage.count() == 0
            storage.save(_policy("p1"))
            assert storage.count() == 1

    def test_clear(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            storage.save(_policy("p1"))
            storage.clear()
            assert storage.count() == 0

    def test_persistence_across_instances(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage1 = PolicyStorage(path)
            storage1.save(_policy("persistent"))
            del storage1

            storage2 = PolicyStorage(path)
            assert storage2.count() == 1
            loaded = storage2.load_all()
            assert loaded[0].name == "persistent"

    def test_new_file(self):
        path = os.path.join(tempfile.mkdtemp(), "new_store.json")
        storage = PolicyStorage(path)
        assert storage.count() == 0

    def test_update_policy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.json")
            storage = PolicyStorage(path)
            policy = _policy("original")
            storage.save(policy)
            policy.name = "updated"
            storage.save(policy)
            loaded = storage.load(policy.policy_id)
            assert loaded.name == "updated"
