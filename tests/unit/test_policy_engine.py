"""Tests for the Advanced Policy Engine — main orchestrator integration."""

import os
import tempfile

import pytest

from q_guardian.policy.config import PolicyEngineConfig
from q_guardian.policy.data import AdvancedPolicyDefinition, AdvancedRule, Condition
from q_guardian.policy.engine import AdvancedPolicyEngine
from q_guardian.policy.enums import (
    ComparisonOperator,
    DSLFormat,
    Permission,
)
from q_guardian.policy.events import (
    PolicyEvaluated,
    PolicyRegistered,
)
from q_guardian.policy.exceptions import (
    PolicyConflictError,
    PolicyNotFoundError,
)


def _policy(name: str = "test-policy", **kwargs) -> AdvancedPolicyDefinition:
    return AdvancedPolicyDefinition(
        name=name,
        rules=[
            AdvancedRule(
                name=f"{name}-block",
                condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.8),
                action="block",
                severity="high",
            ),
            AdvancedRule(
                name=f"{name}-warn",
                condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                action="warn",
                severity="medium",
            ),
        ],
        default_action="allow",
        default_severity="low",
        **kwargs,
    )


class TestAdvancedPolicyEngine:
    def test_register_and_evaluate(self):
        engine = AdvancedPolicyEngine()
        policy = _policy()
        engine.register_policy(policy)
        engine.activate_policy(policy.policy_id)
        result = engine.evaluate({"score": 0.9})
        assert result.action == "block"

    def test_evaluate_default_action(self):
        engine = AdvancedPolicyEngine()
        policy = _policy()
        engine.register_policy(policy)
        engine.activate_policy(policy.policy_id)
        result = engine.evaluate({"score": 0.3})
        assert result.action == "allow"

    def test_evaluate_specific_policy(self):
        engine = AdvancedPolicyEngine()
        p1 = _policy("p1")
        p2 = _policy("p2")
        engine.register_policy(p1)
        engine.register_policy(p2)
        engine.activate_policy(p1.policy_id)
        engine.activate_policy(p2.policy_id)
        result = engine.evaluate({"score": 0.9}, policy_id=p1.policy_id)
        assert result.policy_name == "p1"

    def test_evaluate_no_active_policies_raises(self):
        engine = AdvancedPolicyEngine()
        with pytest.raises(PolicyNotFoundError):
            engine.evaluate({"score": 0.9})

    def test_activate_deactivate(self):
        engine = AdvancedPolicyEngine()
        policy = _policy()
        engine.register_policy(policy)
        engine.activate_policy(policy.policy_id)
        assert policy.policy_id in [p.policy_id for p in engine.list_active_policies()]
        engine.deactivate_policy(policy.policy_id)
        assert policy.policy_id not in [p.policy_id for p in engine.list_active_policies()]

    def test_list_policies(self):
        engine = AdvancedPolicyEngine()
        engine.register_policy(_policy("p1"))
        engine.register_policy(_policy("p2"))
        assert len(engine.list_policies()) == 2

    def test_update_policy(self):
        engine = AdvancedPolicyEngine()
        policy = _policy()
        engine.register_policy(policy)
        policy.description = "updated"
        engine.update_policy(policy, changelog="Updated description")
        loaded = engine.get_policy(policy.policy_id)
        assert loaded.description == "updated"

    def test_simulation(self):
        engine = AdvancedPolicyEngine()
        policy = _policy()
        engine.register_policy(policy)
        result = engine.simulate(policy.policy_id, {"score": 0.9})
        assert result.action == "block"
        assert result.would_execute is True

    def test_simulation_disabled(self):
        config = PolicyEngineConfig(enable_simulation=False)
        engine = AdvancedPolicyEngine(config=config)
        policy = _policy()
        engine.register_policy(policy)
        from q_guardian.policy.exceptions import PolicyEngineError

        with pytest.raises(PolicyEngineError):
            engine.simulate(policy.policy_id, {"score": 0.9})

    def test_simulate_batch(self):
        engine = AdvancedPolicyEngine()
        policy = _policy()
        engine.register_policy(policy)
        results = engine.simulate_batch(policy.policy_id, [{"score": 0.9}, {"score": 0.3}])
        assert len(results) == 2

    def test_conflict_detection(self):
        engine = AdvancedPolicyEngine()
        p1 = _policy("p1")
        engine.register_policy(p1)
        # p2 has same rules with different actions -> conflicts
        p2 = AdvancedPolicyDefinition(
            name="p2",
            rules=[
                AdvancedRule(
                    name="r1",
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.8),
                    action="allow",  # contradicts p1's "block"
                )
            ],
        )
        engine.register_policy(p2)
        conflicts = engine.detect_conflicts(p1.policy_id, p2.policy_id)
        assert len(conflicts) > 0

    def test_internal_conflicts(self):
        engine = AdvancedPolicyEngine()
        policy = AdvancedPolicyDefinition(
            name="self-conflict",
            rules=[
                AdvancedRule(
                    name="r1",
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                    action="block",
                ),
                AdvancedRule(
                    name="r2",
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                    action="allow",
                ),
            ],
        )
        engine.register_policy(policy)
        conflicts = engine.detect_internal_conflicts(policy.policy_id)
        assert len(conflicts) > 0

    def test_versioning(self):
        engine = AdvancedPolicyEngine()
        policy = _policy()
        engine.register_policy(policy)
        engine.update_policy(policy, changelog="v2", bump="minor")
        versions = engine.get_versions(policy.policy_id)
        assert len(versions) >= 2

    def test_rollback(self):
        engine = AdvancedPolicyEngine()
        policy = _policy()
        engine.register_policy(policy)
        v1_version = policy.version
        engine.update_policy(policy, changelog="v2", bump="minor")
        restored = engine.rollback(policy.policy_id, v1_version)
        assert restored.name == "test-policy"

    def test_import_from_json(self):
        engine = AdvancedPolicyEngine()
        data = {
            "name": "imported",
            "rules": [
                {
                    "name": "import-rule",
                    "action": "block",
                    "field": "score",
                    "operator": ">",
                    "value": 0.5,
                }
            ],
        }
        import json

        policy = engine.import_from_dsl(json.dumps(data), DSLFormat.JSON)
        assert policy.name == "imported"

    def test_import_from_yaml(self):
        engine = AdvancedPolicyEngine()
        yaml = """name: yaml-policy
description: Imported
default_action: allow
rules:
  - name: block-high
    action: block
    severity: high
    priority: 1
    field: score
    operator: ">"
    value: "0.5"
"""
        policy = engine.import_from_dsl(yaml, DSLFormat.YAML)
        assert policy.name == "yaml-policy"

    def test_export_to_json(self):
        engine = AdvancedPolicyEngine()
        policy = _policy("export-test")
        engine.register_policy(policy)
        result = engine.export_to_dsl(policy.policy_id, DSLFormat.JSON)
        assert result.success is True
        import json

        data = json.loads(result.raw_source)
        assert data["name"] == "export-test"

    def test_export_nonexistent_raises(self):
        engine = AdvancedPolicyEngine()
        with pytest.raises(PolicyNotFoundError):
            engine.export_to_dsl("nonexistent", DSLFormat.JSON)

    def test_rbac_init(self):
        engine = AdvancedPolicyEngine(PolicyEngineConfig(enable_rbac=True))
        engine.init_rbac()
        assert engine.rbac is not None
        assert engine.check_permission("user1", Permission.POLICY_READ) is True

    def test_composition_init(self):
        engine = AdvancedPolicyEngine()
        engine.init_composition()
        assert engine.composer is not None

    def test_parse_condition(self):
        c = AdvancedPolicyEngine.parse_condition("score >= 0.8 AND confidence > 0.5")
        assert c is not None

    def test_events_tracked(self):
        engine = AdvancedPolicyEngine()
        policy = _policy()
        engine.register_policy(policy)
        engine.activate_policy(policy.policy_id)
        engine.evaluate({"score": 0.9})
        events = engine.get_events()
        assert any(isinstance(e, PolicyRegistered) for e in events)
        assert any(isinstance(e, PolicyEvaluated) for e in events)

    def test_clear_events(self):
        engine = AdvancedPolicyEngine()
        engine.register_policy(_policy())
        engine.clear_events()
        assert len(engine.get_events()) == 0

    def test_config_exposed(self):
        config = PolicyEngineConfig(evaluation_timeout_seconds=10.0)
        engine = AdvancedPolicyEngine(config=config)
        assert engine.config.evaluation_timeout_seconds == 10.0

    def test_registry_exposed(self):
        engine = AdvancedPolicyEngine()
        assert engine.registry is not None

    def test_evaluator_exposed(self):
        engine = AdvancedPolicyEngine()
        assert engine.evaluator is not None

    def test_evaluate_all(self):
        engine = AdvancedPolicyEngine()
        p1 = _policy("p1")
        p2 = _policy("p2")
        engine.register_policy(p1)
        engine.register_policy(p2)
        engine.activate_policy(p1.policy_id)
        engine.activate_policy(p2.policy_id)
        results = engine.evaluate_all({"score": 0.9})
        assert len(results) == 2

    def test_auto_conflict_detection_blocked(self):
        config = PolicyEngineConfig(allow_overlapping_rules=False)
        engine = AdvancedPolicyEngine(config=config)
        p1 = AdvancedPolicyDefinition(
            name="p1",
            rules=[
                AdvancedRule(
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                    action="block",
                )
            ],
        )
        engine.register_policy(p1)
        p2 = AdvancedPolicyDefinition(
            name="p2",
            rules=[
                AdvancedRule(
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                    action="allow",
                )
            ],
        )
        with pytest.raises(PolicyConflictError):
            engine.register_policy(p2)

    def test_conflict_events_emitted(self):
        engine = AdvancedPolicyEngine()
        p1 = AdvancedPolicyDefinition(
            name="p1",
            rules=[
                AdvancedRule(
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                    action="block",
                )
            ],
        )
        engine.register_policy(p1)
        p2 = AdvancedPolicyDefinition(
            name="p2",
            rules=[
                AdvancedRule(
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                    action="allow",
                )
            ],
        )
        engine.register_policy(p2)
        from q_guardian.policy.events import PolicyConflictDetected

        assert any(isinstance(e, PolicyConflictDetected) for e in engine.get_events())


class TestAdvancedPolicyEngineWithPersistence:
    def test_persist_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "engine_store.json")
            config = PolicyEngineConfig(persist_to_file=True, storage_path=path)
            engine = AdvancedPolicyEngine(config=config)
            engine.register_policy(_policy("persisted"))
            del engine

            engine2 = AdvancedPolicyEngine(config=config)
            assert engine2.registry.count() == 1


class TestAdvancedPolicyEngineIntegration:
    def test_full_lifecycle(self):
        """Test a complete lifecycle: register -> evaluate -> simulate -> version -> export."""
        engine = AdvancedPolicyEngine()

        # Create policy
        policy = AdvancedPolicyDefinition(
            name="lifecycle-test",
            description="Full lifecycle test",
            rules=[
                AdvancedRule(
                    name="block-critical",
                    condition=AdvancedPolicyEngine.parse_condition(
                        "risk_score >= 0.9 AND threat_level == critical"
                    ),
                    action="block",
                    severity="critical",
                    priority=1,
                ),
                AdvancedRule(
                    name="warn-high",
                    condition=AdvancedPolicyEngine.parse_condition("risk_score >= 0.7"),
                    action="warn",
                    severity="high",
                    priority=5,
                ),
            ],
            default_action="allow",
        )

        # Register
        engine.register_policy(policy, created_by="admin")
        engine.activate_policy(policy.policy_id)

        # Evaluate - should block
        result = engine.evaluate({"risk_score": 0.95, "threat_level": "critical"})
        assert result.action == "block"

        # Evaluate - should warn
        result2 = engine.evaluate({"risk_score": 0.8, "threat_level": "low"})
        assert result2.action == "warn"

        # Evaluate - default allow
        result3 = engine.evaluate({"risk_score": 0.3})
        assert result3.action == "allow"

        # Simulate
        sim = engine.simulate(policy.policy_id, {"risk_score": 0.95, "threat_level": "critical"})
        assert sim.action == "block"

        # Version
        engine.update_policy(policy, changelog="Updated rules", bump="minor")
        versions = engine.get_versions(policy.policy_id)
        assert len(versions) >= 2

        # Export
        export = engine.export_to_dsl(policy.policy_id, DSLFormat.JSON)
        assert export.success is True

        # Events
        events = engine.get_events()
        assert len(events) > 0
