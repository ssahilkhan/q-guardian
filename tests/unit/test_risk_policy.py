"""Tests for PolicyRegistry, PolicyEvaluator, PolicyEngine, and built-in policies."""

import pytest
from q_guardian.risk.policy.policy_registry import PolicyRegistry
from q_guardian.risk.policy.evaluator import PolicyEvaluator
from q_guardian.risk.policy.policy_engine import PolicyEngine
from q_guardian.risk.policy.policies import (
    create_default_policy, create_strict_policy,
    create_permissive_policy, create_quarantine_policy,
)
from q_guardian.risk.data import PolicyDefinition, PolicyRule, RiskAssessment
from q_guardian.risk.enums import (
    PolicyAction, PolicySeverity, DecisionOutcome, RiskLevel, Severity,
)
from q_guardian.risk.exceptions import PolicyNotFoundError


class TestPolicyRegistry:
    def test_register_policy(self):
        reg = PolicyRegistry()
        p = PolicyDefinition(name="test", rules=[])
        reg.register(p)
        assert reg.count == 1

    def test_register_duplicate_raises(self):
        reg = PolicyRegistry()
        p = PolicyDefinition(name="test", rules=[])
        reg.register(p)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(p)

    def test_unregister(self):
        reg = PolicyRegistry()
        p = PolicyDefinition(name="test", rules=[])
        reg.register(p)
        assert reg.unregister("test") is True
        assert reg.count == 0

    def test_unregister_nonexistent(self):
        reg = PolicyRegistry()
        assert reg.unregister("nope") is False

    def test_get_policy(self):
        reg = PolicyRegistry()
        p = PolicyDefinition(name="test", rules=[])
        reg.register(p)
        got = reg.get("test")
        assert got.name == "test"

    def test_get_nonexistent_raises(self):
        reg = PolicyRegistry()
        with pytest.raises(PolicyNotFoundError):
            reg.get("missing")

    def test_has_policy(self):
        reg = PolicyRegistry()
        p = PolicyDefinition(name="test", rules=[])
        reg.register(p)
        assert reg.has("test") is True
        assert reg.has("nope") is False

    def test_list_policies(self):
        reg = PolicyRegistry()
        reg.register(PolicyDefinition(name="a", rules=[]))
        reg.register(PolicyDefinition(name="b", rules=[]))
        assert len(reg.list_policies()) == 2

    def test_list_enabled(self):
        reg = PolicyRegistry()
        reg.register(PolicyDefinition(name="a", rules=[], enabled=True))
        reg.register(PolicyDefinition(name="b", rules=[], enabled=False))
        assert len(reg.list_enabled()) == 1

    def test_enable_disable(self):
        reg = PolicyRegistry()
        reg.register(PolicyDefinition(name="a", rules=[], enabled=True))
        reg.disable("a")
        assert len(reg.list_enabled()) == 0
        reg.enable("a")
        assert len(reg.list_enabled()) == 1

    def test_update_policy(self):
        reg = PolicyRegistry()
        p = PolicyDefinition(name="test", rules=[], version="1.0.0")
        reg.register(p)
        p2 = PolicyDefinition(name="test", rules=[], version="2.0.0")
        reg.update(p2)
        assert reg.get("test").version == "2.0.0"


class TestPolicyEvaluator:
    def test_evaluate_default_no_match(self):
        evaluator = PolicyEvaluator()
        policy = create_default_policy()
        assessment = RiskAssessment(risk_score=0.01, risk_level=RiskLevel.MINIMAL)
        decision = evaluator.evaluate(policy, assessment)
        assert decision.outcome == DecisionOutcome.ALLOWED

    def test_evaluate_critical_blocks(self):
        evaluator = PolicyEvaluator()
        policy = create_default_policy()
        assessment = RiskAssessment(risk_score=0.95, risk_level=RiskLevel.CRITICAL)
        decision = evaluator.evaluate(policy, assessment)
        assert decision.outcome == DecisionOutcome.BLOCKED
        assert decision.action == PolicyAction.BLOCK

    def test_evaluate_severe_escalates(self):
        evaluator = PolicyEvaluator()
        policy = create_default_policy()
        assessment = RiskAssessment(risk_score=0.8, risk_level=RiskLevel.SEVERE)
        decision = evaluator.evaluate(policy, assessment)
        assert decision.outcome == DecisionOutcome.ESCALATED

    def test_evaluate_high_reviews(self):
        evaluator = PolicyEvaluator()
        policy = create_default_policy()
        assessment = RiskAssessment(risk_score=0.6, risk_level=RiskLevel.HIGH)
        decision = evaluator.evaluate(policy, assessment)
        assert decision.outcome == DecisionOutcome.PENDING_REVIEW

    def test_evaluate_moderate_warns(self):
        evaluator = PolicyEvaluator()
        policy = create_default_policy()
        assessment = RiskAssessment(risk_score=0.45, risk_level=RiskLevel.MODERATE)
        decision = evaluator.evaluate(policy, assessment)
        assert decision.outcome == DecisionOutcome.WARNED

    def test_evaluate_low_logs(self):
        evaluator = PolicyEvaluator()
        policy = create_default_policy()
        assessment = RiskAssessment(risk_score=0.15, risk_level=RiskLevel.LOW)
        decision = evaluator.evaluate(policy, assessment)
        assert decision.outcome == DecisionOutcome.LOGGED

    def test_evaluate_has_matched_rules(self):
        evaluator = PolicyEvaluator()
        policy = create_default_policy()
        assessment = RiskAssessment(risk_score=0.95, risk_level=RiskLevel.CRITICAL)
        decision = evaluator.evaluate(policy, assessment)
        assert len(decision.matched_rules) > 0

    def test_evaluate_has_reasoning(self):
        evaluator = PolicyEvaluator()
        policy = create_default_policy()
        assessment = RiskAssessment(risk_score=0.5)
        decision = evaluator.evaluate(policy, assessment)
        assert len(decision.reasoning) > 0

    def test_evaluate_custom_policy(self):
        evaluator = PolicyEvaluator()
        policy = PolicyDefinition(
            name="custom",
            rules=[
                PolicyRule(
                    condition="risk_score >= 0.5",
                    action=PolicyAction.WARN,
                    severity=PolicySeverity.MEDIUM,
                    priority=0,
                ),
            ],
        )
        assessment = RiskAssessment(risk_score=0.6)
        decision = evaluator.evaluate(policy, assessment)
        assert decision.action == PolicyAction.WARN

    def test_evaluate_disabled_rule_skipped(self):
        evaluator = PolicyEvaluator()
        policy = PolicyDefinition(
            name="test",
            rules=[
                PolicyRule(
                    condition="risk_score >= 0.0",
                    action=PolicyAction.BLOCK,
                    enabled=False,
                ),
            ],
            default_action=PolicyAction.ALLOW,
        )
        assessment = RiskAssessment(risk_score=0.99)
        decision = evaluator.evaluate(policy, assessment)
        assert decision.outcome == DecisionOutcome.ALLOWED


class TestBuiltinPolicies:
    def test_default_policy(self):
        p = create_default_policy()
        assert p.name == "default-security"
        assert len(p.rules) == 5
        assert p.default_action == PolicyAction.ALLOW

    def test_strict_policy(self):
        p = create_strict_policy()
        assert p.name == "strict-security"
        assert p.default_action == PolicyAction.WARN

    def test_permissive_policy(self):
        p = create_permissive_policy()
        assert p.name == "permissive-security"
        assert p.default_action == PolicyAction.ALLOW

    def test_quarantine_policy(self):
        p = create_quarantine_policy()
        assert p.name == "quarantine-security"
        assert p.default_action == PolicyAction.ALLOW


class TestPolicyEngine:
    def test_load_defaults(self):
        engine = PolicyEngine()
        engine.load_defaults()
        assert engine.registry.count == 4

    def test_evaluate_default(self):
        engine = PolicyEngine()
        engine.load_defaults()
        assessment = RiskAssessment(risk_score=0.95, risk_level=RiskLevel.CRITICAL)
        decision = engine.evaluate(assessment)
        assert decision.outcome == DecisionOutcome.BLOCKED

    def test_evaluate_specific_policy(self):
        engine = PolicyEngine()
        engine.load_defaults()
        assessment = RiskAssessment(risk_score=0.95, risk_level=RiskLevel.CRITICAL)
        decision = engine.evaluate(assessment, policy_name="strict-security")
        assert decision.outcome == DecisionOutcome.BLOCKED

    def test_evaluate_count(self):
        engine = PolicyEngine()
        engine.load_defaults()
        assessment = RiskAssessment(risk_score=0.5)
        engine.evaluate(assessment)
        engine.evaluate(assessment)
        assert engine.evaluation_count == 2

    def test_evaluate_permissive(self):
        engine = PolicyEngine()
        engine.load_defaults()
        assessment = RiskAssessment(risk_score=0.95, risk_level=RiskLevel.CRITICAL)
        decision = engine.evaluate(assessment, policy_name="permissive-security")
        assert decision.outcome == DecisionOutcome.BLOCKED

    def test_evaluate_quarantine(self):
        engine = PolicyEngine()
        engine.load_defaults()
        assessment = RiskAssessment(risk_score=0.95, risk_level=RiskLevel.CRITICAL)
        decision = engine.evaluate(assessment, policy_name="quarantine-security")
        assert decision.action == PolicyAction.QUARANTINE
