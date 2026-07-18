"""Security Decision Engine for Q-Guardian.

Makes ALLOW/WARN/REVIEW/BLOCK decisions based on analysis results.
Currently rule-based only; ML integration is a future extension point.
"""

from __future__ import annotations

from typing import Any

from q_guardian.security.enums import PromptDecision, PromptSeverity
from q_guardian.security.models import PromptAnalysis, PromptFinding


class SecurityDecisionEngine:
    """Makes security decisions based on prompt analysis findings.

    Decision logic (rule-based):
    - CRITICAL findings → BLOCK
    - Multiple HIGH findings → BLOCK
    - Single HIGH finding → REVIEW
    - MEDIUM findings → WARN
    - Low findings only → ALLOW
    - No findings → ALLOW

    Future ML integration:
      ML classifiers will provide an additional risk score that
      is combined with rule-based findings. The decision engine
      will weight both sources.

    Future Quantum integration:
      Quantum analysis results will be merged as an additional
      factor in the decision scoring.
    """

    def __init__(
        self,
        block_on_critical: bool = True,
        block_on_high_count: int = 2,
        review_on_high_count: int = 1,
        warn_on_medium_count: int = 1,
    ) -> None:
        """Initialize the decision engine.

        Args:
            block_on_critical: Block if any CRITICAL finding exists.
            block_on_high_count: Block if this many HIGH findings exist.
            review_on_high_count: REVIEW if this many HIGH findings exist.
            warn_on_medium_count: WARN if this many MEDIUM findings exist.
        """
        self._block_on_critical = block_on_critical
        self._block_on_high_count = block_on_high_count
        self._review_on_high_count = review_on_high_count
        self._warn_on_medium_count = warn_on_medium_count

    def decide(self, analysis: PromptAnalysis) -> PromptAnalysis:
        """Make a security decision based on analysis findings.

        Updates the analysis in-place with the decision, risk score,
        and recommendation. Returns the updated analysis.

        Args:
            analysis: The PromptAnalysis with findings populated.

        Returns:
            The same PromptAnalysis with decision fields updated.
        """
        findings = analysis.findings

        # No findings → ALLOW
        if not findings:
            analysis.decision = PromptDecision.ALLOW
            analysis.risk_score = 0.0
            analysis.recommendation = "No security concerns detected."
            return analysis

        # Count by severity
        severity_counts = self._count_by_severity(findings)

        critical = severity_counts.get(PromptSeverity.CRITICAL, 0)
        high = severity_counts.get(PromptSeverity.HIGH, 0)
        medium = severity_counts.get(PromptSeverity.MEDIUM, 0)
        low = severity_counts.get(PromptSeverity.LOW, 0)

        # Compute risk score (0-1)
        analysis.risk_score = self._compute_risk_score(findings)

        # Decision cascade
        if self._block_on_critical and critical > 0:
            analysis.decision = PromptDecision.BLOCK
            analysis.recommendation = (
                f"BLOCK: {critical} critical severity finding(s) detected."
            )
        elif high >= self._block_on_high_count:
            analysis.decision = PromptDecision.BLOCK
            analysis.recommendation = (
                f"BLOCK: {high} high severity finding(s) exceed threshold."
            )
        elif high >= self._review_on_high_count:
            analysis.decision = PromptDecision.REVIEW
            analysis.recommendation = (
                f"REVIEW: {high} high severity finding(s) require review."
            )
        elif medium >= self._warn_on_medium_count:
            analysis.decision = PromptDecision.WARN
            analysis.recommendation = (
                f"WARN: {medium} medium severity finding(s) detected."
            )
        else:
            analysis.decision = PromptDecision.ALLOW
            analysis.recommendation = (
                "ALLOW: Findings are low severity; prompt is likely safe."
            )

        return analysis

    def _count_by_severity(
        self, findings: list[PromptFinding]
    ) -> dict[PromptSeverity, int]:
        """Count findings by severity level.

        Args:
            findings: List of findings.

        Returns:
            Dictionary mapping severity to count.
        """
        counts: dict[PromptSeverity, int] = {}
        for f in findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts

    def _compute_risk_score(self, findings: list[PromptFinding]) -> float:
        """Compute a risk score from findings.

        Uses weighted scoring based on severity and confidence.

        Args:
            findings: List of findings.

        Returns:
            Risk score between 0.0 and 1.0.
        """
        if not findings:
            return 0.0

        severity_weights = {
            PromptSeverity.INFO: 0.1,
            PromptSeverity.LOW: 0.2,
            PromptSeverity.MEDIUM: 0.5,
            PromptSeverity.HIGH: 0.8,
            PromptSeverity.CRITICAL: 1.0,
        }

        total = 0.0
        for f in findings:
            weight = severity_weights.get(f.severity, 0.1)
            total += weight * f.confidence

        # Normalize to 0-1 using diminishing returns (log scale)
        import math

        raw = total / len(findings)
        # Apply sigmoid-like scaling for better distribution
        score = min(1.0, raw * 1.2)

        return round(score, 4)
