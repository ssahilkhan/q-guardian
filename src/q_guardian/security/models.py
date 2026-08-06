"""Prompt security models for Q-Guardian.

Defines the domain models for prompt analysis, feature extraction,
rule matching, and security decisions. These models are the data
contract between pipeline stages.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.security.enums import (
    PromptCategory,
    PromptDecision,
    PromptSeverity,
    ValidationStatus,
)
from q_guardian.utils.uuid_utils import generate_uuid


class PromptFeatures(BaseModel):
    """Structured features extracted from a prompt.

    Populated by PromptFeatureExtractor. Used by RuleEngine for
    rule matching and by future ML modules for classification.
    """

    model_config = ConfigDict(populate_by_name=True)

    length: int = Field(default=0, description="Character count")
    word_count: int = Field(default=0, description="Word count")
    line_count: int = Field(default=0, description="Line count")
    token_estimate: int = Field(default=0, description="Estimated token count (~4 chars/token)")
    special_char_count: int = Field(default=0, description="Count of non-alphanumeric characters")
    code_block_count: int = Field(default=0, description="Number of fenced code blocks")
    url_count: int = Field(default=0, description="Number of URLs found")
    markdown_usage: bool = Field(default=False, description="Whether markdown syntax is present")
    repeated_patterns: list[str] = Field(default_factory=list, description="Repeated substrings")
    entropy: float = Field(default=0.0, description="Shannon entropy estimate (0-5)")
    suspicious_keywords: list[str] = Field(
        default_factory=list, description="Matched suspicious keywords"
    )
    has_unicode_escaped: bool = Field(
        default=False, description="Contains unicode escape sequences"
    )
    has_html_tags: bool = Field(default=False, description="Contains HTML/XML tags")
    uppercase_ratio: float = Field(default=0.0, description="Ratio of uppercase characters")
    digit_ratio: float = Field(default=0.0, description="Ratio of digit characters")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional feature data")


class PromptFinding(BaseModel):
    """A single finding from prompt analysis.

    Created by RuleEngine when a rule matches. Contains all
    information needed for the security decision and audit trail.
    """

    model_config = ConfigDict(populate_by_name=True)

    finding_id: str = Field(default_factory=generate_uuid, description="Unique finding ID")
    rule_id: str = Field(default="", description="Rule that produced this finding")
    rule_name: str = Field(default="", description="Human-readable rule name")
    category: PromptCategory = Field(default=PromptCategory.UNKNOWN, description="Finding category")
    severity: PromptSeverity = Field(default=PromptSeverity.LOW, description="Finding severity")
    description: str = Field(default="", description="Description of the finding")
    matched_text: str = Field(default="", description="The text that triggered the match")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Detection confidence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional finding data")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Finding timestamp"
    )


class PromptRule(BaseModel):
    """Definition of a detection rule.

    Rules are used by RuleEngine to scan prompts. Each rule
    defines patterns, categories, severity, and metadata.
    """

    model_config = ConfigDict(populate_by_name=True)

    rule_id: str = Field(default_factory=generate_uuid, description="Unique rule ID")
    name: str = Field(description="Rule name")
    description: str = Field(default="", description="Rule description")
    category: PromptCategory = Field(default=PromptCategory.UNKNOWN, description="Rule category")
    severity: PromptSeverity = Field(default=PromptSeverity.MEDIUM, description="Default severity")
    patterns: list[str] = Field(default_factory=list, description="Regex patterns to match")
    keywords: list[str] = Field(default_factory=list, description="Case-insensitive keywords")
    enabled: bool = Field(default=True, description="Whether rule is active")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Base confidence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional rule data")


class PromptAnalysis(BaseModel):
    """Complete result of prompt analysis.

    Aggregates all pipeline outputs: normalized text, features,
    findings, decision, and recommendation. This is the primary
    output of the Prompt Security Engine.
    """

    model_config = ConfigDict(populate_by_name=True)

    analysis_id: str = Field(default_factory=generate_uuid, description="Unique analysis ID")
    original_prompt: str = Field(description="Original prompt text")
    normalized_prompt: str = Field(default="", description="Normalized prompt text")
    is_valid: bool = Field(default=True, description="Whether prompt passed validation")
    validation_status: ValidationStatus = Field(
        default=ValidationStatus.VALID, description="Validation status"
    )
    validation_errors: list[str] = Field(
        default_factory=list, description="Validation error messages"
    )
    features: PromptFeatures = Field(
        default_factory=PromptFeatures, description="Extracted features"
    )
    findings: list[PromptFinding] = Field(default_factory=list, description="Detection findings")
    decision: PromptDecision = Field(default=PromptDecision.ALLOW, description="Security decision")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Computed risk score")
    recommendation: str = Field(default="", description="Human-readable recommendation")
    processing_time_ms: float = Field(default=0.0, description="Total processing time in ms")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional analysis data")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Analysis timestamp"
    )

    @property
    def finding_count(self) -> int:
        """Return the number of findings."""
        return len(self.findings)

    @property
    def high_severity_count(self) -> int:
        """Return the number of high/critical severity findings."""
        return sum(
            1 for f in self.findings if f.severity in (PromptSeverity.HIGH, PromptSeverity.CRITICAL)
        )

    def to_security_dict(self) -> dict[str, Any]:
        """Convert to a dictionary suitable for SecurityContext update.

        Returns:
            Dictionary with risk_score, findings, blocked, etc.
        """
        return {
            "risk_score": self.risk_score,
            "decision": self.decision.value,
            "finding_count": self.finding_count,
            "high_severity_count": self.high_severity_count,
            "blocked": self.decision == PromptDecision.BLOCK,
            "recommendation": self.recommendation,
            "categories": list({f.category.value for f in self.findings}),
        }
