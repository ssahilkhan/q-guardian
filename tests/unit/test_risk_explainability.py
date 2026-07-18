"""Tests for ExplanationEngine, ReasoningGraphBuilder, ReportGenerator."""

import pytest
from q_guardian.risk.explainability.explanation_engine import ExplanationEngine
from q_guardian.risk.explainability.reasoning_graph import ReasoningGraphBuilder
from q_guardian.risk.explainability.report_generator import ReportGenerator
from q_guardian.risk.data import (
    RiskAssessment, PolicyDecision, ActionResult, Explanation, ReasoningGraph, TrustScore,
)
from q_guardian.risk.enums import (
    ExplanationFormat, RiskLevel, DecisionOutcome, PolicyAction,
)


def _make_assessment(**kwargs) -> RiskAssessment:
    defaults = {"risk_score": 0.8, "risk_level": RiskLevel.SEVERE}
    defaults.update(kwargs)
    return RiskAssessment(**defaults)


def _make_decision(**kwargs) -> PolicyDecision:
    defaults = {
        "policy_name": "default-security",
        "outcome": DecisionOutcome.BLOCKED,
        "action": PolicyAction.BLOCK,
        "risk_score": 0.8,
    }
    defaults.update(kwargs)
    return PolicyDecision(**defaults)


class TestReasoningGraphBuilder:
    def test_build_basic(self):
        builder = ReasoningGraphBuilder()
        a = _make_assessment()
        d = _make_decision()
        graph = builder.build(a, d)
        assert isinstance(graph, ReasoningGraph)
        assert len(graph.nodes) > 0
        assert len(graph.edges) > 0

    def test_graph_has_input_node(self):
        builder = ReasoningGraphBuilder()
        a = _make_assessment()
        d = _make_decision()
        graph = builder.build(a, d)
        input_nodes = [n for n in graph.nodes if n.node_type.value == "input"]
        assert len(input_nodes) == 1

    def test_graph_has_policy_node(self):
        builder = ReasoningGraphBuilder()
        a = _make_assessment()
        d = _make_decision()
        graph = builder.build(a, d)
        policy_nodes = [n for n in graph.nodes if n.node_type.value == "policy"]
        assert len(policy_nodes) == 1

    def test_graph_has_action_node(self):
        builder = ReasoningGraphBuilder()
        a = _make_assessment()
        d = _make_decision()
        graph = builder.build(a, d)
        action_nodes = [n for n in graph.nodes if n.node_type.value == "action"]
        assert len(action_nodes) == 1

    def test_graph_has_trust_nodes(self):
        builder = ReasoningGraphBuilder()
        a = _make_assessment()
        a.trust_scores = {"provider-1": TrustScore(provider_id="provider-1", trust_score=0.8)}
        d = _make_decision()
        graph = builder.build(a, d)
        trust_nodes = [n for n in graph.nodes if n.node_type.value == "trust"]
        assert len(trust_nodes) >= 1

    def test_graph_summary(self):
        builder = ReasoningGraphBuilder()
        a = _make_assessment()
        d = _make_decision()
        graph = builder.build(a, d)
        assert "Risk" in graph.summary
        assert "Policy" in graph.summary

    def test_graph_edges_connect(self):
        builder = ReasoningGraphBuilder()
        a = _make_assessment()
        d = _make_decision()
        graph = builder.build(a, d)
        node_ids = {n.node_id for n in graph.nodes}
        for edge in graph.edges:
            assert edge.source_node_id in node_ids
            assert edge.target_node_id in node_ids


class TestReportGenerator:
    def test_generate_structured(self):
        gen = ReportGenerator()
        a = _make_assessment()
        d = _make_decision()
        e = gen.generate(a, d, format=ExplanationFormat.STRUCTURED)
        assert isinstance(e, Explanation)
        assert e.summary
        assert e.why
        assert e.policy_used == "default-security"

    def test_generate_json(self):
        gen = ReportGenerator()
        a = _make_assessment()
        d = _make_decision()
        e = gen.generate(a, d, format=ExplanationFormat.JSON)
        assert "json" in e.export_data

    def test_generate_markdown(self):
        gen = ReportGenerator()
        a = _make_assessment()
        d = _make_decision()
        e = gen.generate(a, d, format=ExplanationFormat.MARKDOWN)
        assert "markdown" in e.export_data
        assert "# Risk Assessment Report" in e.export_data["markdown"]

    def test_generate_text(self):
        gen = ReportGenerator()
        a = _make_assessment()
        d = _make_decision()
        e = gen.generate(a, d, format=ExplanationFormat.TEXT)
        assert "text" in e.export_data
        assert "Risk Assessment Report" in e.export_data["text"]

    def test_generate_with_action_result(self):
        gen = ReportGenerator()
        a = _make_assessment()
        d = _make_decision()
        ar = ActionResult(action_type="block", success=True, message="Blocked")
        e = gen.generate(a, d, action_result=ar)
        assert e.metadata.get("action_success") is True

    def test_generate_with_graph(self):
        gen = ReportGenerator()
        a = _make_assessment()
        d = _make_decision()
        graph = ReasoningGraphBuilder().build(a, d)
        e = gen.generate(a, d, reasoning_graph=graph)
        assert e.reasoning_graph is not None

    def test_confidence_summary(self):
        gen = ReportGenerator()
        a = _make_assessment()
        a.confidence.raw_confidence = 0.85
        a.confidence.normalized_confidence = 0.82
        d = _make_decision()
        e = gen.generate(a, d)
        assert "0.82" in e.confidence_summary

    def test_risk_summary(self):
        gen = ReportGenerator()
        a = _make_assessment()
        d = _make_decision()
        e = gen.generate(a, d)
        assert "Threat score" in e.risk_summary


class TestExplanationEngine:
    def test_explain(self):
        engine = ExplanationEngine()
        a = _make_assessment()
        d = _make_decision()
        e = engine.explain(a, d)
        assert isinstance(e, Explanation)
        assert engine.explanation_count == 1

    def test_explain_with_action(self):
        engine = ExplanationEngine()
        a = _make_assessment()
        d = _make_decision()
        ar = ActionResult(action_type="block", success=True)
        e = engine.explain(a, d, action_result=ar)
        assert e.action_taken == "block"

    def test_explain_json_format(self):
        engine = ExplanationEngine()
        a = _make_assessment()
        d = _make_decision()
        e = engine.explain(a, d, format=ExplanationFormat.JSON)
        assert e.format == ExplanationFormat.JSON

    def test_explain_batch(self):
        engine = ExplanationEngine()
        assessments = [_make_assessment() for _ in range(3)]
        decisions = [_make_decision() for _ in range(3)]
        explanations = engine.explain_batch(assessments, decisions)
        assert len(explanations) == 3
        assert engine.explanation_count == 3

    def test_explain_has_graph(self):
        engine = ExplanationEngine()
        a = _make_assessment()
        d = _make_decision()
        e = engine.explain(a, d)
        assert e.reasoning_graph is not None
        assert len(e.reasoning_graph.nodes) > 0

    def test_explain_which_models(self):
        engine = ExplanationEngine()
        a = _make_assessment()
        a.contributing_sources = ["rule-engine", "ml-model"]
        d = _make_decision()
        e = engine.explain(a, d)
        assert "rule-engine" in e.which_models
        assert "ml-model" in e.which_models
