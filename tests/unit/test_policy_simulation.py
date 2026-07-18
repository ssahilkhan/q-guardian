"""Tests for the Simulation Engine."""

import pytest

from q_guardian.policy.core.simulation import SimulationEngine
from q_guardian.policy.core.evaluator import PolicyEvaluator
from q_guardian.policy.data import AdvancedPolicyDefinition, AdvancedRule, Condition
from q_guardian.policy.enums import ComparisonOperator


def _policy_with_rules() -> AdvancedPolicyDefinition:
    return AdvancedPolicyDefinition(
        name="sim-test",
        rules=[
            AdvancedRule(
                name="high-risk",
                condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.8),
                action="block",
                severity="high",
            ),
            AdvancedRule(
                name="medium-risk",
                condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                action="warn",
                severity="medium",
            ),
        ],
        default_action="allow",
    )


class TestSimulationEngine:
    def test_simulate_basic(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        result = engine.simulate(policy, {"score": 0.9})
        assert result.action == "block"
        assert result.policy_name == "sim-test"

    def test_simulate_no_match(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        result = engine.simulate(policy, {"score": 0.3})
        assert result.action == "allow"

    def test_simulate_records_history(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        engine.simulate(policy, {"score": 0.9})
        engine.simulate(policy, {"score": 0.3})
        assert len(engine.get_history()) == 2

    def test_simulate_batch(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        contexts = [{"score": 0.9}, {"score": 0.6}, {"score": 0.3}]
        results = engine.simulate_batch(policy, contexts)
        assert len(results) == 3
        assert results[0].action == "block"
        assert results[1].action == "warn"
        assert results[2].action == "allow"

    def test_simulate_with_overrides(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        result = engine.simulate_with_overrides(
            policy, {"score": 0.9}, override_action="log"
        )
        # Override action only affects default_action, not rule-matched actions
        assert result.action == "block"

    def test_simulate_with_disabled_rules(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        high_rule_id = policy.rules[0].rule_id
        result = engine.simulate_with_overrides(
            policy, {"score": 0.9}, disabled_rule_ids=[high_rule_id]
        )
        # High-risk rule disabled, medium-risk should match
        assert result.action == "warn"

    def test_replay(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        engine.simulate(policy, {"score": 0.9})
        engine.simulate(policy, {"score": 0.3})
        replay_results = engine.replay(policy)
        assert len(replay_results) == 2

    def test_replay_filtered(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        r1 = engine.simulate(policy, {"score": 0.9})
        r2 = engine.simulate(policy, {"score": 0.3})
        replay_results = engine.replay(policy, simulation_ids=[r1.simulation_id])
        assert len(replay_results) == 1

    def test_clear_history(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        engine.simulate(policy, {"score": 0.9})
        engine.clear_history()
        assert len(engine.get_history()) == 0

    def test_compare_policies(self):
        engine = SimulationEngine()
        p1 = AdvancedPolicyDefinition(
            name="strict",
            rules=[
                AdvancedRule(
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                    action="block",
                )
            ],
        )
        p2 = AdvancedPolicyDefinition(
            name="permissive",
            rules=[
                AdvancedRule(
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.8),
                    action="warn",
                )
            ],
        )
        comparison = engine.compare_policies(p1, p2, {"score": 0.9})
        assert comparison["policy_a"]["action"] == "block"
        assert comparison["policy_b"]["action"] == "warn"
        assert comparison["same_action"] is False

    def test_compare_same_action(self):
        engine = SimulationEngine()
        p1 = AdvancedPolicyDefinition(name="a", rules=[
            AdvancedRule(
                condition=Condition(field="x", operator=ComparisonOperator.GT, value=0.5),
                action="block",
            )
        ])
        p2 = AdvancedPolicyDefinition(name="b", rules=[
            AdvancedRule(
                condition=Condition(field="y", operator=ComparisonOperator.GT, value=0.5),
                action="block",
            )
        ])
        comparison = engine.compare_policies(p1, p2, {"x": 0.9, "y": 0.9})
        assert comparison["same_action"] is True

    def test_simulate_tracks_metadata(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        result = engine.simulate(policy, {"score": 0.9})
        assert result.would_execute is True
        assert result.execution_time_ms >= 0

    def test_simulate_context_captured(self):
        engine = SimulationEngine()
        policy = _policy_with_rules()
        ctx = {"score": 0.9, "source": "test"}
        result = engine.simulate(policy, ctx)
        assert result.input_context == ctx
