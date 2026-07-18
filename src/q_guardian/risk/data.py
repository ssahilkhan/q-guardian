"""Domain data models for the Risk & Decision Intelligence Engine.

All data models consumed and produced by the risk module. These models
are standalone — they do not import from quantum/, ml/, or security/.
The risk module receives pre-fused ThreatPrediction/FusedPrediction
objects and produces its own RiskAssessment, PolicyDecision, and
Explanation objects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.risk.enums import (
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
from q_guardian.utils.uuid_utils import generate_uuid


# ── Input models ────────────────────────────────────────────────────────


class NormalizedPrediction(BaseModel):
    """Standardized prediction input for risk assessment.

    Accepts outputs from any upstream source (ThreatPrediction,
    FusedPrediction, or any other detector) in a source-agnostic format.
    """

    model_config = ConfigDict(populate_by_name=True)

    prediction_id: str = Field(default_factory=generate_uuid, description="Unique ID")
    source_id: str = Field(default="", description="Upstream source identifier")
    source_type: str = Field(default="", description="Source type (rule/ml/quantum/fused)")
    model_name: str = Field(default="", description="Model that produced this")
    provider_id: str = Field(default="", description="Provider identifier")

    predicted_label: str = Field(description="Predicted class label")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence 0-1")
    probabilities: dict[str, float] = Field(default_factory=dict, description="Class probabilities")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk score 0-1")

    reasoning_steps: list[str] = Field(default_factory=list, description="Reasoning steps from source")
    evidence: list[str] = Field(default_factory=list, description="Evidence snippets")
    rules_triggered: list[str] = Field(default_factory=list, description="Rule IDs that fired")
    feature_importances: dict[str, float] = Field(default_factory=dict, description="Feature importances")

    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra source metadata")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Creation time")
    is_valid: bool = Field(default=True, description="Whether prediction is usable")
    error_message: str = Field(default="", description="Error if prediction failed")


# ── Scoring models ──────────────────────────────────────────────────────


class ThreatScore(BaseModel):
    """Composite threat score from the ThreatScorer."""

    model_config = ConfigDict(populate_by_name=True)

    score_id: str = Field(default_factory=generate_uuid, description="Unique ID")
    threat_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Composite threat score")
    probability_component: float = Field(default=0.0, ge=0.0, le=1.0, description="Probability weight")
    confidence_component: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence weight")
    reliability_component: float = Field(default=0.0, ge=0.0, le=1.0, description="Reliability weight")
    agreement_component: float = Field(default=0.0, ge=0.0, le=1.0, description="Agreement weight")
    diversity_component: float = Field(default=0.0, ge=0.0, le=1.0, description="Diversity weight")
    severity_component: float = Field(default=0.0, ge=0.0, le=1.0, description="Severity weight")
    threat_level: ThreatLevel = Field(default=ThreatLevel.NONE, description="Threat level")
    reasoning: list[str] = Field(default_factory=list, description="Scoring reasoning steps")


class TrustScore(BaseModel):
    """Trust score for a provider."""

    model_config = ConfigDict(populate_by_name=True)

    provider_id: str = Field(description="Provider identifier")
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Trust score 0-1")
    trust_level: TrustLevel = Field(default=TrustLevel.MODERATE, description="Trust level")
    total_predictions: int = Field(default=0, description="Total predictions made")
    correct_predictions: int = Field(default=0, description="Correct predictions")
    incorrect_predictions: int = Field(default=0, description="Incorrect predictions")
    false_positives: int = Field(default=0, description="False positives")
    false_negatives: int = Field(default=0, description="False negatives")
    accuracy: float = Field(default=0.0, ge=0.0, le=1.0, description="Historical accuracy")
    last_adjustment: datetime | None = Field(default=None, description="Last trust adjustment")
    adjustment_history: list[dict[str, Any]] = Field(
        default_factory=list, description="Recent adjustments"
    )


class SeverityScore(BaseModel):
    """Severity classification result."""

    model_config = ConfigDict(populate_by_name=True)

    severity: Severity = Field(default=Severity.LOW, description="Classified severity")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Raw severity score")
    reasoning: str = Field(default="", description="Why this severity was assigned")
    mapping_used: str = Field(default="default", description="Which mapping was applied")


class ConfidenceScore(BaseModel):
    """Normalized and aggregated confidence."""

    model_config = ConfigDict(populate_by_name=True)

    raw_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Raw confidence")
    normalized_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Normalized confidence")
    method: ConfidenceMethod = Field(default=ConfidenceMethod.NONE, description="Method used")
    confidence_interval: tuple[float, float] | None = Field(
        default=None, description="Confidence interval (low, high)"
    )
    aggregation_count: int = Field(default=1, description="Number of sources aggregated")


# ── Assessment model ────────────────────────────────────────────────────


class RiskAssessment(BaseModel):
    """Complete risk assessment output — the primary output of the risk engine.

    Produced by RiskAssessmentEngine. Contains all scoring, severity,
    trust, confidence, and decision metadata needed for downstream
    policy evaluation and action execution.
    """

    model_config = ConfigDict(populate_by_name=True)

    assessment_id: str = Field(default_factory=generate_uuid, description="Unique ID")
    prediction_id: str = Field(default="", description="Input prediction ID")

    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall risk score 0-1")
    risk_level: RiskLevel = Field(default=RiskLevel.MINIMAL, description="Risk level")
    threat_score: ThreatScore = Field(default_factory=ThreatScore, description="Threat scoring detail")
    severity: SeverityScore = Field(default_factory=SeverityScore, description="Severity classification")
    confidence: ConfidenceScore = Field(default_factory=ConfidenceScore, description="Confidence detail")
    trust_scores: dict[str, TrustScore] = Field(
        default_factory=dict, description="Provider trust scores"
    )

    reasoning: list[str] = Field(default_factory=list, description="Assessment reasoning steps")
    contributing_sources: list[str] = Field(default_factory=list, description="Source IDs that contributed")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Assessment time")


# ── Policy models ───────────────────────────────────────────────────────


class PolicyRule(BaseModel):
    """A single rule within a policy."""

    model_config = ConfigDict(populate_by_name=True)

    rule_id: str = Field(default_factory=generate_uuid, description="Unique rule ID")
    condition: str = Field(description="Condition expression (e.g. 'risk_score >= 0.9')")
    action: PolicyAction = Field(description="Action to take when condition is met")
    severity: PolicySeverity = Field(default=PolicySeverity.MEDIUM, description="Rule severity")
    description: str = Field(default="", description="Human-readable description")
    enabled: bool = Field(default=True, description="Whether rule is active")
    priority: int = Field(default=0, description="Rule priority (lower = higher priority)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")


class PolicyDefinition(BaseModel):
    """Full policy definition with rules and metadata."""

    model_config = ConfigDict(populate_by_name=True)

    policy_id: str = Field(default_factory=generate_uuid, description="Unique policy ID")
    name: str = Field(description="Policy name")
    description: str = Field(default="", description="Human-readable description")
    version: str = Field(default="1.0.0", description="Policy version")
    enabled: bool = Field(default=True, description="Whether policy is active")
    rules: list[PolicyRule] = Field(default_factory=list, description="Policy rules")
    default_action: PolicyAction = Field(default=PolicyAction.ALLOW, description="Default action if no rule matches")
    default_severity: PolicySeverity = Field(default=PolicySeverity.LOW, description="Default severity")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Creation time")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Last update")


class PolicyDecision(BaseModel):
    """Result of evaluating a policy against a risk assessment."""

    model_config = ConfigDict(populate_by_name=True)

    decision_id: str = Field(default_factory=generate_uuid, description="Unique ID")
    assessment_id: str = Field(default="", description="Input assessment ID")
    policy_id: str = Field(default="", description="Policy used")
    policy_name: str = Field(default="", description="Policy name")

    outcome: DecisionOutcome = Field(default=DecisionOutcome.ALLOWED, description="Decision outcome")
    action: PolicyAction = Field(default=PolicyAction.ALLOW, description="Action prescribed")
    severity: PolicySeverity = Field(default=PolicySeverity.LOW, description="Severity level")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk score at decision time")

    matched_rules: list[str] = Field(default_factory=list, description="Rule IDs that matched")
    reasoning: list[str] = Field(default_factory=list, description="Decision reasoning")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Decision time")


# ── Action models ───────────────────────────────────────────────────────


class ActionResult(BaseModel):
    """Result of executing an action."""

    model_config = ConfigDict(populate_by_name=True)

    action_id: str = Field(default_factory=generate_uuid, description="Unique ID")
    decision_id: str = Field(default="", description="Input decision ID")
    action_type: str = Field(description="Action type executed")
    success: bool = Field(default=True, description="Whether action succeeded")
    message: str = Field(default="", description="Result message")
    details: dict[str, Any] = Field(default_factory=dict, description="Extra result data")
    execution_time_ms: float = Field(default=0.0, description="Execution time in ms")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Execution time")


class AuditRecord(BaseModel):
    """Immutable audit record for a risk decision."""

    model_config = ConfigDict(populate_by_name=True)

    record_id: str = Field(default_factory=generate_uuid, description="Unique record ID")
    assessment_id: str = Field(default="", description="Associated assessment")
    decision_id: str = Field(default="", description="Associated decision")
    prediction_id: str = Field(default="", description="Associated prediction")

    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk score")
    risk_level: RiskLevel = Field(default=RiskLevel.MINIMAL, description="Risk level")
    severity: Severity = Field(default=Severity.LOW, description="Severity")
    outcome: DecisionOutcome = Field(default=DecisionOutcome.ALLOWED, description="Decision outcome")
    action: PolicyAction = Field(default=PolicyAction.ALLOW, description="Action taken")

    contributing_sources: list[str] = Field(default_factory=list, description="Source IDs")
    reasoning: list[str] = Field(default_factory=list, description="Decision reasoning")
    policy_name: str = Field(default="", description="Policy used")

    status: AuditStatus = Field(default=AuditStatus.ACTIVE, description="Audit status")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Creation time")


# ── Explanation models ──────────────────────────────────────────────────


class ReasoningNode(BaseModel):
    """A node in the reasoning graph."""

    model_config = ConfigDict(populate_by_name=True)

    node_id: str = Field(default_factory=generate_uuid, description="Unique node ID")
    node_type: ReasoningNodeType = Field(description="Type of node")
    label: str = Field(description="Human-readable label")
    description: str = Field(default="", description="Detailed description")
    value: Any = Field(default=None, description="Node value")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Node confidence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")


class ReasoningEdge(BaseModel):
    """A directed edge in the reasoning graph."""

    model_config = ConfigDict(populate_by_name=True)

    edge_id: str = Field(default_factory=generate_uuid, description="Unique edge ID")
    source_node_id: str = Field(description="Source node ID")
    target_node_id: str = Field(description="Target node ID")
    label: str = Field(default="", description="Edge label")
    weight: float = Field(default=1.0, description="Edge weight")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")


class ReasoningGraph(BaseModel):
    """Complete reasoning graph for a decision."""

    model_config = ConfigDict(populate_by_name=True)

    graph_id: str = Field(default_factory=generate_uuid, description="Unique graph ID")
    assessment_id: str = Field(default="", description="Associated assessment")
    nodes: list[ReasoningNode] = Field(default_factory=list, description="Graph nodes")
    edges: list[ReasoningEdge] = Field(default_factory=list, description="Graph edges")
    summary: str = Field(default="", description="Human-readable summary")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")


class Explanation(BaseModel):
    """Complete explanation for a risk decision."""

    model_config = ConfigDict(populate_by_name=True)

    explanation_id: str = Field(default_factory=generate_uuid, description="Unique ID")
    assessment_id: str = Field(default="", description="Associated assessment")
    decision_id: str = Field(default="", description="Associated decision")

    summary: str = Field(description="Human-readable summary")
    why: str = Field(default="", description="Why this decision was made")
    which_models: list[str] = Field(default_factory=list, description="Models that contributed")
    confidence_summary: str = Field(default="", description="Confidence explanation")
    risk_summary: str = Field(default="", description="Risk explanation")
    policy_used: str = Field(default="", description="Policy name")
    action_taken: str = Field(default="", description="Action taken")

    reasoning_graph: ReasoningGraph | None = Field(
        default=None, description="Reasoning graph"
    )
    format: ExplanationFormat = Field(
        default=ExplanationFormat.STRUCTURED, description="Output format"
    )
    export_data: dict[str, Any] = Field(default_factory=dict, description="Exportable data")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Generation time")


# ── Notification models ─────────────────────────────────────────────────


class Notification(BaseModel):
    """A notification to be sent to administrators or external systems."""

    model_config = ConfigDict(populate_by_name=True)

    notification_id: str = Field(default_factory=generate_uuid, description="Unique ID")
    title: str = Field(description="Notification title")
    message: str = Field(description="Notification message")
    severity: Severity = Field(default=Severity.LOW, description="Notification severity")
    recipient: str = Field(default="admin", description="Recipient identifier")
    channel: str = Field(default="default", description="Notification channel")
    sent: bool = Field(default=False, description="Whether notification was sent")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Creation time")
