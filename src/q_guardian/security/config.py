"""Prompt Security Engine configuration for Q-Guardian."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptSecurityConfig(BaseModel):
    """Configuration for the Prompt Security Engine.

    Supports enable/disable, limits, rule configuration,
    severity thresholds, and future ML/Quantum placeholders.
    """

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable prompt security engine")

    # Limits
    max_prompt_length: int = Field(default=100_000, description="Maximum prompt character count")
    min_prompt_length: int = Field(default=1, description="Minimum prompt character count")
    max_lines: int = Field(default=10_000, description="Maximum line count")

    # Rule configuration
    enabled_rules: list[str] = Field(
        default_factory=list,
        description="List of enabled rule IDs (empty = all enabled)",
    )
    disabled_rules: list[str] = Field(
        default_factory=list,
        description="List of disabled rule IDs",
    )
    custom_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Custom rule definitions as dictionaries",
    )

    # Severity thresholds
    block_on_critical: bool = Field(default=True, description="Block when CRITICAL findings exist")
    block_on_high_count: int = Field(
        default=2, description="Block when this many HIGH findings exist"
    )
    review_on_high_count: int = Field(
        default=1, description="REVIEW when this many HIGH findings exist"
    )
    warn_on_medium_count: int = Field(
        default=1, description="WARN when this many MEDIUM findings exist"
    )

    # Logging
    log_findings: bool = Field(default=True, description="Log individual findings")
    log_normalized_prompt: bool = Field(default=False, description="Log the normalized prompt text")

    # Feature extraction
    suspicious_keywords: list[str] | None = Field(
        default=None,
        description="Custom suspicious keywords (null = use defaults)",
    )

    # Future ML configuration placeholders
    ml_enabled: bool = Field(default=False, description="Enable ML-based analysis (future)")
    ml_model_path: str = Field(default="", description="Path to ML model (future)")
    ml_threshold: float = Field(default=0.5, description="ML detection threshold (future)")

    # Future Quantum configuration placeholders
    quantum_enabled: bool = Field(default=False, description="Enable quantum analysis (future)")
    quantum_backend: str = Field(default="", description="Quantum backend name (future)")
