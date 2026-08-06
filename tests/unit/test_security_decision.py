"""Tests for SecurityDecisionEngine."""

from __future__ import annotations

from q_guardian.security.decision import SecurityDecisionEngine
from q_guardian.security.enums import PromptCategory, PromptDecision, PromptSeverity
from q_guardian.security.models import PromptAnalysis, PromptFinding


def _make_finding(
    category: PromptCategory = PromptCategory.PROMPT_INJECTION,
    severity: PromptSeverity = PromptSeverity.MEDIUM,
    confidence: float = 0.8,
) -> PromptFinding:
    return PromptFinding(
        category=category,
        severity=severity,
        confidence=confidence,
        description="test",
    )


class TestSecurityDecisionEngine:
    def setup_method(self) -> None:
        self.engine = SecurityDecisionEngine()

    def test_no_findings_allows(self) -> None:
        analysis = PromptAnalysis(original_prompt="hello", findings=[])
        result = self.engine.decide(analysis)
        assert result.decision == PromptDecision.ALLOW
        assert result.risk_score == 0.0

    def test_critical_blocks(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[_make_finding(severity=PromptSeverity.CRITICAL)],
        )
        result = self.engine.decide(analysis)
        assert result.decision == PromptDecision.BLOCK

    def test_two_high_blocks(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[
                _make_finding(severity=PromptSeverity.HIGH),
                _make_finding(severity=PromptSeverity.HIGH),
            ],
        )
        result = self.engine.decide(analysis)
        assert result.decision == PromptDecision.BLOCK

    def test_single_high_reviews(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[_make_finding(severity=PromptSeverity.HIGH)],
        )
        result = self.engine.decide(analysis)
        assert result.decision == PromptDecision.REVIEW

    def test_medium_warns(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[_make_finding(severity=PromptSeverity.MEDIUM)],
        )
        result = self.engine.decide(analysis)
        assert result.decision == PromptDecision.WARN

    def test_low_only_allows(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[_make_finding(severity=PromptSeverity.LOW)],
        )
        result = self.engine.decide(analysis)
        assert result.decision == PromptDecision.ALLOW

    def test_mixed_severity_high_priority_wins(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[
                _make_finding(severity=PromptSeverity.HIGH),
                _make_finding(severity=PromptSeverity.LOW),
            ],
        )
        result = self.engine.decide(analysis)
        assert result.decision == PromptDecision.REVIEW

    def test_risk_score_computed(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[
                _make_finding(severity=PromptSeverity.MEDIUM, confidence=0.9),
            ],
        )
        result = self.engine.decide(analysis)
        assert 0.0 < result.risk_score <= 1.0

    def test_recommendation_set(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[_make_finding(severity=PromptSeverity.HIGH)],
        )
        result = self.engine.decide(analysis)
        assert result.recommendation != ""

    def test_custom_thresholds(self) -> None:
        engine = SecurityDecisionEngine(
            block_on_critical=False,
            block_on_high_count=5,
            review_on_high_count=3,
            warn_on_medium_count=2,
        )
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[
                _make_finding(severity=PromptSeverity.HIGH),
                _make_finding(severity=PromptSeverity.MEDIUM),
            ],
        )
        result = engine.decide(analysis)
        assert result.decision == PromptDecision.ALLOW

    def test_returns_same_analysis(self) -> None:
        analysis = PromptAnalysis(original_prompt="test")
        result = self.engine.decide(analysis)
        assert result is analysis
