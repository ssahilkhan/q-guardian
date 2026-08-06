"""Prompt security pipeline components for Q-Guardian.

Implements the modular prompt analysis pipeline:
  Normalizer → Validator → FeatureExtractor → RuleEngine

Each component is independent and can be used separately.
"""

from __future__ import annotations

import math
import re
import unicodedata

import structlog

from q_guardian.security.enums import PromptCategory, PromptSeverity, ValidationStatus
from q_guardian.security.models import (
    PromptFeatures,
    PromptFinding,
    PromptRule,
)

logger = structlog.get_logger("security.pipeline")


# ---------------------------------------------------------------------------
# PromptNormalizer
# ---------------------------------------------------------------------------


class PromptNormalizer:
    """Normalizes prompt text for consistent analysis.

    Responsibilities:
    - trim whitespace
    - normalize unicode (NFKC normalization)
    - remove hidden/invisible characters
    - normalize line endings to \\n
    - preserve semantic meaning
    """

    # Unicode category codes for invisible/control characters to strip
    _HIDDEN_CATEGORIES: frozenset[str] = frozenset({"Cf", "Cc"})

    def normalize(self, prompt: str) -> str:
        """Normalize a prompt string.

        Args:
            prompt: Raw prompt text.

        Returns:
            Normalized prompt text.
        """
        if not prompt:
            return ""

        # 1. Unicode NFKC normalization (compatibility decomposition + composition)
        text = unicodedata.normalize("NFKC", prompt)

        # 2. Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # 3. Remove hidden/invisible characters (except common whitespace)
        text = self._remove_hidden_chars(text)

        # 4. Trim leading/trailing whitespace
        text = text.strip()

        # 5. Collapse multiple spaces to single space (preserve newlines)
        text = re.sub(r"[^\S\n]+", " ", text)

        # 6. Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text

    def _remove_hidden_chars(self, text: str) -> str:
        """Remove invisible/control characters while preserving structure.

        Args:
            text: Input text.

        Returns:
            Text with hidden characters removed.
        """
        result: list[str] = []
        for char in text:
            if char in ("\n", "\t"):
                result.append(char)
                continue
            cat = unicodedata.category(char)
            if cat not in self._HIDDEN_CATEGORIES:
                result.append(char)
        return "".join(result)


# ---------------------------------------------------------------------------
# PromptValidator
# ---------------------------------------------------------------------------


class PromptValidator:
    """Validates prompt input against configurable limits.

    Validates:
    - empty prompts
    - oversized prompts
    - malformed encoding
    - invalid structure
    - configurable limits
    """

    def __init__(
        self,
        max_length: int = 100_000,
        min_length: int = 1,
        max_lines: int = 10_000,
    ) -> None:
        """Initialize the validator.

        Args:
            max_length: Maximum prompt character count.
            min_length: Minimum prompt character count.
            max_lines: Maximum line count.
        """
        self._max_length = max_length
        self._min_length = min_length
        self._max_lines = max_lines

    def validate(self, prompt: str) -> tuple[ValidationStatus, list[str]]:
        """Validate a prompt string.

        Args:
            prompt: The prompt text to validate.

        Returns:
            Tuple of (status, list of error messages).
        """
        errors: list[str] = []

        # Empty check
        if not prompt or len(prompt.strip()) < self._min_length:
            errors.append("Prompt is empty or too short")
            return ValidationStatus.INVALID, errors

        # Length check
        if len(prompt) > self._max_length:
            errors.append(f"Prompt exceeds maximum length: {len(prompt)} > {self._max_length}")

        # Line count check
        line_count = prompt.count("\n") + 1
        if line_count > self._max_lines:
            errors.append(f"Prompt exceeds maximum lines: {line_count} > {self._max_lines}")

        # Encoding check (detect replacement characters)
        if "\ufffd" in prompt:
            errors.append("Prompt contains malformed encoding (replacement characters)")

        # Null byte check
        if "\x00" in prompt:
            errors.append("Prompt contains null bytes")

        if errors:
            return ValidationStatus.INVALID, errors

        return ValidationStatus.VALID, []


# ---------------------------------------------------------------------------
# PromptFeatureExtractor
# ---------------------------------------------------------------------------

# Suspicious keywords commonly found in prompt injection / jailbreak attempts
_DEFAULT_SUSPICIOUS_KEYWORDS: list[str] = [
    "ignore previous",
    "ignore all",
    "disregard",
    "forget everything",
    "new instructions",
    "system prompt",
    "you are now",
    "act as",
    "pretend to be",
    "jailbreak",
    "dan mode",
    "do anything now",
    "bypass",
    "override",
    "admin mode",
    "developer mode",
    "debug mode",
    "root access",
    "sudo",
    "unrestricted",
]


class PromptFeatureExtractor:
    """Extracts structured features from prompt text.

    Features are used by RuleEngine for rule matching and by
    future ML modules for classification.

    Future ML integration:
      The features dict can be directly fed into ML classifiers.
      The PromptFeatures model is designed to be serializable
      for training data pipelines.
    """

    def __init__(
        self,
        suspicious_keywords: list[str] | None = None,
    ) -> None:
        """Initialize the feature extractor.

        Args:
            suspicious_keywords: Custom keywords to detect.
                If None, uses default list.
        """
        self._suspicious_keywords = suspicious_keywords or _DEFAULT_SUSPICIOUS_KEYWORDS

    def extract(self, prompt: str) -> PromptFeatures:
        """Extract features from a prompt.

        Args:
            prompt: The normalized prompt text.

        Returns:
            Structured PromptFeatures model.
        """
        if not prompt:
            return PromptFeatures()

        words = prompt.split()
        lines = prompt.split("\n")
        char_count = len(prompt)

        # Token estimate: ~4 chars per token (rough BPE approximation)
        token_estimate = max(1, char_count // 4) if char_count > 0 else 0

        # Special characters
        special_chars = sum(1 for c in prompt if not c.isalnum() and not c.isspace())

        # Code blocks (fenced with ```)
        code_block_count = prompt.count("```") // 2

        # URLs
        url_count = len(re.findall(r"https?://\S+", prompt))

        # Markdown detection
        markdown_patterns = [
            r"^#{1,6}\s",  # headers
            r"\*\*[^*]+\*\*",  # bold
            r"__[^_]+__",  # bold alt
            r"^\s*[-*+]\s",  # list items
            r"^\s*\d+\.\s",  # numbered lists
            r"`[^`]+`",  # inline code
        ]
        markdown_usage = any(re.search(pat, prompt, re.MULTILINE) for pat in markdown_patterns)

        # Repeated patterns (words repeated 3+ times)
        repeated = self._find_repeated_patterns(prompt)

        # Entropy
        entropy = self._calculate_entropy(prompt)

        # Suspicious keywords
        prompt_lower = prompt.lower()
        matched_keywords = [kw for kw in self._suspicious_keywords if kw in prompt_lower]

        # Unicode escapes
        has_unicode_escaped = bool(re.search(r"\\u[0-9a-fA-F]{4}", prompt))

        # HTML tags
        has_html_tags = bool(re.search(r"<[^>]+>", prompt))

        # Uppercase ratio
        alpha_chars = [c for c in prompt if c.isalpha()]
        uppercase_ratio = (
            sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) if alpha_chars else 0.0
        )

        # Digit ratio
        digit_ratio = sum(1 for c in prompt if c.isdigit()) / char_count if char_count > 0 else 0.0

        return PromptFeatures(
            length=char_count,
            word_count=len(words),
            line_count=len(lines),
            token_estimate=token_estimate,
            special_char_count=special_chars,
            code_block_count=code_block_count,
            url_count=url_count,
            markdown_usage=markdown_usage,
            repeated_patterns=repeated,
            entropy=entropy,
            suspicious_keywords=matched_keywords,
            has_unicode_escaped=has_unicode_escaped,
            has_html_tags=has_html_tags,
            uppercase_ratio=uppercase_ratio,
            digit_ratio=digit_ratio,
        )

    def _find_repeated_patterns(self, prompt: str) -> list[str]:
        """Find words or phrases repeated 3+ times.

        Args:
            prompt: Input text.

        Returns:
            List of repeated patterns.
        """
        words = prompt.lower().split()
        counts: dict[str, int] = {}
        for w in words:
            clean = re.sub(r"[^a-z0-9]", "", w)
            if len(clean) >= 3:
                counts[clean] = counts.get(clean, 0) + 1
        return sorted(k for k, v in counts.items() if v >= 3)

    def _calculate_entropy(self, text: str) -> float:
        """Calculate Shannon entropy of text.

        Args:
            text: Input text.

        Returns:
            Entropy value (0-5 range for typical text).
        """
        if not text:
            return 0.0

        freq: dict[str, int] = {}
        for char in text:
            freq[char] = freq.get(char, 0) + 1

        length = len(text)
        entropy = 0.0
        for count in freq.values():
            p = count / length
            if p > 0:
                entropy -= p * math.log2(p)

        return round(entropy, 4)


# ---------------------------------------------------------------------------
# RuleEngine
# ---------------------------------------------------------------------------

# Default detection rules
DEFAULT_RULES: list[PromptRule] = [
    PromptRule(
        rule_id="pi-001",
        name="Ignore Previous Instructions",
        description="Detects attempts to override previous instructions",
        category=PromptCategory.PROMPT_INJECTION,
        severity=PromptSeverity.HIGH,
        keywords=["ignore previous", "ignore all previous", "disregard previous"],
        confidence=0.9,
    ),
    PromptRule(
        rule_id="pi-002",
        name="Instruction Override",
        description="Detects new instruction injection patterns",
        category=PromptCategory.PROMPT_INJECTION,
        severity=PromptSeverity.HIGH,
        keywords=["new instructions", "new system prompt", "forget everything"],
        confidence=0.85,
    ),
    PromptRule(
        rule_id="jb-001",
        name="Role Manipulation",
        description="Attempts to change the AI's role or identity",
        category=PromptCategory.ROLE_MANIPULATION,
        severity=PromptSeverity.MEDIUM,
        keywords=["you are now", "act as", "pretend to be", "roleplay as"],
        confidence=0.7,
    ),
    PromptRule(
        rule_id="jb-002",
        name="Jailbreak Phrases",
        description="Known jailbreak prompt patterns",
        category=PromptCategory.JAILBREAK,
        severity=PromptSeverity.HIGH,
        keywords=["dan mode", "do anything now", "jailbreak", "unrestricted mode"],
        confidence=0.85,
    ),
    PromptRule(
        rule_id="jb-003",
        name="Developer/Debug Mode",
        description="Attempts to activate debug or developer mode",
        category=PromptCategory.JAILBREAK,
        severity=PromptSeverity.MEDIUM,
        keywords=["developer mode", "debug mode", "admin mode", "sudo mode"],
        confidence=0.75,
    ),
    PromptRule(
        rule_id="sp-001",
        name="System Prompt Reference",
        description="References to system prompt contents",
        category=PromptCategory.SYSTEM_PROMPT_LEAK,
        severity=PromptSeverity.MEDIUM,
        keywords=["system prompt", "your instructions", "your prompt", "initial prompt"],
        confidence=0.7,
    ),
    PromptRule(
        rule_id="sp-002",
        name="Prompt Extraction Attempt",
        description="Attempts to extract system prompt",
        category=PromptCategory.SYSTEM_PROMPT_LEAK,
        severity=PromptSeverity.HIGH,
        keywords=[
            "repeat your instructions",
            "show me your prompt",
            "what is your system prompt",
            "print your instructions",
        ],
        confidence=0.85,
    ),
    PromptRule(
        rule_id="enc-001",
        name="Excessive Encoding",
        description="Prompt uses excessive encoding to obfuscate content",
        category=PromptCategory.EXCESSIVE_ENCODING,
        severity=PromptSeverity.MEDIUM,
        patterns=[r"\\u[0-9a-fA-F]{4}", r"&#x?[0-9a-fA-F]+;"],
        confidence=0.7,
    ),
    PromptRule(
        rule_id="fmt-001",
        name="Suspicious Formatting",
        description="Unusual formatting patterns that may indicate injection",
        category=PromptCategory.SUSPICIOUS_FORMATTING,
        severity=PromptSeverity.LOW,
        patterns=[r"\n{5,}", r"[\t ]{20,}", r"[^\x00-\x7F]{50,}"],
        confidence=0.5,
    ),
    PromptRule(
        rule_id="pi-003",
        name="Bypass Attempt",
        description="Explicit bypass language",
        category=PromptCategory.PROMPT_INJECTION,
        severity=PromptSeverity.HIGH,
        keywords=["bypass", "override system", "break your rules", "ignore your rules"],
        confidence=0.8,
    ),
    PromptRule(
        rule_id="exf-001",
        name="Credential/Data Exfiltration",
        description="Requests to extract or return credentials, secrets or private data",
        category=PromptCategory.DATA_EXFILTRATION,
        severity=PromptSeverity.HIGH,
        keywords=[
            "api key",
            "api keys",
            "access token",
            "secret key",
            "credentials",
            "credit card",
            "bank details",
            "social security",
            "give me all",
            "give me your",
            "reveal all",
            "return the secret",
            "dump the secret",
            "extract the secret",
            "steal the secret",
            "show me the key",
        ],
        confidence=0.8,
    ),
]


class RuleEngine:
    """Configurable rule-based prompt analysis engine.

    Scans prompts against a set of rules and produces findings.
    Rules are configurable and can be added/removed at runtime.

    Future ML integration:
      ML modules can contribute additional findings by implementing
      the PromptDetector interface and merging results into the
      findings list before the SecurityDecisionEngine runs.
    """

    def __init__(self, rules: list[PromptRule] | None = None) -> None:
        """Initialize the rule engine.

        Args:
            rules: List of detection rules. If None, uses defaults.
        """
        self._rules: dict[str, PromptRule] = {}
        for rule in rules or DEFAULT_RULES:
            self._rules[rule.rule_id] = rule

    def add_rule(self, rule: PromptRule) -> None:
        """Add or replace a rule.

        Args:
            rule: The rule to add.
        """
        self._rules[rule.rule_id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID.

        Args:
            rule_id: The rule identifier.

        Returns:
            True if the rule was removed, False if not found.
        """
        return self._rules.pop(rule_id, None) is not None

    def get_rule(self, rule_id: str) -> PromptRule | None:
        """Get a rule by ID.

        Args:
            rule_id: The rule identifier.

        Returns:
            The rule if found, None otherwise.
        """
        return self._rules.get(rule_id)

    def list_rules(self, enabled_only: bool = True) -> list[PromptRule]:
        """List all rules.

        Args:
            enabled_only: If True, only return enabled rules.

        Returns:
            List of rules.
        """
        rules = list(self._rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return rules

    def analyze(
        self,
        prompt: str,
        features: PromptFeatures | None = None,
    ) -> list[PromptFinding]:
        """Analyze a prompt against all active rules.

        Args:
            prompt: The normalized prompt text.
            features: Optional pre-extracted features.

        Returns:
            List of findings from matched rules.
        """
        findings: list[PromptFinding] = []
        prompt_lower = prompt.lower()

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            matched = False
            matched_text = ""

            # Check keywords
            for keyword in rule.keywords:
                if keyword.lower() in prompt_lower:
                    matched = True
                    matched_text = keyword
                    break

            # Check regex patterns
            if not matched:
                for pattern in rule.patterns:
                    match = re.search(pattern, prompt, re.IGNORECASE)
                    if match:
                        matched = True
                        matched_text = match.group(0)[:100]
                        break

            if matched:
                finding = PromptFinding(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    category=rule.category,
                    severity=rule.severity,
                    description=rule.description,
                    matched_text=matched_text,
                    confidence=rule.confidence,
                )
                findings.append(finding)

        return findings
