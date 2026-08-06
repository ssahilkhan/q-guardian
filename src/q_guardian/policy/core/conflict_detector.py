"""Conflict Detector — detects overlapping, shadowed, and contradicting rules."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.policy.data import AdvancedPolicyDefinition, AdvancedRule, ConflictResult
from q_guardian.policy.enums import ConflictResolution, ConflictType

logger = structlog.get_logger(__name__)


class ConflictDetector:
    """Detects conflicts between rules within and across policies."""

    def __init__(self, resolution: ConflictResolution = ConflictResolution.PRIORITY) -> None:
        self._resolution = resolution

    def detect_rule_conflicts(
        self,
        rules_a: list[AdvancedRule],
        rules_b: list[AdvancedRule],
    ) -> list[ConflictResult]:
        """Detect conflicts between two sets of rules."""
        conflicts: list[ConflictResult] = []

        for ra in rules_a:
            if not ra.enabled:
                continue
            for rb in rules_b:
                if not rb.enabled:
                    continue
                conflict = self._check_pair(ra, rb)
                if conflict:
                    conflicts.append(conflict)

        return conflicts

    def detect_policy_conflicts(
        self,
        policy_a: AdvancedPolicyDefinition,
        policy_b: AdvancedPolicyDefinition,
    ) -> list[ConflictResult]:
        """Detect conflicts between two policies."""
        conflicts = self.detect_rule_conflicts(policy_a.rules, policy_b.rules)
        for c in conflicts:
            c.policy_id_a = policy_a.policy_id
            c.policy_id_b = policy_b.policy_id
        return conflicts

    def detect_internal_conflicts(
        self,
        policy: AdvancedPolicyDefinition,
    ) -> list[ConflictResult]:
        """Detect conflicts between rules within a single policy."""
        rules = policy.enabled_rules()
        conflicts: list[ConflictResult] = []
        for i, ra in enumerate(rules):
            for rb in rules[i + 1 :]:
                conflict = self._check_pair(ra, rb)
                if conflict:
                    conflict.policy_id_a = policy.policy_id
                    conflict.policy_id_b = policy.policy_id
                    conflicts.append(conflict)
        return conflicts

    def _check_pair(self, ra: AdvancedRule, rb: AdvancedRule) -> ConflictResult | None:
        """Check if two rules conflict."""
        a_fields = self._extract_fields(ra)
        b_fields = self._extract_fields(rb)

        # Same action = no contradiction, but could be redundant
        if ra.action == rb.action:
            if a_fields == b_fields:
                return ConflictResult(
                    conflict_type=ConflictType.REDUNDANT,
                    rule_id_a=ra.rule_id,
                    rule_id_b=rb.rule_id,
                    description=f"Rules have identical conditions and action '{ra.action}'",
                    resolution=self._resolution,
                )
            return None

        # Different actions — check shadowing first (higher priority subsumes)
        if self._is_subsumed(ra, rb):
            if ra.priority < rb.priority:
                return ConflictResult(
                    conflict_type=ConflictType.SHADOWED,
                    rule_id_a=ra.rule_id,
                    rule_id_b=rb.rule_id,
                    description=(
                        f"Rule '{ra.rule_id[:8]}' (priority={ra.priority}) shadows "
                        f"'{rb.rule_id[:8]}' (priority={rb.priority})"
                    ),
                    resolution=self._resolution,
                    winning_rule_id=ra.rule_id,
                )
            if rb.priority < ra.priority:
                return ConflictResult(
                    conflict_type=ConflictType.SHADOWED,
                    rule_id_a=rb.rule_id,
                    rule_id_b=ra.rule_id,
                    description=(
                        f"Rule '{rb.rule_id[:8]}' (priority={rb.priority}) shadows "
                        f"'{ra.rule_id[:8]}' (priority={ra.priority})"
                    ),
                    resolution=self._resolution,
                    winning_rule_id=rb.rule_id,
                )

        # Different actions and overlapping fields → contradicting
        if a_fields and b_fields and self._fields_overlap(a_fields, b_fields):
            return ConflictResult(
                conflict_type=ConflictType.CONTRADICTING,
                rule_id_a=ra.rule_id,
                rule_id_b=rb.rule_id,
                description=(
                    f"Rules overlap on fields {a_fields & b_fields} but have "
                    f"different actions: '{ra.action}' vs '{rb.action}'"
                ),
                resolution=self._resolution,
            )

        return None

    @staticmethod
    def _extract_fields(rule: AdvancedRule) -> set[str]:
        """Extract field names from a rule's condition."""
        from q_guardian.policy.data import CompoundCondition

        cond = rule.condition
        if isinstance(cond, CompoundCondition):
            fields: set[str] = set()
            for c in cond.conditions:
                if hasattr(c, "field"):
                    fields.add(c.field)
                elif hasattr(c, "conditions"):
                    fields.update(ConflictDetector._extract_fields_from_compound(c))
            return fields
        if hasattr(cond, "field"):
            return {cond.field}
        return set()

    @staticmethod
    def _extract_fields_from_compound(cond: Any) -> set[str]:
        fields: set[str] = set()
        if hasattr(cond, "conditions"):
            for c in cond.conditions:
                if hasattr(c, "field"):
                    fields.add(c.field)
                elif hasattr(c, "conditions"):
                    fields.update(ConflictDetector._extract_fields_from_compound(c))
        return fields

    @staticmethod
    def _fields_overlap(fields_a: set[str], fields_b: set[str]) -> bool:
        return bool(fields_a & fields_b)

    @staticmethod
    def _is_subsumed(ra: AdvancedRule, rb: AdvancedRule) -> bool:
        """Heuristic: if higher-priority rule covers a superset of fields."""
        a_fields = ConflictDetector._extract_fields(ra)
        b_fields = ConflictDetector._extract_fields(rb)
        return a_fields.issubset(b_fields) or b_fields.issubset(a_fields)
