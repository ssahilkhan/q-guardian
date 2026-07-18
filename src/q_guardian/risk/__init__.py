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
from q_guardian.risk.assessment import (
    ConfidenceEngine,
    RiskAssessmentEngine,
    SeverityEngine,
    ThreatScorer,
    TrustEngine,
)
from q_guardian.risk.policy import (
    PolicyEngine,
    PolicyEvaluator,
    PolicyRegistry,
    create_default_policy,
    create_permissive_policy,
    create_quarantine_policy,
    create_strict_policy,
)
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
from q_guardian.risk.explainability import (
    ExplanationEngine,
    ReasoningGraphBuilder,
    ReportGenerator,
)
from q_guardian.risk.plugin import RiskAnalysisPlugin
from q_guardian.risk.storage import RiskStorage

__all__ = [
    # Config
    "RiskConfig",
    # Enums
    "ThreatLevel",
    "RiskLevel",
    "Severity",
    "TrustLevel",
    "PolicyAction",
    "PolicySeverity",
    "DecisionOutcome",
    "ActionType",
    "AuditStatus",
    "ConfidenceMethod",
    "TrustAdjustmentReason",
    "ExplanationFormat",
    "ReasoningNodeType",
    # Data models
    "NormalizedPrediction",
    "ThreatScore",
    "TrustScore",
    "SeverityScore",
    "ConfidenceScore",
    "RiskAssessment",
    "PolicyRule",
    "PolicyDefinition",
    "PolicyDecision",
    "ActionResult",
    "AuditRecord",
    "Notification",
    "ReasoningNode",
    "ReasoningEdge",
    "ReasoningGraph",
    "Explanation",
    # Exceptions
    "RiskError",
    "AssessmentError",
    "PolicyError",
    "PolicyNotFoundError",
    "ActionError",
    "ExplanationError",
    "TrustError",
    "ConfigurationError",
    # Assessment
    "RiskAssessmentEngine",
    "ThreatScorer",
    "TrustEngine",
    "ConfidenceEngine",
    "SeverityEngine",
    # Policy
    "PolicyEngine",
    "PolicyRegistry",
    "PolicyEvaluator",
    "create_default_policy",
    "create_strict_policy",
    "create_permissive_policy",
    "create_quarantine_policy",
    # Actions
    "ActionEngine",
    "AuditTrail",
    "Notifier",
    "AuditLogResponder",
    "AlertResponder",
    "BlockResponder",
    "ContinueResponder",
    "NotifyAdminResponder",
    "WebhookResponder",
    # Explainability
    "ExplanationEngine",
    "ReasoningGraphBuilder",
    "ReportGenerator",
    # Plugin
    "RiskAnalysisPlugin",
    # Storage
    "RiskStorage",
]
