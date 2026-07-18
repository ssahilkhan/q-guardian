"""ExplanationEngine — top-level orchestrator for explainability."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.risk.data import ActionResult, Explanation, PolicyDecision, RiskAssessment
from q_guardian.risk.enums import ExplanationFormat
from q_guardian.risk.explainability.reasoning_graph import ReasoningGraphBuilder
from q_guardian.risk.explainability.report_generator import ReportGenerator

logger = structlog.get_logger("risk.explanation_engine")


class ExplanationEngine:
    """Orchestrates explainability for risk decisions.

    Produces complete Explanation objects with reasoning graphs,
    summaries, and exportable reports.
    """

    def __init__(self) -> None:
        self._graph_builder = ReasoningGraphBuilder()
        self._report_generator = ReportGenerator()
        self._explanation_count = 0

    @property
    def explanation_count(self) -> int:
        return self._explanation_count

    def explain(
        self,
        assessment: RiskAssessment,
        decision: PolicyDecision,
        action_result: ActionResult | None = None,
        format: ExplanationFormat = ExplanationFormat.STRUCTURED,
    ) -> Explanation:
        """Generate a complete explanation for a risk decision.

        Args:
            assessment: The risk assessment.
            decision: The policy decision.
            action_result: Optional action execution result.
            format: Output format.

        Returns:
            Complete Explanation.
        """
        self._explanation_count += 1

        graph = self._graph_builder.build(assessment, decision)

        explanation = self._report_generator.generate(
            assessment=assessment,
            decision=decision,
            action_result=action_result,
            reasoning_graph=graph,
            format=format,
        )

        logger.info(
            "explanation_generated",
            explanation_id=explanation.explanation_id,
            assessment_id=assessment.assessment_id,
            format=format.value,
        )

        return explanation

    def explain_batch(
        self,
        assessments: list[RiskAssessment],
        decisions: list[PolicyDecision],
        format: ExplanationFormat = ExplanationFormat.STRUCTURED,
    ) -> list[Explanation]:
        """Generate explanations for a batch of assessments and decisions."""
        return [
            self.explain(a, d, format=format)
            for a, d in zip(assessments, decisions)
        ]
