"""Tests for the Policy Evaluator."""

import pytest

from q_guardian.policy.core.evaluator import PolicyEvaluator
from q_guardian.policy.data import AdvancedPolicyDefinition, AdvancedRule, Condition, CompoundCondition
from q_guardian.policy.enums import ComparisonOperator, LogicalOperator


def _make_policy(
    name: str = "test",
    rules: list | None = None,
    default_action: str = "allow",
    default_severity: str = "low",
) -> AdvancedPolicyDefinition:
    return AdvancedPolicyDefinition(
        name=name,
        rules=rules or [],
        default_action=default_action,
        default_severity=default_severity,
    )


class TestPolicyEvaluator:
    def test_no_rules_returns_default(self):
        evaluator = PolicyEvaluator()
        policy = _make_policy(default_action="allow")
        result = evaluator.evaluate(policy, {"risk_score": 0.9})
        assert result.action == "allow"
        assert result.severity == "low"
        assert result.matched_rules == []

    def test_single_rule_match(self):
        rule = AdvancedRule(
            name="high-risk",
            condition=Condition(field="risk_score", operator=ComparisonOperator.GTE, value=0.8),
            action="block",
            severity="high",
            priority=1,
        )
        evaluator = PolicyEvaluator()
        policy = _make_policy(rules=[rule])
        result = evaluator.evaluate(policy, {"risk_score": 0.9})
        assert result.action == "block"
        assert "high-risk" in result.reasoning[0] or rule.rule_id in result.matched_rules

    def test_single_rule_no_match(self):
        rule = AdvancedRule(
            condition=Condition(field="risk_score", operator=ComparisonOperator.GTE, value=0.8),
            action="block",
        )
        evaluator = PolicyEvaluator()
        policy = _make_policy(rules=[rule])
        result = evaluator.evaluate(policy, {"risk_score": 0.5})
        assert result.action == "allow"

    def test_priority_wins(self):
        high_pri = AdvancedRule(
            name="high-pri",
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="block",
            priority=1,
        )
        low_pri = AdvancedRule(
            name="low-pri",
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.3),
            action="warn",
            priority=10,
        )
        evaluator = PolicyEvaluator()
        policy = _make_policy(rules=[low_pri, high_pri])
        result = evaluator.evaluate(policy, {"score": 0.9})
        assert result.action == "block"

    def test_multiple_matches_all_tracked(self):
        r1 = AdvancedRule(
            name="r1",
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.3),
            action="log",
            priority=10,
        )
        r2 = AdvancedRule(
            name="r2",
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="warn",
            priority=5,
        )
        r3 = AdvancedRule(
            name="r3",
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.8),
            action="block",
            priority=1,
        )
        evaluator = PolicyEvaluator()
        policy = _make_policy(rules=[r1, r2, r3])
        result = evaluator.evaluate(policy, {"score": 0.9})
        assert result.action == "block"
        assert len(result.all_matching_rules) == 3

    def test_disabled_rule_skipped(self):
        rule = AdvancedRule(
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="block",
            enabled=False,
        )
        evaluator = PolicyEvaluator()
        policy = _make_policy(rules=[rule])
        result = evaluator.evaluate(policy, {"score": 0.9})
        assert result.action == "allow"

    def test_compound_condition(self):
        rule = AdvancedRule(
            condition=CompoundCondition(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                    Condition(field="confidence", operator=ComparisonOperator.LT, value=0.3),
                ],
            ),
            action="block",
        )
        evaluator = PolicyEvaluator()
        policy = _make_policy(rules=[rule])
        result = evaluator.evaluate(policy, {"score": 0.8, "confidence": 0.2})
        assert result.action == "block"
        result2 = evaluator.evaluate(policy, {"score": 0.8, "confidence": 0.7})
        assert result2.action == "allow"

    def test_action_params(self):
        rule = AdvancedRule(
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="webhook",
            action_params={"url": "https://example.com"},
        )
        evaluator = PolicyEvaluator()
        policy = _make_policy(rules=[rule])
        result = evaluator.evaluate(policy, {"score": 0.8})
        assert result.action_params["url"] == "https://example.com"

    def test_execution_time_tracked(self):
        evaluator = PolicyEvaluator()
        policy = _make_policy()
        result = evaluator.evaluate(policy, {})
        assert result.execution_time_ms >= 0

    def test_context_in_result(self):
        evaluator = PolicyEvaluator()
        policy = _make_policy()
        ctx = {"risk_score": 0.9, "source": "test"}
        result = evaluator.evaluate(policy, ctx)
        assert result.context == ctx

    def test_policy_version_in_result(self):
        evaluator = PolicyEvaluator()
        policy = _make_policy()
        policy.version = "2.1.0"
        result = evaluator.evaluate(policy, {})
        assert result.policy_version == "2.1.0"

    def test_evaluate_rules_directly(self):
        evaluator = PolicyEvaluator()
        rules = [
            AdvancedRule(
                condition=Condition(field="x", operator=ComparisonOperator.GT, value=5),
                action="block",
                priority=1,
            ),
            AdvancedRule(
                condition=Condition(field="x", operator=ComparisonOperator.GT, value=3),
                action="warn",
                priority=2,
            ),
        ]
        matching = evaluator.evaluate_rules(rules, {"x": 7})
        assert len(matching) == 2
