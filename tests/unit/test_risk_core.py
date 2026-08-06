"""Tests for risk module enums, data models, config, exceptions, and events."""

from q_guardian.risk.config import (
    ConfidenceConfig,
    RiskConfig,
    ScoringWeights,
    SeverityMapping,
    TrustConfig,
)
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
from q_guardian.risk.events import (
    ActionExecuted,
    ExplanationGenerated,
    PolicyExecuted,
    PolicyMatched,
    RiskAssessmentCompleted,
    RiskCalculated,
    ThreatScored,
    TrustUpdated,
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


class TestEnums:
    def test_threat_level_values(self):
        assert ThreatLevel.NONE.value == "none"
        assert ThreatLevel.CRITICAL.value == "critical"
        assert len(ThreatLevel) == 5

    def test_risk_level_values(self):
        assert RiskLevel.MINIMAL.value == "minimal"
        assert RiskLevel.CRITICAL.value == "critical"
        assert len(RiskLevel) == 6

    def test_severity_values(self):
        assert Severity.LOW.value == "low"
        assert Severity.CRITICAL.value == "critical"
        assert len(Severity) == 4

    def test_trust_level_values(self):
        assert TrustLevel.UNTRUSTED.value == "untrusted"
        assert TrustLevel.VERIFIED.value == "verified"
        assert len(TrustLevel) == 5

    def test_policy_action_values(self):
        assert PolicyAction.ALLOW.value == "allow"
        assert PolicyAction.BLOCK.value == "block"
        assert PolicyAction.QUARANTINE.value == "quarantine"
        assert PolicyAction.TERMINATE_SESSION.value == "terminate_session"
        assert len(PolicyAction) == 9

    def test_decision_outcome_values(self):
        assert DecisionOutcome.ALLOWED.value == "allowed"
        assert DecisionOutcome.BLOCKED.value == "blocked"
        assert len(DecisionOutcome) == 9

    def test_action_type_values(self):
        assert ActionType.AUDIT_LOG.value == "audit_log"
        assert ActionType.WEBHOOK.value == "webhook"
        assert len(ActionType) == 8

    def test_audit_status_values(self):
        assert AuditStatus.CREATED.value == "created"
        assert AuditStatus.ESCALATED.value == "escalated"
        assert len(AuditStatus) == 5

    def test_confidence_method_values(self):
        assert ConfidenceMethod.NONE.value == "none"
        assert ConfidenceMethod.Z_SCORE.value == "z_score"
        assert len(ConfidenceMethod) == 5

    def test_trust_adjustment_reason_values(self):
        assert TrustAdjustmentReason.CORRECT_PREDICTION.value == "correct_prediction"
        assert len(TrustAdjustmentReason) == 8

    def test_explanation_format_values(self):
        assert ExplanationFormat.JSON.value == "json"
        assert ExplanationFormat.MARKDOWN.value == "markdown"
        assert len(ExplanationFormat) == 4

    def test_reasoning_node_type_values(self):
        assert ReasoningNodeType.INPUT.value == "input"
        assert ReasoningNodeType.OUTCOME.value == "outcome"
        assert len(ReasoningNodeType) == 10


class TestDataModels:
    def test_normalized_prediction_defaults(self):
        p = NormalizedPrediction(predicted_label="benign")
        assert p.predicted_label == "benign"
        assert p.confidence == 0.0
        assert p.risk_score == 0.0
        assert p.is_valid is True
        assert p.prediction_id  # auto-generated

    def test_normalized_prediction_full(self):
        p = NormalizedPrediction(
            predicted_label="threat",
            confidence=0.95,
            risk_score=0.88,
            probabilities={"benign": 0.05, "threat": 0.95},
            source_id="rule-engine",
            source_type="rule",
        )
        assert p.source_id == "rule-engine"
        assert p.probabilities["threat"] == 0.95

    def test_threat_score_defaults(self):
        ts = ThreatScore()
        assert ts.threat_score == 0.0
        assert ts.threat_level == ThreatLevel.NONE

    def test_trust_score_full(self):
        ts = TrustScore(
            provider_id="ml-model",
            trust_score=0.85,
            total_predictions=100,
            correct_predictions=85,
        )
        assert ts.accuracy == 0.0  # accuracy not auto-computed
        assert ts.total_predictions == 100

    def test_severity_score_defaults(self):
        ss = SeverityScore()
        assert ss.severity == Severity.LOW

    def test_confidence_score_defaults(self):
        cs = ConfidenceScore()
        assert cs.raw_confidence == 0.0
        assert cs.method == ConfidenceMethod.NONE

    def test_risk_assessment_defaults(self):
        ra = RiskAssessment()
        assert ra.risk_score == 0.0
        assert ra.risk_level == RiskLevel.MINIMAL
        assert ra.assessment_id  # auto-generated

    def test_policy_rule_full(self):
        pr = PolicyRule(
            condition="risk_score >= 0.9",
            action=PolicyAction.BLOCK,
            severity=PolicySeverity.CRITICAL,
            description="Block high risk",
            priority=0,
        )
        assert pr.condition == "risk_score >= 0.9"
        assert pr.action == PolicyAction.BLOCK
        assert pr.enabled is True

    def test_policy_definition_defaults(self):
        pd = PolicyDefinition(name="test-policy")
        assert pd.name == "test-policy"
        assert pd.version == "1.0.0"
        assert pd.default_action == PolicyAction.ALLOW
        assert pd.enabled is True

    def test_policy_decision_defaults(self):
        pd = PolicyDecision()
        assert pd.outcome == DecisionOutcome.ALLOWED
        assert pd.action == PolicyAction.ALLOW

    def test_action_result_defaults(self):
        ar = ActionResult(action_type="block")
        assert ar.success is True
        assert ar.execution_time_ms == 0.0

    def test_audit_record_defaults(self):
        ar = AuditRecord()
        assert ar.status == AuditStatus.ACTIVE
        assert ar.outcome == DecisionOutcome.ALLOWED

    def test_notification_full(self):
        n = Notification(
            title="Alert",
            message="High risk detected",
            severity=Severity.HIGH,
            recipient="admin",
        )
        assert n.title == "Alert"
        assert n.sent is False

    def test_reasoning_node_full(self):
        rn = ReasoningNode(
            node_type=ReasoningNodeType.INPUT,
            label="Test Node",
            value="test",
        )
        assert rn.node_type == ReasoningNodeType.INPUT
        assert rn.confidence == 1.0

    def test_reasoning_edge_full(self):
        re = ReasoningEdge(
            source_node_id="n1",
            target_node_id="n2",
            label="flows to",
        )
        assert re.weight == 1.0

    def test_reasoning_graph_defaults(self):
        rg = ReasoningGraph()
        assert rg.nodes == []
        assert rg.edges == []

    def test_explanation_full(self):
        e = Explanation(
            summary="Test summary",
            why="Because",
            policy_used="default",
            action_taken="block",
        )
        assert e.summary == "Test summary"
        assert e.format == ExplanationFormat.STRUCTURED


class TestConfig:
    def test_risk_config_defaults(self):
        c = RiskConfig()
        assert c.enabled is True
        assert c.audit_enabled is True
        assert c.explanation_enabled is True
        assert c.max_risk_score == 1.0

    def test_scoring_weights_defaults(self):
        w = ScoringWeights()
        total = (
            w.probability + w.confidence + w.reliability + w.agreement + w.diversity + w.severity
        )
        assert abs(total - 1.0) < 0.01

    def test_severity_mapping_defaults(self):
        m = SeverityMapping()
        assert m.critical_threshold == 0.9
        assert m.high_threshold == 0.7

    def test_trust_config_defaults(self):
        tc = TrustConfig()
        assert tc.initial_trust == 0.5
        assert tc.adjustment_rate == 0.1

    def test_confidence_config_defaults(self):
        cc = ConfidenceConfig()
        assert cc.method == ConfidenceMethod.NONE
        assert cc.temperature == 1.0


class TestExceptions:
    def test_risk_error(self):
        e = RiskError("test error")
        assert e.message == "test error"
        assert e.code == "RISK_ERROR"

    def test_assessment_error(self):
        e = AssessmentError("assessment failed")
        assert e.code == "ASSESSMENT_ERROR"

    def test_policy_error(self):
        e = PolicyError("policy failed")
        assert e.code == "POLICY_ERROR"

    def test_policy_not_found_error(self):
        e = PolicyNotFoundError("missing-policy")
        assert "missing-policy" in e.message
        assert e.code == "POLICY_NOT_FOUND"

    def test_action_error(self):
        e = ActionError("action failed")
        assert e.code == "ACTION_ERROR"

    def test_explanation_error(self):
        e = ExplanationError("explain failed")
        assert e.code == "EXPLANATION_ERROR"

    def test_trust_error(self):
        e = TrustError("trust failed")
        assert e.code == "TRUST_ERROR"

    def test_configuration_error(self):
        e = ConfigurationError("bad config")
        assert e.code == "RISK_CONFIGURATION_ERROR"

    def test_risk_error_to_dict(self):
        e = RiskError("test", details={"key": "value"})
        d = e.to_dict()
        assert d["error"]["code"] == "RISK_ERROR"
        assert d["error"]["details"]["key"] == "value"


class TestEvents:
    def test_risk_calculated_event(self):
        e = RiskCalculated(source="test", data={"risk_score": 0.8})
        assert e.event_type == "risk.score.calculated"

    def test_threat_scored_event(self):
        e = ThreatScored(source="test")
        assert e.event_type == "risk.threat.scored"

    def test_trust_updated_event(self):
        e = TrustUpdated(source="test")
        assert e.event_type == "risk.trust.updated"

    def test_policy_matched_event(self):
        e = PolicyMatched(source="test")
        assert e.event_type == "risk.policy.matched"

    def test_policy_executed_event(self):
        e = PolicyExecuted(source="test")
        assert e.event_type == "risk.policy.executed"

    def test_action_executed_event(self):
        e = ActionExecuted(source="test")
        assert e.event_type == "risk.action.executed"

    def test_explanation_generated_event(self):
        e = ExplanationGenerated(source="test")
        assert e.event_type == "risk.explanation.generated"

    def test_risk_assessment_completed_event(self):
        e = RiskAssessmentCompleted(source="test")
        assert e.event_type == "risk.assessment.completed"
