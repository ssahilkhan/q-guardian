"""Prompt Security Engine configuration for Q-Guardian."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IndirectInjectionConfig(BaseModel):
    """Configuration for indirect prompt injection detection (P3-5).

    Controls how untrusted content segments (tool outputs, RAG context,
    retrieved documents, ...) are analyzed for injection directives.
    Detection only runs on segments explicitly marked as untrusted;
    ordinary direct prompt analysis is never affected.
    """

    enabled: bool = Field(
        default=True,
        description="Enable indirect injection detection on untrusted segments",
    )
    trusted_sources: list[str] = Field(
        default_factory=list,
        description=(
            "Allowlist treated as trusted: exact source_id matches, exact uri "
            "matches, or uri prefix matches for entries ending with '/'"
        ),
    )
    segment_max_bytes: int = Field(
        default=50_000,
        ge=1,
        description="Maximum segment content size (bytes) before truncation",
    )
    max_segments: int = Field(
        default=64,
        ge=0,
        description="Maximum number of untrusted segments analyzed per scan",
    )
    confidence_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Per-source-type confidence weights; empty uses module defaults",
    )
    quote_discount: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence multiplier for quoted/attributed directive text",
    )
    code_discount: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence multiplier for matches inside fenced code blocks",
    )
    disabled_rules: list[str] = Field(
        default_factory=list,
        description="ii-* rule IDs excluded from standalone detection",
    )


class OutputMonitoringConfig(BaseModel):
    """Configuration for output monitoring (P3-3).

    Controls analysis of agent/model output text for leakage, sensitive
    data exposure, actionable commands, obfuscated payloads, and
    propagation of untrusted content. The ``om-*`` rules are
    direction-gated: they never fire on ordinary prompt scans.
    """

    enabled: bool = Field(
        default=True,
        description="Enable output monitoring when an output scan is requested",
    )
    max_output_length: int = Field(
        default=100_000,
        ge=1,
        description="Maximum output character count analyzed per scan",
    )
    disabled_rules: list[str] = Field(
        default_factory=list,
        description="om-* rule IDs excluded from output monitoring",
    )
    secret_entropy_threshold: float = Field(
        default=3.0,
        ge=0.0,
        le=8.0,
        description="Minimum Shannon entropy (bits/char) for entropy-gated secrets",
    )
    quote_discount: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence multiplier for quoted/attributed matches",
    )
    code_discount: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence multiplier for matches inside fenced code blocks",
    )
    max_decoded_variants: int = Field(
        default=4,
        ge=0,
        description="Maximum decoded payload variants inspected by om-006",
    )
    decoded_preview_chars: int = Field(
        default=5000,
        ge=1,
        description="Maximum characters retained per decoded variant",
    )
    correlation_shingle_words: int = Field(
        default=5,
        ge=2,
        description="Word n-gram size used by om-007 propagation correlation",
    )
    correlation_min_shingles: int = Field(
        default=6,
        ge=1,
        description="Minimum matching shingles before om-007 fires",
    )
    correlation_overlap_threshold: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Minimum shingle containment ratio for om-007",
    )


class MultiTurnConfig(BaseModel):
    """Configuration for multi-turn / session-level threat detection (P3-4).

    Controls analysis of conversation history across multiple turns to
    detect split injection, progressive escalation, and other
    cross-turn attack patterns.  The ``mt-*`` rules are session-gated:
    they never fire on ordinary single-turn prompt scans.
    """

    enabled: bool = Field(
        default=False,
        description="Enable multi-turn threat detection (opt-in per session)",
    )
    window_size: int = Field(
        default=20,
        ge=2,
        le=200,
        description="Maximum number of most-recent turns analysed per scan",
    )
    max_total_length: int = Field(
        default=200_000,
        ge=1_000,
        description="Maximum total character count across the turn window",
    )
    confidence_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for a finding to be emitted",
    )
    disabled_rules: list[str] = Field(
        default_factory=list,
        description="mt-* rule IDs excluded from multi-turn detection",
    )


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

    # Encoding detection configuration
    encoding_detection_enabled: bool = Field(
        default=True, description="Enable encoding detection (Base64, ROT13, Hex, URL)"
    )
    encoding_max_depth: int = Field(default=3, description="Maximum recursive decoding depth")
    encoding_max_decoded_length: int = Field(
        default=50_000, description="Maximum decoded content length per attempt"
    )
    encoding_max_attempts: int = Field(default=4, description="Maximum decoding attempts per input")

    # Indirect injection detection (P3-5)
    indirect: IndirectInjectionConfig = Field(
        default_factory=IndirectInjectionConfig,
        description="Indirect prompt injection detection configuration",
    )

    # Output monitoring (P3-3)
    output: OutputMonitoringConfig = Field(
        default_factory=OutputMonitoringConfig,
        description="Agent output monitoring configuration",
    )

    # Multi-turn detection (P3-4)
    multiturn: MultiTurnConfig = Field(
        default_factory=MultiTurnConfig,
        description="Multi-turn / session-level threat detection configuration",
    )

    # Future ML configuration placeholders
    ml_enabled: bool = Field(default=False, description="Enable ML-based analysis (future)")
    ml_model_path: str = Field(default="", description="Path to ML model (future)")
    ml_threshold: float = Field(default=0.5, description="ML detection threshold (future)")

    # Future Quantum configuration placeholders
    quantum_enabled: bool = Field(default=False, description="Enable quantum analysis (future)")
    quantum_backend: str = Field(default="", description="Quantum backend name (future)")
