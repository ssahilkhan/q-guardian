"""Advanced Policy Engine — Module 8.

Standalone policy-as-code framework with advanced condition parsing
(AND/OR/NOT, regex, temporal), policy versioning, conflict detection,
simulation, external DSL adapters (Rego, Cedar, YAML), RBAC, and
policy composition (templates, inheritance, overrides).

This module is the full-featured counterpart to the lightweight
``risk.policy`` evaluator, designed for production deployments that
require complex rule logic, auditability, and policy lifecycle management.
"""

from q_guardian.policy.config import PolicyEngineConfig
from q_guardian.policy.data import (
    AdvancedPolicyDefinition,
    AdvancedRule,
    CompoundCondition,
    Condition,
    ConflictResult,
    DSLAdapterResult,
    PolicyEvaluationResult,
    PolicyVersion,
    RBACPermission,
    SimulationResult,
)
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
from q_guardian.policy.events import (
    PolicyActivated,
    PolicyConflictDetected,
    PolicyDeactivated,
    PolicyEvaluated,
    PolicyRegistered,
    PolicySimulated,
    PolicyUpdated,
)
from q_guardian.policy.exceptions import (
    ConditionParseError,
    DSLAdapterError,
    PolicyCompositionError,
    PolicyConflictError,
    PolicyEngineError,
    PolicyNotFoundError,
    PolicyVersionError,
    RBACError,
    SimulationError,
)

__all__ = [
    "AdvancedPolicyDefinition",
    "AdvancedRule",
    # Enums
    "ComparisonOperator",
    "CompoundCondition",
    # Data
    "Condition",
    "ConditionParseError",
    "ConditionType",
    "ConflictResolution",
    "ConflictResult",
    "ConflictType",
    "DSLAdapterError",
    "DSLAdapterResult",
    "DSLFormat",
    "LogicalOperator",
    "Permission",
    "PolicyActivated",
    "PolicyCompositionError",
    "PolicyConflictDetected",
    "PolicyConflictError",
    "PolicyDeactivated",
    # Config
    "PolicyEngineConfig",
    # Exceptions
    "PolicyEngineError",
    "PolicyEvaluated",
    "PolicyEvaluationResult",
    "PolicyNotFoundError",
    # Events
    "PolicyRegistered",
    "PolicySimulated",
    "PolicyStatus",
    "PolicyUpdated",
    "PolicyVersion",
    "PolicyVersionError",
    "RBACError",
    "RBACPermission",
    "SimulationError",
    "SimulationResult",
]
