"""Advanced Policy Evaluator — evaluates policies against contexts with full condition support."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import structlog

from q_guardian.policy.data import (
    AdvancedPolicyDefinition,
    AdvancedRule,
    PolicyEvaluationResult,
)

logger = structlog.get_logger(__name__)


class PolicyEvaluator:
    """Evaluates advanced policies with rich condition support.

    Unlike the simple first-match evaluator in risk/policy, this evaluator:
    - Collects ALL matching rules (not just first match)
    - Supports action parameters
    - Respects temporal validity windows
    - Tracks detailed reasoning
    """

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self._timeout_seconds = timeout_seconds

    def evaluate(
        self,
        policy: AdvancedPolicyDefinition,
        context: dict[str, Any],
    ) -> PolicyEvaluationResult:
        """Evaluate a policy against a context dict.

        Returns a PolicyEvaluationResult with all matching rules,
        the winning action, and reasoning steps.
        """
        start = time.monotonic()
        reasoning: list[str] = []
        all_matching: list[str] = []
        winning_rule: AdvancedRule | None = None

        reasoning.append(f"Evaluating policy '{policy.name}' (v{policy.version})")
        reasoning.append(f"Context keys: {list(context.keys())}")

        enabled_rules = policy.enabled_rules()
        reasoning.append(f"Enabled rules: {len(enabled_rules)}")

        # Sort by priority (ascending = highest priority first)
        sorted_rules = sorted(enabled_rules, key=lambda r: r.priority)

        for rule in sorted_rules:
            try:
                matched = rule.evaluate(context)
            except Exception as e:
                reasoning.append(f"Rule '{rule.rule_id}' evaluation error: {e}")
                matched = False

            if matched:
                all_matching.append(rule.rule_id)
                rule_desc = rule.name or rule.rule_id[:8]
                reasoning.append(
                    f"Rule '{rule_desc}' matched (action={rule.action}, priority={rule.priority})"
                )
                if winning_rule is None:
                    winning_rule = rule

            # Check timeout
            elapsed = (time.monotonic() - start) * 1000
            if elapsed > self._timeout_seconds * 1000:
                reasoning.append(f"Evaluation timed out after {elapsed:.1f}ms")
                break

        # Determine final action
        if winning_rule:
            action = winning_rule.action
            action_params = winning_rule.action_params.copy()
            severity = winning_rule.severity
            reasoning.append(
                f"Winning rule: '{winning_rule.name or winning_rule.rule_id[:8]}' "
                f"-> action={action}"
            )
        else:
            action = policy.default_action
            action_params = policy.default_action_params.copy()
            severity = policy.default_severity
            reasoning.append(f"No rules matched -> default action={action}")

        elapsed_ms = (time.monotonic() - start) * 1000

        result = PolicyEvaluationResult(
            policy_id=policy.policy_id,
            policy_name=policy.name,
            policy_version=policy.version,
            matched_rules=[winning_rule.rule_id] if winning_rule else [],
            all_matching_rules=all_matching,
            action=action,
            action_params=action_params,
            severity=severity,
            reasoning=reasoning,
            context=context,
            execution_time_ms=elapsed_ms,
        )

        logger.info(
            "policy_evaluated",
            policy_id=policy.policy_id,
            action=action,
            matched_count=len(all_matching),
            elapsed_ms=round(elapsed_ms, 2),
        )

        return result

    def evaluate_rules(
        self,
        rules: list[AdvancedRule],
        context: dict[str, Any],
    ) -> list[str]:
        """Evaluate a list of rules and return IDs of all matching rules."""
        matching: list[str] = []
        for rule in sorted(rules, key=lambda r: r.priority):
            if rule.enabled and rule.evaluate(context):
                matching.append(rule.rule_id)
        return matching
