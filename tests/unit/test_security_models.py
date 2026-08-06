"""Tests for prompt security models and configuration."""

from __future__ import annotations

import copy

from q_guardian.security.config import PromptSecurityConfig
from q_guardian.security.enums import (
    PromptCategory,
    PromptDecision,
    PromptSeverity,
    ValidationStatus,
)
from q_guardian.security.events import (
    PromptAllowed,
    PromptAnalysisCompleted,
    PromptBlocked,
    PromptFeaturesExtracted,
    PromptNormalized,
    PromptRuleMatched,
    PromptValidated,
)
from q_guardian.security.extensibility import DetectionResult
from q_guardian.security.models import (
    PromptAnalysis,
    PromptFeatures,
    PromptFinding,
    PromptRule,
)


class TestPromptFeatures:
    def test_defaults(self) -> None:
        f = PromptFeatures()
        assert f.length == 0
        assert f.entropy == 0.0

    def test_json_roundtrip(self) -> None:
        f = PromptFeatures(length=100, word_count=20, entropy=3.5)
        data = f.model_dump()
        restored = PromptFeatures.model_validate(data)
        assert restored.length == 100
        assert restored.entropy == 3.5

    def test_deep_copy(self) -> None:
        f = PromptFeatures(suspicious_keywords=["test"])
        copied = copy.deepcopy(f)
        copied.suspicious_keywords.append("new")
        assert len(f.suspicious_keywords) == 1


class TestPromptFinding:
    def test_defaults(self) -> None:
        finding = PromptFinding()
        assert finding.category == PromptCategory.UNKNOWN
        assert finding.severity == PromptSeverity.LOW
        assert isinstance(finding.finding_id, str)

    def test_json_roundtrip(self) -> None:
        finding = PromptFinding(
            rule_id="r1",
            category=PromptCategory.JAILBREAK,
            severity=PromptSeverity.HIGH,
            confidence=0.95,
        )
        data = finding.model_dump()
        restored = PromptFinding.model_validate(data)
        assert restored.category == PromptCategory.JAILBREAK
        assert restored.confidence == 0.95


class TestPromptRule:
    def test_defaults(self) -> None:
        rule = PromptRule(name="test")
        assert rule.enabled is True
        assert rule.severity == PromptSeverity.MEDIUM

    def test_json_roundtrip(self) -> None:
        rule = PromptRule(
            rule_id="r1",
            name="test",
            keywords=["k1", "k2"],
            patterns=[r"\d+"],
        )
        data = rule.model_dump()
        restored = PromptRule.model_validate(data)
        assert len(restored.keywords) == 2


class TestPromptAnalysis:
    def test_defaults(self) -> None:
        analysis = PromptAnalysis(original_prompt="hello")
        assert analysis.decision == PromptDecision.ALLOW
        assert analysis.risk_score == 0.0

    def test_finding_count(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[
                PromptFinding(severity=PromptSeverity.LOW),
                PromptFinding(severity=PromptSeverity.HIGH),
            ],
        )
        assert analysis.finding_count == 2
        assert analysis.high_severity_count == 1

    def test_to_security_dict(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            findings=[PromptFinding(severity=PromptSeverity.CRITICAL)],
            decision=PromptDecision.BLOCK,
            risk_score=0.9,
        )
        d = analysis.to_security_dict()
        assert d["blocked"] is True
        assert d["decision"] == "block"
        assert d["risk_score"] == 0.9

    def test_json_roundtrip(self) -> None:
        analysis = PromptAnalysis(
            original_prompt="test",
            risk_score=0.5,
        )
        data = analysis.model_dump()
        restored = PromptAnalysis.model_validate(data)
        assert restored.risk_score == 0.5


class TestPromptSecurityConfig:
    def test_defaults(self) -> None:
        config = PromptSecurityConfig()
        assert config.enabled is True
        assert config.max_prompt_length == 100_000
        assert config.block_on_critical is True

    def test_custom_config(self) -> None:
        config = PromptSecurityConfig(
            enabled=False,
            max_prompt_length=500,
            block_on_high_count=3,
        )
        assert config.enabled is False
        assert config.max_prompt_length == 500
        assert config.block_on_high_count == 3

    def test_json_roundtrip(self) -> None:
        config = PromptSecurityConfig(ml_enabled=True, ml_threshold=0.7)
        data = config.model_dump()
        restored = PromptSecurityConfig.model_validate(data)
        assert restored.ml_enabled is True
        assert restored.ml_threshold == 0.7

    def test_future_placeholders(self) -> None:
        config = PromptSecurityConfig()
        assert config.ml_enabled is False
        assert config.quantum_enabled is False


class TestSecurityEvents:
    def test_all_events_types(self) -> None:
        events = [
            PromptNormalized(source="test"),
            PromptValidated(source="test"),
            PromptFeaturesExtracted(source="test"),
            PromptRuleMatched(source="test"),
            PromptAnalysisCompleted(source="test"),
            PromptBlocked(source="test"),
            PromptAllowed(source="test"),
        ]
        for e in events:
            assert e.event_type.startswith("security.prompt.")

    def test_event_serialization(self) -> None:
        e = PromptBlocked(source="plugin", data={"blocked": True})
        d = e.model_dump()
        assert d["data"]["blocked"] is True


class TestDetectionResult:
    def test_defaults(self) -> None:
        r = DetectionResult(detector_name="test")
        assert r.risk_score == 0.0
        assert r.confidence == 0.0
        assert r.findings == []


class TestEnums:
    def test_prompt_severity_values(self) -> None:
        assert PromptSeverity.INFO.value == "info"
        assert PromptSeverity.CRITICAL.value == "critical"

    def test_prompt_category_values(self) -> None:
        assert PromptCategory.PROMPT_INJECTION.value == "prompt_injection"
        assert PromptCategory.JAILBREAK.value == "jailbreak"

    def test_prompt_decision_values(self) -> None:
        assert PromptDecision.ALLOW.value == "allow"
        assert PromptDecision.BLOCK.value == "block"

    def test_validation_status_values(self) -> None:
        assert ValidationStatus.VALID.value == "valid"
        assert ValidationStatus.INVALID.value == "invalid"
