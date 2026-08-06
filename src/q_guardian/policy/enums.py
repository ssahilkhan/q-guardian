"""Enums for the Advanced Policy Engine."""

from __future__ import annotations

from enum import StrEnum


class ComparisonOperator(StrEnum):
    """Comparison operators for condition expressions."""

    EQ = "=="
    NEQ = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    MATCHES = "=~"  # regex
    NOT_MATCHES = "!~"  # negated regex
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


class LogicalOperator(StrEnum):
    """Logical operators for compound conditions."""

    AND = "and"
    OR = "or"
    NOT = "not"


class ConditionType(StrEnum):
    """Types of conditions."""

    COMPARISON = "comparison"
    COMPOUND = "compound"
    TEMPORAL = "temporal"
    REGEX = "regex"
    EXISTS = "exists"


class PolicyStatus(StrEnum):
    """Lifecycle status of a policy."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"
    DELETED = "deleted"


class ConflictType(StrEnum):
    """Types of policy conflicts."""

    OVERLAPPING = "overlapping"
    SHADOWED = "shadowed"
    CONTRADICTING = "contradicting"
    REDUNDANT = "redundant"


class ConflictResolution(StrEnum):
    """Strategies for resolving policy conflicts."""

    PRIORITY = "priority"  # higher priority wins
    MOST_RESTRICTIVE = "most_restrictive"
    MOST_PERMISSIVE = "most_permissive"
    FIRST_MATCH = "first_match"
    MANUAL = "manual"


class DSLFormat(StrEnum):
    """Supported external DSL formats."""

    REGO = "rego"
    CEDAR = "cedar"
    YAML = "yaml"
    JSON = "json"
    CUSTOM = "custom"


class Permission(StrEnum):
    """RBAC permissions for policy operations."""

    POLICY_CREATE = "policy_create"
    POLICY_READ = "policy_read"
    POLICY_UPDATE = "policy_update"
    POLICY_DELETE = "policy_delete"
    POLICY_EVALUATE = "policy_evaluate"
    POLICY_ACTIVATE = "policy_activate"
    POLICY_DEACTIVATE = "policy_deactivate"
    POLICY_SIMULATE = "policy_simulate"
    POLICY_EXPORT = "policy_export"
    POLICY_IMPORT = "policy_import"
    POLICY_ADMIN = "policy_admin"
