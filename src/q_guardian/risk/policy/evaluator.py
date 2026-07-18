"""PolicyEvaluator — evaluates a policy against a RiskAssessment.

Determines which rules match and produces a PolicyDecision.
"""

from __future__ import annotations

import operator
from typing import Any

import structlog

from q_guardian.risk.data import PolicyDecision, PolicyDefinition, PolicyRule, RiskAssessment
from q_guardian.risk.enums import DecisionOutcome, PolicyAction, PolicySeverity

logger = structlog.get_logger("risk.evaluator")

_COMPARISON_OPS: dict[str, Any] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}


class PolicyEvaluator:
    """Evaluates policy rules against risk assessments.

    Uses a simple condition language:
      - 'risk_score >= 0.9'
      - 'risk_level == critical'
      - 'severity == high'
    """

    def evaluate(
        self,
        policy: PolicyDefinition,
        assessment: RiskAssessment,
    ) -> PolicyDecision:
        """Evaluate a policy against a risk assessment.

        Args:
            policy: The policy to evaluate.
            assessment: The risk assessment to evaluate against.

        Returns:
            PolicyDecision with the matched outcome.
        """
        context = self._build_context(assessment)
        matched_rules: list[str] = []
        reasoning: list[str] = []
        best_match: PolicyRule | None = None

        sorted_rules = sorted(policy.rules, key=lambda r: r.priority)

        for rule in sorted_rules:
            if not rule.enabled:
                continue

            if self._evaluate_condition(rule.condition, context):
                matched_rules.append(rule.rule_id)
                reasoning.append(
                    f"Rule '{rule.rule_id}' matched: {rule.condition} -> {rule.action.value}"
                )

                if best_match is None or rule.priority < best_match.priority:
                    best_match = rule

        if best_match is not None:
            action = best_match.action
            severity = best_match.severity
            outcome = self._action_to_outcome(action)
            reasoning.append(f"Selected action: {action.value} (rule priority={best_match.priority})")
        else:
            action = policy.default_action
            severity = policy.default_severity
            outcome = self._action_to_outcome(action)
            reasoning.append(f"No rules matched, using default: {action.value}")

        decision = PolicyDecision(
            assessment_id=assessment.assessment_id,
            policy_id=policy.policy_id,
            policy_name=policy.name,
            outcome=outcome,
            action=action,
            severity=severity,
            risk_score=assessment.risk_score,
            matched_rules=matched_rules,
            reasoning=reasoning,
        )

        logger.info(
            "policy_evaluated",
            policy_name=policy.name,
            outcome=outcome.value,
            action=action.value,
            matched_rules=len(matched_rules),
        )

        return decision

    def _build_context(self, assessment: RiskAssessment) -> dict[str, Any]:
        """Build evaluation context from a risk assessment."""
        return {
            "risk_score": assessment.risk_score,
            "risk_level": assessment.risk_level.value,
            "severity": assessment.severity.severity.value,
            "confidence": assessment.confidence.normalized_confidence,
            "threat_score": assessment.threat_score.threat_score,
            "threat_level": assessment.threat_score.threat_level.value,
        }

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a condition string against a context.

        Supports simple expressions like:
          - 'risk_score >= 0.9'
          - 'risk_level == critical'
          - 'severity in [high, critical]'
        """
        condition = condition.strip()

        if " in [" in condition:
            return self._evaluate_in_condition(condition, context)

        for op_str, op_func in _COMPARISON_OPS.items():
            if op_str in condition:
                parts = condition.split(op_str, 1)
                if len(parts) == 2:
                    left_key = parts[0].strip()
                    right_str = parts[1].strip()

                    left_val = context.get(left_key)
                    if left_val is None:
                        return False

                    right_val = self._parse_value(right_str)
                    return op_func(left_val, right_val)

        return False

    def _evaluate_in_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate 'key in [val1, val2]' conditions."""
        parts = condition.split(" in ", 1)
        if len(parts) != 2:
            return False

        left_key = parts[0].strip()
        left_val = context.get(left_key)
        if left_val is None:
            return False

        values_str = parts[1].strip().strip("[]")
        values = [v.strip().strip("'\"") for v in values_str.split(",")]
        return str(left_val) in values

    @staticmethod
    def _parse_value(s: str) -> Any:
        """Parse a string value to appropriate Python type."""
        s = s.strip().strip("'\"")
        try:
            return float(s)
        except ValueError:
            return s

    @staticmethod
    def _action_to_outcome(action: PolicyAction) -> DecisionOutcome:
        """Map a PolicyAction to a DecisionOutcome."""
        mapping = {
            PolicyAction.ALLOW: DecisionOutcome.ALLOWED,
            PolicyAction.WARN: DecisionOutcome.WARNED,
            PolicyAction.LOG: DecisionOutcome.LOGGED,
            PolicyAction.REVIEW: DecisionOutcome.PENDING_REVIEW,
            PolicyAction.BLOCK: DecisionOutcome.BLOCKED,
            PolicyAction.QUARANTINE: DecisionOutcome.QUARANTINED,
            PolicyAction.TERMINATE_SESSION: DecisionOutcome.SESSION_TERMINATED,
            PolicyAction.ESCALATE: DecisionOutcome.ESCALATED,
            PolicyAction.CUSTOM: DecisionOutcome.CUSTOM_ACTION,
        }
        return mapping.get(action, DecisionOutcome.ALLOWED)
