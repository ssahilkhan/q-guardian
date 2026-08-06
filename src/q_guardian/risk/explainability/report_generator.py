"""ReportGenerator — generates human-readable and JSON reports."""

from __future__ import annotations

import structlog

from q_guardian.risk.data import (
    ActionResult,
    Explanation,
    PolicyDecision,
    ReasoningGraph,
    RiskAssessment,
)
from q_guardian.risk.enums import ExplanationFormat

logger = structlog.get_logger("risk.report_generator")


class ReportGenerator:
    """Generates explainability reports in multiple formats.

    Supports:
      - STRUCTURED: dict-based format
      - JSON: serialized JSON string
      - TEXT: human-readable plain text
      - MARKDOWN: Markdown-formatted text
    """

    def generate(
        self,
        assessment: RiskAssessment,
        decision: PolicyDecision,
        action_result: ActionResult | None = None,
        reasoning_graph: ReasoningGraph | None = None,
        explanation_format: ExplanationFormat = ExplanationFormat.STRUCTURED,
    ) -> Explanation:
        """Generate a complete explanation report.

        Args:
            assessment: The risk assessment.
            decision: The policy decision.
            action_result: Optional action execution result.
            reasoning_graph: Optional reasoning graph.
            explanation_format: Output format.

        Returns:
            Complete Explanation.
        """
        summary = self._build_summary(assessment, decision)
        why = self._build_why(assessment, decision)
        which_models = assessment.contributing_sources
        confidence_summary = self._build_confidence_summary(assessment)
        risk_summary = self._build_risk_summary(assessment)

        explanation = Explanation(
            assessment_id=assessment.assessment_id,
            decision_id=decision.decision_id,
            summary=summary,
            why=why,
            which_models=which_models,
            confidence_summary=confidence_summary,
            risk_summary=risk_summary,
            policy_used=decision.policy_name,
            action_taken=decision.action.value,
            reasoning_graph=reasoning_graph,
            format=explanation_format,
        )

        if action_result is not None:
            explanation.metadata["action_success"] = action_result.success
            explanation.metadata["action_message"] = action_result.message

        if explanation_format == ExplanationFormat.JSON:
            explanation.export_data = {"json": explanation.model_dump_json(indent=2)}
        elif explanation_format == ExplanationFormat.MARKDOWN:
            explanation.export_data = {"markdown": self._to_markdown(explanation)}
        elif explanation_format == ExplanationFormat.TEXT:
            explanation.export_data = {"text": self._to_text(explanation)}
        else:
            explanation.export_data = explanation.model_dump()

        logger.debug(
            "explanation_generated",
            explanation_id=explanation.explanation_id,
            format=explanation_format.value,
        )

        return explanation

    def _build_summary(self, assessment: RiskAssessment, decision: PolicyDecision) -> str:
        return (
            f"Risk assessment {assessment.assessment_id[:8]}: "
            f"score={assessment.risk_score:.4f}, level={assessment.risk_level.value}, "
            f"severity={assessment.severity.severity.value}. "
            f"Policy '{decision.policy_name}' -> {decision.action.value} "
            f"({decision.outcome.value})."
        )

    def _build_why(self, assessment: RiskAssessment, decision: PolicyDecision) -> str:
        reasons = []
        if assessment.risk_score >= 0.7:
            reasons.append(f"High risk score ({assessment.risk_score:.4f})")
        elif assessment.risk_score >= 0.4:
            reasons.append(f"Moderate risk score ({assessment.risk_score:.4f})")
        else:
            reasons.append(f"Low risk score ({assessment.risk_score:.4f})")

        if assessment.severity.severity.value in ("high", "critical"):
            reasons.append(f"Severity classified as {assessment.severity.severity.value}")

        if decision.matched_rules:
            reasons.append(f"{len(decision.matched_rules)} policy rule(s) matched")

        return "; ".join(reasons) if reasons else "Standard processing"

    def _build_confidence_summary(self, assessment: RiskAssessment) -> str:
        c = assessment.confidence
        interval_str = ""
        if c.confidence_interval:
            interval_str = (
                f" (95% CI: [{c.confidence_interval[0]:.4f}, {c.confidence_interval[1]:.4f}])"
            )
        return (
            f"Confidence: {c.normalized_confidence:.4f} (raw: {c.raw_confidence:.4f}){interval_str}"
        )

    def _build_risk_summary(self, assessment: RiskAssessment) -> str:
        ts = assessment.threat_score
        return (
            f"Threat score: {ts.threat_score:.4f} ({ts.threat_level.value}). "
            f"Components: probability={ts.probability_component:.4f}, "
            f"confidence={ts.confidence_component:.4f}, "
            f"reliability={ts.reliability_component:.4f}."
        )

    def _to_markdown(self, explanation: Explanation) -> str:
        lines = [
            "# Risk Assessment Report",
            "",
            f"**Assessment ID:** {explanation.assessment_id}",
            f"**Decision ID:** {explanation.decision_id}",
            f"**Timestamp:** {explanation.timestamp.isoformat()}",
            "",
            "## Summary",
            explanation.summary,
            "",
            "## Why",
            explanation.why,
            "",
            "## Confidence",
            explanation.confidence_summary,
            "",
            "## Risk",
            explanation.risk_summary,
            "",
            f"**Policy:** {explanation.policy_used}",
            f"**Action:** {explanation.action_taken}",
            "",
            "## Contributing Models",
        ]
        for model in explanation.which_models:
            lines.append(f"- {model}")
        return "\n".join(lines)

    def _to_text(self, explanation: Explanation) -> str:
        lines = [
            f"Risk Assessment Report - {explanation.assessment_id}",
            "=" * 60,
            explanation.summary,
            "",
            "WHY:",
            explanation.why,
            "",
            "CONFIDENCE:",
            explanation.confidence_summary,
            "",
            "RISK:",
            explanation.risk_summary,
            "",
            f"POLICY: {explanation.policy_used}",
            f"ACTION: {explanation.action_taken}",
        ]
        return "\n".join(lines)
