"""PolicyEngine — orchestrates policy registration and evaluation."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.risk.data import PolicyDecision, PolicyDefinition, RiskAssessment
from q_guardian.risk.policy.evaluator import PolicyEvaluator
from q_guardian.risk.policy.policies import (
    create_default_policy,
    create_permissive_policy,
    create_quarantine_policy,
    create_strict_policy,
)
from q_guardian.risk.policy.policy_registry import PolicyRegistry

logger = structlog.get_logger("risk.policy_engine")


class PolicyEngine:
    """Orchestrates policy management and evaluation.

    Manages the policy lifecycle:
      1. Register policies (or use built-in defaults)
      2. Evaluate assessments against active policies
      3. Produce PolicyDecisions
    """

    def __init__(self) -> None:
        self._registry = PolicyRegistry()
        self._evaluator = PolicyEvaluator()
        self._evaluation_count = 0

    @property
    def registry(self) -> PolicyRegistry:
        return self._registry

    @property
    def evaluator(self) -> PolicyEvaluator:
        return self._evaluator

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    def load_defaults(self) -> None:
        """Load all built-in default policies."""
        for policy_fn in [
            create_default_policy,
            create_strict_policy,
            create_permissive_policy,
            create_quarantine_policy,
        ]:
            policy = policy_fn()
            if not self._registry.has(policy.name):
                self._registry.register(policy)

    def evaluate(
        self,
        assessment: RiskAssessment,
        policy_name: str | None = None,
    ) -> PolicyDecision:
        """Evaluate a risk assessment against a policy.

        Args:
            assessment: The risk assessment to evaluate.
            policy_name: Specific policy to use. If None, uses the first
                         enabled policy (recommended: 'default-security').

        Returns:
            PolicyDecision.
        """
        self._evaluation_count += 1

        if policy_name is not None:
            policy = self._registry.get(policy_name)
        else:
            enabled = self._registry.list_enabled()
            if not enabled:
                self.load_defaults()
                enabled = self._registry.list_enabled()
            policy = enabled[0]

        decision = self._evaluator.evaluate(policy, assessment)

        logger.info(
            "policy_engine_evaluated",
            assessment_id=assessment.assessment_id,
            policy_name=policy.name,
            outcome=decision.outcome.value,
        )

        return decision
