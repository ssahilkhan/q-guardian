"""Enumerations for the Prompt Security Engine."""

from __future__ import annotations

from enum import Enum


class PromptSeverity(str, Enum):
    """Severity level of a prompt finding."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PromptCategory(str, Enum):
    """Category of detected prompt issue."""

    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    ROLE_MANIPULATION = "role_manipulation"
    SYSTEM_PROMPT_LEAK = "system_prompt_leak"
    DATA_EXFILTRATION = "data_exfiltration"
    EXCESSIVE_ENCODING = "excessive_encoding"
    SUSPICIOUS_FORMATTING = "suspicious_formatting"
    OVERSIZED_PROMPT = "oversized_prompt"
    MALFORMED_INPUT = "malformed_input"
    UNKNOWN = "unknown"


class PromptDecision(str, Enum):
    """Security decision for a prompt."""

    ALLOW = "allow"
    WARN = "warn"
    REVIEW = "review"
    BLOCK = "block"


class ValidationStatus(str, Enum):
    """Result of prompt validation."""

    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
