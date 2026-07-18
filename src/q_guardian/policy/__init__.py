"""Advanced Policy Engine — Module 8.

Standalone policy-as-code framework with advanced condition parsing
(AND/OR/NOT, regex, temporal), policy versioning, conflict detection,
simulation, external DSL adapters (Rego, Cedar, YAML), RBAC, and
policy composition (templates, inheritance, overrides).

This module is the full-featured counterpart to the lightweight
``risk.policy`` evaluator, designed for production deployments that
require complex rule logic, auditability, and policy lifecycle management.
"""

from q_guardian.policy.enums import (
    ComparisonOperator,
    LogicalOperator,
    ConditionType,
    PolicyStatus,
    ConflictType,
    ConflictResolution,
    DSLFormat,
    Permission,
)
from q_guardian.policy.data import (
    Condition,
    CompoundCondition,
    AdvancedRule,
    AdvancedPolicyDefinition,
    PolicyVersion,
    ConflictResult,
    SimulationResult,
    PolicyEvaluationResult,
    RBACPermission,
    DSLAdapterResult,
)
from q_guardian.policy.config import PolicyEngineConfig
from q_guardian.policy.events import (
    PolicyRegistered,
    PolicyUpdated,
    PolicyEvaluated,
    PolicyConflictDetected,
    PolicySimulated,
    PolicyActivated,
    PolicyDeactivated,
)
from q_guardian.policy.exceptions import (
    PolicyEngineError,
    ConditionParseError,
    PolicyConflictError,
    PolicyVersionError,
    SimulationError,
    DSLAdapterError,
    RBACError,
    PolicyNotFoundError,
    PolicyCompositionError,
)

__all__ = [
    # Enums
    "ComparisonOperator",
    "LogicalOperator",
    "ConditionType",
    "PolicyStatus",
    "ConflictType",
    "ConflictResolution",
    "DSLFormat",
    "Permission",
    # Data
    "Condition",
    "CompoundCondition",
    "AdvancedRule",
    "AdvancedPolicyDefinition",
    "PolicyVersion",
    "ConflictResult",
    "SimulationResult",
    "PolicyEvaluationResult",
    "RBACPermission",
    "DSLAdapterResult",
    # Config
    "PolicyEngineConfig",
    # Events
    "PolicyRegistered",
    "PolicyUpdated",
    "PolicyEvaluated",
    "PolicyConflictDetected",
    "PolicySimulated",
    "PolicyActivated",
    "PolicyDeactivated",
    # Exceptions
    "PolicyEngineError",
    "ConditionParseError",
    "PolicyConflictError",
    "PolicyVersionError",
    "SimulationError",
    "DSLAdapterError",
    "RBACError",
    "PolicyNotFoundError",
    "PolicyCompositionError",
]
