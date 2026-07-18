"""ReasoningGraph — builds directed graphs that explain decision paths.

Each node represents a step in the reasoning process. Edges show
the flow of information from input to final decision.
"""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.risk.data import (
    Explanation,
    PolicyDecision,
    ReasoningEdge,
    ReasoningGraph,
    ReasoningNode,
    RiskAssessment,
)
from q_guardian.risk.enums import ReasoningNodeType

logger = structlog.get_logger("risk.reasoning_graph")


class ReasoningGraphBuilder:
    """Builds reasoning graphs from risk assessment and policy decision data.

    The graph structure:
      INPUT -> SCORING -> CONFIDENCE -> SEVERITY -> RISK -> POLICY -> ACTION -> OUTCOME
    """

    def build(
        self,
        assessment: RiskAssessment,
        decision: PolicyDecision,
    ) -> ReasoningGraph:
        """Build a reasoning graph from an assessment and decision.

        Args:
            assessment: The risk assessment.
            decision: The policy decision.

        Returns:
            Complete ReasoningGraph.
        """
        nodes: list[ReasoningNode] = []
        edges: list[ReasoningEdge] = []

        input_node = ReasoningNode(
            node_type=ReasoningNodeType.INPUT,
            label="Prediction Input",
            description=f"Source: {', '.join(assessment.contributing_sources)}",
            value={
                "prediction_id": assessment.prediction_id,
                "sources": assessment.contributing_sources,
            },
        )
        nodes.append(input_node)

        scoring_node = ReasoningNode(
            node_type=ReasoningNodeType.PROCESS,
            label="Threat Scoring",
            description=f"Threat score: {assessment.threat_score.threat_score:.4f}",
            value=assessment.threat_score.model_dump(),
            confidence=assessment.confidence.normalized_confidence,
        )
        nodes.append(scoring_node)
        edges.append(ReasoningEdge(
            source_node_id=input_node.node_id,
            target_node_id=scoring_node.node_id,
            label="scored by",
        ))

        conf_node = ReasoningNode(
            node_type=ReasoningNodeType.CONFIDENCE,
            label="Confidence Normalization",
            description=f"Confidence: {assessment.confidence.normalized_confidence:.4f}",
            value=assessment.confidence.model_dump(),
            confidence=assessment.confidence.normalized_confidence,
        )
        nodes.append(conf_node)
        edges.append(ReasoningEdge(
            source_node_id=scoring_node.node_id,
            target_node_id=conf_node.node_id,
            label="calibrated",
        ))

        sev_node = ReasoningNode(
            node_type=ReasoningNodeType.RISK,
            label="Severity Classification",
            description=f"Severity: {assessment.severity.severity.value}",
            value=assessment.severity.model_dump(),
        )
        nodes.append(sev_node)
        edges.append(ReasoningEdge(
            source_node_id=conf_node.node_id,
            target_node_id=sev_node.node_id,
            label="classified",
        ))

        risk_node = ReasoningNode(
            node_type=ReasoningNodeType.RISK,
            label="Risk Assessment",
            description=f"Risk: {assessment.risk_score:.4f} ({assessment.risk_level.value})",
            value={"risk_score": assessment.risk_score, "risk_level": assessment.risk_level.value},
        )
        nodes.append(risk_node)
        edges.append(ReasoningEdge(
            source_node_id=sev_node.node_id,
            target_node_id=risk_node.node_id,
            label="determines risk",
        ))

        for provider_id, ts in assessment.trust_scores.items():
            trust_node = ReasoningNode(
                node_type=ReasoningNodeType.TRUST,
                label=f"Trust: {provider_id}",
                description=f"Trust: {ts.trust_score:.4f} ({ts.trust_level.value})",
                value=ts.model_dump(),
                confidence=ts.trust_score,
            )
            nodes.append(trust_node)
            edges.append(ReasoningEdge(
                source_node_id=scoring_node.node_id,
                target_node_id=trust_node.node_id,
                label="provider trust",
            ))

        policy_node = ReasoningNode(
            node_type=ReasoningNodeType.POLICY,
            label=f"Policy: {decision.policy_name}",
            description=f"Matched {len(decision.matched_rules)} rules",
            value={
                "policy_name": decision.policy_name,
                "matched_rules": decision.matched_rules,
                "action": decision.action.value,
            },
        )
        nodes.append(policy_node)
        edges.append(ReasoningEdge(
            source_node_id=risk_node.node_id,
            target_node_id=policy_node.node_id,
            label="evaluated by",
        ))

        action_node = ReasoningNode(
            node_type=ReasoningNodeType.ACTION,
            label=f"Action: {decision.action.value}",
            description=f"Outcome: {decision.outcome.value}",
            value={
                "action": decision.action.value,
                "outcome": decision.outcome.value,
                "severity": decision.severity.value,
            },
        )
        nodes.append(action_node)
        edges.append(ReasoningEdge(
            source_node_id=policy_node.node_id,
            target_node_id=action_node.node_id,
            label="prescribes",
        ))

        summary = (
            f"Risk {assessment.risk_score:.2f} ({assessment.risk_level.value}) "
            f"-> Policy '{decision.policy_name}' -> {decision.action.value} "
            f"({decision.outcome.value})"
        )

        graph = ReasoningGraph(
            assessment_id=assessment.assessment_id,
            nodes=nodes,
            edges=edges,
            summary=summary,
        )

        logger.debug(
            "reasoning_graph_built",
            graph_id=graph.graph_id,
            nodes=len(nodes),
            edges=len(edges),
        )

        return graph
