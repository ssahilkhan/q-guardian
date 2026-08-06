"""Simulation Engine — dry-run policy evaluation, replay, and sandbox testing."""

from __future__ import annotations

import time
from typing import Any

import structlog

from q_guardian.policy.core.evaluator import PolicyEvaluator
from q_guardian.policy.data import (
    AdvancedPolicyDefinition,
    SimulationResult,
)

logger = structlog.get_logger(__name__)


class SimulationEngine:
    """Performs dry-run policy evaluation without executing actions."""

    def __init__(self, evaluator: PolicyEvaluator | None = None) -> None:
        self._evaluator = evaluator or PolicyEvaluator()
        self._history: list[SimulationResult] = []

    def simulate(
        self,
        policy: AdvancedPolicyDefinition,
        context: dict[str, Any],
        would_execute: bool = True,
    ) -> SimulationResult:
        """Run a dry-run evaluation of a policy against a context."""
        start = time.monotonic()

        result = self._evaluator.evaluate(policy, context)

        sim = SimulationResult(
            policy_id=policy.policy_id,
            policy_name=policy.name,
            input_context=context,
            matched_rules=result.all_matching_rules,
            action=result.action,
            action_params=result.action_params,
            severity=result.severity,
            reasoning=result.reasoning,
            would_execute=would_execute,
            execution_time_ms=(time.monotonic() - start) * 1000,
        )

        self._history.append(sim)
        logger.info(
            "simulation_completed",
            policy_id=policy.policy_id,
            action=sim.action,
            matched_count=len(sim.matched_rules),
        )
        return sim

    def simulate_batch(
        self,
        policy: AdvancedPolicyDefinition,
        contexts: list[dict[str, Any]],
    ) -> list[SimulationResult]:
        """Simulate a policy against multiple contexts."""
        return [self.simulate(policy, ctx) for ctx in contexts]

    def simulate_with_overrides(
        self,
        policy: AdvancedPolicyDefinition,
        context: dict[str, Any],
        override_action: str | None = None,
        override_severity: str | None = None,
        disabled_rule_ids: list[str] | None = None,
    ) -> SimulationResult:
        """Simulate with temporary overrides for testing scenarios."""
        # Create a modified copy
        sim_policy = policy.model_copy(deep=True)

        if disabled_rule_ids:
            for rule in sim_policy.rules:
                if rule.rule_id in disabled_rule_ids:
                    rule.enabled = False

        if override_action:
            sim_policy.default_action = override_action
        if override_severity:
            sim_policy.default_severity = override_severity

        result = self.simulate(sim_policy, context)
        result.metadata["overrides_applied"] = {
            "override_action": override_action,
            "override_severity": override_severity,
            "disabled_rules": disabled_rule_ids or [],
        }
        return result

    def replay(
        self,
        policy: AdvancedPolicyDefinition,
        simulation_ids: list[str] | None = None,
    ) -> list[SimulationResult]:
        """Replay previous simulations against current policy state."""
        results: list[SimulationResult] = []
        # Snapshot history before iterating to avoid infinite loop
        # (simulate() appends to _history)
        history_snapshot = list(self._history)
        for sim in history_snapshot:
            if simulation_ids and sim.simulation_id not in simulation_ids:
                continue
            new_result = self._evaluator.evaluate(policy, sim.input_context)

            result = SimulationResult(
                policy_id=policy.policy_id,
                policy_name=policy.name,
                input_context=sim.input_context,
                matched_rules=new_result.all_matching_rules,
                action=new_result.action,
                action_params=new_result.action_params,
                severity=new_result.severity,
                reasoning=new_result.reasoning,
                would_execute=True,
                execution_time_ms=new_result.execution_time_ms,
            )
            results.append(result)
        return results

    def get_history(self) -> list[SimulationResult]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()

    def compare_policies(
        self,
        policy_a: AdvancedPolicyDefinition,
        policy_b: AdvancedPolicyDefinition,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare how two policies would handle the same context."""
        sim_a = self.simulate(policy_a, context)
        sim_b = self.simulate(policy_b, context)
        return {
            "policy_a": {
                "name": policy_a.name,
                "action": sim_a.action,
                "severity": sim_a.severity,
                "matched_rules": sim_a.matched_rules,
            },
            "policy_b": {
                "name": policy_b.name,
                "action": sim_b.action,
                "severity": sim_b.severity,
                "matched_rules": sim_b.matched_rules,
            },
            "same_action": sim_a.action == sim_b.action,
            "same_severity": sim_a.severity == sim_b.severity,
        }
