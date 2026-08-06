"""Risk & Decision Intelligence Engine — Module 7.

Transforms raw detections into intelligent, explainable security
decisions. Consumes outputs from upstream modules (rules, classical ML,
quantum, fusion) and produces risk assessments, policy decisions,
actions, and explanations.

Architecture:
  - Source-agnostic: only consumes NormalizedPrediction objects
  - Pluggable policies with configurable rules
  - Explainable decisions with reasoning graphs
  - Audit trail for compliance and forensics
"""

from q_guardian.risk.actions import (
    ActionEngine,
    AlertResponder,
    AuditLogResponder,
    AuditTrail,
    BlockResponder,
    ContinueResponder,
    Notifier,
    NotifyAdminResponder,
    WebhookResponder,
)
from q_guardian.risk.assessment import (
    ConfidenceEngine,
    RiskAssessmentEngine,
    SeverityEngine,
    ThreatScorer,
    TrustEngine,
)
from q_guardian.risk.config import RiskConfig
from q_guardian.risk.data import (
    ActionResult,
    AuditRecord,
    ConfidenceScore,
    Explanation,
    NormalizedPrediction,
    Notification,
    PolicyDecision,
    PolicyDefinition,
    PolicyRule,
    ReasoningEdge,
    ReasoningGraph,
    ReasoningNode,
    RiskAssessment,
    SeverityScore,
    ThreatScore,
    TrustScore,
)
from q_guardian.risk.enums import (
    ActionType,
    AuditStatus,
    ConfidenceMethod,
    DecisionOutcome,
    ExplanationFormat,
    PolicyAction,
    PolicySeverity,
    ReasoningNodeType,
    RiskLevel,
    Severity,
    ThreatLevel,
    TrustAdjustmentReason,
    TrustLevel,
)
from q_guardian.risk.exceptions import (
    ActionError,
    AssessmentError,
    ConfigurationError,
    ExplanationError,
    PolicyError,
    PolicyNotFoundError,
    RiskError,
    TrustError,
)
from q_guardian.risk.explainability import (
    ExplanationEngine,
    ReasoningGraphBuilder,
    ReportGenerator,
)
from q_guardian.risk.plugin import RiskAnalysisPlugin
from q_guardian.risk.policy import (
    PolicyEngine,
    PolicyEvaluator,
    PolicyRegistry,
    create_default_policy,
    create_permissive_policy,
    create_quarantine_policy,
    create_strict_policy,
)
from q_guardian.risk.storage import RiskStorage

__all__ = [
    # Actions
    "ActionEngine",
    "ActionError",
    "ActionResult",
    "ActionType",
    "AlertResponder",
    "AssessmentError",
    "AuditLogResponder",
    "AuditRecord",
    "AuditStatus",
    "AuditTrail",
    "BlockResponder",
    "ConfidenceEngine",
    "ConfidenceMethod",
    "ConfidenceScore",
    "ConfigurationError",
    "ContinueResponder",
    "DecisionOutcome",
    "Explanation",
    # Explainability
    "ExplanationEngine",
    "ExplanationError",
    "ExplanationFormat",
    # Data models
    "NormalizedPrediction",
    "Notification",
    "Notifier",
    "NotifyAdminResponder",
    "PolicyAction",
    "PolicyDecision",
    "PolicyDefinition",
    # Policy
    "PolicyEngine",
    "PolicyError",
    "PolicyEvaluator",
    "PolicyNotFoundError",
    "PolicyRegistry",
    "PolicyRule",
    "PolicySeverity",
    "ReasoningEdge",
    "ReasoningGraph",
    "ReasoningGraphBuilder",
    "ReasoningNode",
    "ReasoningNodeType",
    "ReportGenerator",
    # Plugin
    "RiskAnalysisPlugin",
    "RiskAssessment",
    # Assessment
    "RiskAssessmentEngine",
    # Config
    "RiskConfig",
    # Exceptions
    "RiskError",
    "RiskLevel",
    # Storage
    "RiskStorage",
    "Severity",
    "SeverityEngine",
    "SeverityScore",
    # Enums
    "ThreatLevel",
    "ThreatScore",
    "ThreatScorer",
    "TrustAdjustmentReason",
    "TrustEngine",
    "TrustError",
    "TrustLevel",
    "TrustScore",
    "WebhookResponder",
    "create_default_policy",
    "create_permissive_policy",
    "create_quarantine_policy",
    "create_strict_policy",
]
