"""Data models for the Advanced Policy Engine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from q_guardian.policy.enums import (
    ComparisonOperator,
    ConditionType,
    ConflictResolution,
    ConflictType,
    DSLFormat,
    LogicalOperator,
    Permission,
    PolicyStatus,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Condition models
# ---------------------------------------------------------------------------


class Condition(BaseModel):
    """A single comparison condition: ``field operator value``."""

    condition_id: str = Field(default_factory=_uuid)
    field: str
    operator: ComparisonOperator
    value: Any
    negated: bool = False
    condition_type: ConditionType = ConditionType.COMPARISON
    metadata: dict[str, Any] = Field(default_factory=dict)

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Evaluate this condition against a context dict."""
        actual = context.get(self.field)
        if actual is None and self.operator not in (
            ComparisonOperator.EQ,
            ComparisonOperator.NEQ,
        ):
            return False

        result = self._compare(actual, self.operator, self.value)
        return not result if self.negated else result

    def _compare(self, actual: Any, op: ComparisonOperator, expected: Any) -> bool:
        if op == ComparisonOperator.EQ:
            return self._coerce_equal(actual, expected)
        if op == ComparisonOperator.NEQ:
            return not self._coerce_equal(actual, expected)
        if op == ComparisonOperator.GT:
            return float(actual) > float(expected)
        if op == ComparisonOperator.GTE:
            return float(actual) >= float(expected)
        if op == ComparisonOperator.LT:
            return float(actual) < float(expected)
        if op == ComparisonOperator.LTE:
            return float(actual) <= float(expected)
        if op == ComparisonOperator.MATCHES:
            import re

            return bool(re.search(str(expected), str(actual)))
        if op == ComparisonOperator.NOT_MATCHES:
            import re

            return not bool(re.search(str(expected), str(actual)))
        if op == ComparisonOperator.IN:
            return str(actual) in [str(v) for v in expected]
        if op == ComparisonOperator.NOT_IN:
            return str(actual) not in [str(v) for v in expected]
        if op == ComparisonOperator.CONTAINS:
            return str(expected) in str(actual)
        if op == ComparisonOperator.STARTS_WITH:
            return str(actual).startswith(str(expected))
        if op == ComparisonOperator.ENDS_WITH:
            return str(actual).endswith(str(expected))
        return False

    @staticmethod
    def _coerce_equal(actual: Any, expected: Any) -> bool:
        try:
            if float(actual) == float(expected):
                return True
        except (ValueError, TypeError):
            pass
        return str(actual) == str(expected)


class CompoundCondition(BaseModel):
    """A logical combination of conditions: ``AND / OR / NOT``."""

    condition_id: str = Field(default_factory=_uuid)
    operator: LogicalOperator
    conditions: list[Condition | CompoundCondition] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Evaluate this compound condition against a context dict."""
        if not self.conditions:
            return True

        if self.operator == LogicalOperator.NOT:
            inner = self.conditions[0]
            result = (
                inner.evaluate(context)
                if isinstance(inner, (Condition, CompoundCondition))
                else bool(inner)
            )
            return not result

        if self.operator == LogicalOperator.AND:
            return all(
                c.evaluate(context) if isinstance(c, (Condition, CompoundCondition)) else bool(c)
                for c in self.conditions
            )

        if self.operator == LogicalOperator.OR:
            return any(
                c.evaluate(context) if isinstance(c, (Condition, CompoundCondition)) else bool(c)
                for c in self.conditions
            )

        return False


# ---------------------------------------------------------------------------
# Rule & Policy models
# ---------------------------------------------------------------------------


class AdvancedRule(BaseModel):
    """An advanced policy rule with rich conditions and action parameters."""

    rule_id: str = Field(default_factory=_uuid)
    name: str = ""
    description: str = ""
    condition: Condition | CompoundCondition
    action: str = "allow"
    action_params: dict[str, Any] = Field(default_factory=dict)
    severity: str = "medium"
    priority: int = 0
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_temporal(self) -> bool:
        return self.valid_from is not None or self.valid_until is not None

    def is_valid_now(self) -> bool:
        now = _utcnow()
        if self.valid_from and now < self.valid_from:
            return False
        return not (self.valid_until and now > self.valid_until)

    def evaluate(self, context: dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        if self.is_temporal() and not self.is_valid_now():
            return False
        return self.condition.evaluate(context)


class AdvancedPolicyDefinition(BaseModel):
    """Full policy definition with versioning and lifecycle."""

    policy_id: str = Field(default_factory=_uuid)
    name: str
    description: str = ""
    version: str = "1.0.0"
    status: PolicyStatus = PolicyStatus.DRAFT
    rules: list[AdvancedRule] = Field(default_factory=list)
    default_action: str = "allow"
    default_action_params: dict[str, Any] = Field(default_factory=dict)
    default_severity: str = "low"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    created_by: str = ""
    parent_policy_id: str | None = None  # for composition/inheritance

    def enabled_rules(self) -> list[AdvancedRule]:
        return [r for r in self.rules if r.enabled]


class PolicyVersion(BaseModel):
    """A snapshot of a policy version for lifecycle management."""

    version_id: str = Field(default_factory=_uuid)
    policy_id: str
    version: str
    policy_snapshot: AdvancedPolicyDefinition
    changelog: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    created_by: str = ""


# ---------------------------------------------------------------------------
# Conflict & Simulation models
# ---------------------------------------------------------------------------


class ConflictResult(BaseModel):
    """Result of conflict detection between two rules or policies."""

    conflict_id: str = Field(default_factory=_uuid)
    conflict_type: ConflictType
    rule_id_a: str
    rule_id_b: str
    policy_id_a: str = ""
    policy_id_b: str = ""
    description: str = ""
    resolution: ConflictResolution = ConflictResolution.PRIORITY
    resolved: bool = False
    winning_rule_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulationResult(BaseModel):
    """Result of a policy simulation (dry-run)."""

    simulation_id: str = Field(default_factory=_uuid)
    policy_id: str
    policy_name: str
    input_context: dict[str, Any]
    matched_rules: list[str] = Field(default_factory=list)
    action: str = "allow"
    action_params: dict[str, Any] = Field(default_factory=dict)
    severity: str = "low"
    reasoning: list[str] = Field(default_factory=list)
    would_execute: bool = True
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyEvaluationResult(BaseModel):
    """Result of evaluating a policy against a context."""

    evaluation_id: str = Field(default_factory=_uuid)
    policy_id: str
    policy_name: str
    policy_version: str = ""
    matched_rules: list[str] = Field(default_factory=list)
    all_matching_rules: list[str] = Field(default_factory=list)
    action: str = "allow"
    action_params: dict[str, Any] = Field(default_factory=dict)
    severity: str = "low"
    reasoning: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = 0.0
    timestamp: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# RBAC models
# ---------------------------------------------------------------------------


class RBACPermission(BaseModel):
    """A role-based access control permission entry."""

    permission_id: str = Field(default_factory=_uuid)
    role: str
    permissions: list[Permission] = Field(default_factory=list)
    policy_ids: list[str] = Field(default_factory=list)  # empty = all policies
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# DSL adapter models
# ---------------------------------------------------------------------------


class DSLAdapterResult(BaseModel):
    """Result of converting a policy to/from an external DSL format."""

    result_id: str = Field(default_factory=_uuid)
    source_format: DSLFormat
    target_format: DSLFormat = DSLFormat.CUSTOM
    raw_source: str = ""
    policy: AdvancedPolicyDefinition | None = None
    success: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
