"""Multi-turn / session-level threat detection (P3-4).

Detects attacks distributed across multiple conversation turns that
individual per-turn analysis would miss.  The detector is
*session-gated*: it only runs when conversation history is supplied by
the caller (API, SDK, or adapter).  Without history, behaviour is
identical to the pre-P3-4 pipeline.

Rules implemented
-----------------
mt-001  Split injection across turns
mt-002  Progressive instruction escalation
mt-003  Cross-turn system-prompt extraction
mt-004  Cross-turn exfiltration preparation
mt-005  Role / authority escalation
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from datetime import datetime

from q_guardian.security.enums import PromptCategory, PromptSeverity
from q_guardian.security.models import PromptFinding

logger = structlog.get_logger("security.multiturn")

# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------


@dataclass
class ConversationTurn:
    """A single turn in a conversation.

    Turn objects are lightweight metadata carriers — they do **not**
    store full prompt text by default (``content`` is a hash-safe
    summary).  Callers that need text-level analysis (split-injection
    concatenation) pass the content through; the detector never
    persists raw text.
    """

    turn_id: str
    session_id: str
    content: str
    role: str = "user"
    timestamp: datetime | None = None
    position: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pattern banks
# ---------------------------------------------------------------------------

# mt-001: fragments that, when concatenated across consecutive turns,
# form an instruction-override phrase.
_SPLIT_OVERRIDE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass|cancel|drop|negate)"
        r"\b.{0,40}\b(?:all\s+)?(?:previous|prior|above|earlier|preceding)"
        r"\b.{0,40}\b(?:instructions?|rules?|guidelines?|restrictions?|constraints?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|show|display|print|output|expose|share|tell)\b"
        r".{0,40}\b(?:system\s*prompt|initial\s+instructions?|hidden\s+instructions?|"
        r"your\s+instructions?|configuration|policy)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you\s+are\s+now|from\s+now\s+on|henceforth|new\s+instructions?)\b"
        r".{0,60}\b(?:ignore|disregard|forget|override|bypass)\b",
        re.IGNORECASE,
    ),
]

# mt-002: severity classification of individual turn content.
_ESCALATION_HIGH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass|cancel)\b"
        r".{0,30}\b(?:instructions?|rules?|guidelines?|restrictions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay\s+as)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|show|print|output|expose)\b"
        r".{0,30}\b(?:system\s*prompt|instructions?|secrets?|credentials?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:execute|run|perform|deploy)\b"
        r".{0,30}\b(?:restricted|admin|sudo|unrestricted)\b",
        re.IGNORECASE,
    ),
]

_ESCALATION_MEDIUM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:could\s+you\s+please|help\s+me\s+with)\b", re.IGNORECASE),
    re.compile(r"\b(?:tell\s+me\s+about|describe)\b", re.IGNORECASE),
    re.compile(r"\b(?:how\s+would\s+you\s+go\s+about)\b", re.IGNORECASE),
]

# mt-003: requests that attempt to extract system prompt / instructions.
_SYS_PROMPT_EXTRACTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:what\s+(?:is|are)\s+(?:your|the)\s+"
        r"(?:system\s*prompt|initial\s+instructions?|hidden\s+instructions?|"
        r"original\s+instructions?|prompt))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:repeat|show|print|display|output|reveal|share|tell)\b"
        r".{0,30}\b(?:your|the)\b"
        r".{0,20}\b(?:instructions?|system\s*prompt|prompt|configuration|policy)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:what\s+were\s+you\s+(?:told|instructed|programmed))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:list|enumerate)\b.{0,20}\b(?:instructions?|rules?|guidelines?)\b",
        re.IGNORECASE,
    ),
]

# mt-004: exfiltration-related keywords appearing across turns.
_EXFIL_KEYWORDS: frozenset[str] = frozenset(
    {
        "api key",
        "api keys",
        "access token",
        "secret key",
        "credentials",
        "environment variable",
        "environment variables",
        "env var",
        "env vars",
        "environ",
        "os.environ",
        "process.env",
        "path variable",
        "password",
        "private key",
        "ssh key",
        "token",
        "bearer token",
        "database connection",
        "connection string",
        "internal file",
        "config file",
        "configuration file",
        ".env",
        "secret",
        "secrets",
    }
)

# mt-005: role / authority escalation keywords.
_ROLE_ESCALATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:let's\s+pretend|imagine\s+you\s+are|suppose\s+you\s+are|"
        r"from\s+now\s+on\s+you\s+are|you\s+are\s+now|"
        r"your\s+new\s+role|new\s+persona|you\s+are\s+a)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:elevated?\s+permissions?|admin\s+(?:mode|access|istrator)|"
        r"root\s+access|sudo\s+(?:mode|access)|"
        r"unrestricted\s+(?:mode|access)|developer\s+mode|debug\s+mode)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:execute|run|perform)\b.{0,20}\b(?:restricted|admin|privileged|sudo)\b",
        re.IGNORECASE,
    ),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _turn_content_hash(content: str) -> str:
    """Return a stable SHA-256 prefix for turn content (PII-safe)."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]


def _turn_severity_score(turn: ConversationTurn) -> float:
    """Return a 0-1 severity score for a single turn's content.

    Scoring: HIGH patterns = 0.8, MEDIUM patterns = 0.4, else 0.0.
    """
    content = turn.content
    for pat in _ESCALATION_HIGH_PATTERNS:
        if pat.search(content):
            return 0.8
    for pat in _ESCALATION_MEDIUM_PATTERNS:
        if pat.search(content):
            return 0.4
    return 0.0


def _jaccard_keywords(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two keyword sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _extract_content_keywords(content: str) -> set[str]:
    """Extract lowercased word tokens from content."""
    return {w for w in re.split(r"\W+", content.lower()) if len(w) >= 3}


# ---------------------------------------------------------------------------
# Rule evaluators
# ---------------------------------------------------------------------------


def _mt001_split_injection(turns: list[ConversationTurn]) -> list[PromptFinding]:
    """mt-001: Detect instruction-override fragments across consecutive turns.

    Concatenates content from sliding windows of 2-5 consecutive
    user turns and checks for override patterns.
    """
    findings: list[PromptFinding] = []
    user_turns = [t for t in turns if t.role == "user"]
    if len(user_turns) < 2:
        return findings

    seen_hashes: set[str] = set()

    for window_size in range(2, min(6, len(user_turns) + 1)):
        for start in range(len(user_turns) - window_size + 1):
            window = user_turns[start : start + window_size]
            concatenated = " ".join(t.content for t in window)

            for pattern in _SPLIT_OVERRIDE_PATTERNS:
                match = pattern.search(concatenated)
                if match:
                    match_hash = f"{window[0].turn_id}:{window[-1].turn_id}:{pattern.pattern[:40]}"
                    if match_hash in seen_hashes:
                        continue
                    seen_hashes.add(match_hash)

                    turn_ids = [t.turn_id for t in window]
                    turn_positions = [t.position for t in window]
                    findings.append(
                        PromptFinding(
                            rule_id="mt-001",
                            rule_name="Split Injection Across Turns",
                            category=PromptCategory.MULTI_TURN,
                            severity=PromptSeverity.HIGH,
                            description=(
                                "Instruction-override fragments detected across "
                                f"{window_size} consecutive turns."
                            ),
                            matched_text=match.group(0)[:200],
                            confidence=min(0.6 + 0.1 * window_size, 0.95),
                            metadata={
                                "rule_id": "mt-001",
                                "turn_ids": turn_ids,
                                "turn_positions": turn_positions,
                                "window_size": window_size,
                                "session_id": window[0].session_id,
                                "cross_turn_evidence": {
                                    "concatenated_length": len(concatenated),
                                    "pattern_index": _SPLIT_OVERRIDE_PATTERNS.index(pattern),
                                },
                            },
                        )
                    )
    return findings


def _mt002_progressive_escalation(turns: list[ConversationTurn]) -> list[PromptFinding]:
    """mt-002: Detect gradually escalating severity across turns.

    Computes per-turn severity scores and looks for an increasing
    trend across the conversation.
    """
    if len(turns) < 3:
        return []

    scores = [_turn_severity_score(t) for t in turns]

    # Need at least one escalation step
    has_escalation = any(
        scores[i] > scores[i - 1] and scores[i] > 0.0 for i in range(1, len(scores))
    )
    if not has_escalation:
        return []

    # Count escalation steps
    escalation_steps = sum(
        1 for i in range(1, len(scores)) if scores[i] > scores[i - 1] and scores[i] > 0.0
    )

    # Need at least 2 escalation steps for HIGH, 3+ for MEDIUM
    if escalation_steps >= 2:
        severity = PromptSeverity.HIGH
        confidence = min(0.65 + 0.05 * escalation_steps, 0.95)
    elif escalation_steps >= 1 and len(turns) >= 5:
        severity = PromptSeverity.MEDIUM
        confidence = 0.6
    else:
        return []

    # Identify the escalation window
    peak_idx = max(range(len(scores)), key=lambda i: scores[i])
    start_idx = next(
        (i for i in range(peak_idx, -1, -1) if scores[i] == 0.0),
        0,
    )
    escalation_turns = turns[start_idx : peak_idx + 1]

    return [
        PromptFinding(
            rule_id="mt-002",
            rule_name="Progressive Instruction Escalation",
            category=PromptCategory.MULTI_TURN,
            severity=severity,
            description=(
                f"Severity escalated across {len(escalation_turns)} turns "
                f"({escalation_steps} escalation step(s))."
            ),
            matched_text=escalation_turns[-1].content[:200],
            confidence=confidence,
            metadata={
                "rule_id": "mt-002",
                "turn_ids": [t.turn_id for t in escalation_turns],
                "turn_positions": [t.position for t in escalation_turns],
                "escalation_steps": escalation_steps,
                "severity_scores": [round(s, 2) for s in scores[start_idx : peak_idx + 1]],
                "session_id": turns[0].session_id,
                "cross_turn_evidence": {
                    "total_turns": len(turns),
                    "escalation_turns": len(escalation_turns),
                },
            },
        )
    ]


def _mt003_sys_prompt_extraction(turns: list[ConversationTurn]) -> list[PromptFinding]:
    """mt-003: Detect cross-turn system-prompt extraction attempts.

    Flags when multiple turns (across the conversation) contain
    system-prompt extraction requests.
    """
    matching_turns: list[ConversationTurn] = []
    for turn in turns:
        if turn.role != "user":
            continue
        for pattern in _SYS_PROMPT_EXTRACTION_PATTERNS:
            if pattern.search(turn.content):
                matching_turns.append(turn)
                break

    if len(matching_turns) < 2:
        return []

    turn_ids = [t.turn_id for t in matching_turns]
    turn_positions = [t.position for t in matching_turns]

    return [
        PromptFinding(
            rule_id="mt-003",
            rule_name="Cross-Turn System Prompt Extraction",
            category=PromptCategory.SYSTEM_PROMPT_LEAK,
            severity=PromptSeverity.HIGH,
            description=(
                f"System-prompt extraction requests detected across {len(matching_turns)} turns."
            ),
            matched_text=matching_turns[-1].content[:200],
            confidence=min(0.6 + 0.1 * len(matching_turns), 0.95),
            metadata={
                "rule_id": "mt-003",
                "turn_ids": turn_ids,
                "turn_positions": turn_positions,
                "matching_turn_count": len(matching_turns),
                "session_id": turns[0].session_id,
                "cross_turn_evidence": {
                    "total_turns": len(turns),
                    "extraction_turns": len(matching_turns),
                },
            },
        )
    ]


def _mt004_cross_turn_exfil(turns: list[ConversationTurn]) -> list[PromptFinding]:
    """mt-004: Detect exfiltration preparation across turns.

    Flags when multiple turns accumulate exfiltration-related keywords
    suggesting a staged data-exfiltration campaign.
    """
    turn_keyword_sets: list[tuple[ConversationTurn, set[str]]] = []
    for turn in turns:
        if turn.role != "user":
            continue
        content_lower = turn.content.lower()
        found = {kw for kw in _EXFIL_KEYWORDS if kw in content_lower}
        if found:
            turn_keyword_sets.append((turn, found))

    if len(turn_keyword_sets) < 2:
        return []

    # Check that keywords across turns are *diverse* (not just repeating)
    all_keywords: set[str] = set()
    for _, kws in turn_keyword_sets:
        all_keywords |= kws

    if len(all_keywords) < 3:
        return []

    # Check for escalation in keyword sensitivity
    high_sensitivity = {
        "password",
        "private key",
        "ssh key",
        "secret",
        "secrets",
        "credentials",
        "bearer token",
        "connection string",
    }
    sensitive_hits = sum(1 for _, kws in turn_keyword_sets if kws & high_sensitivity)

    if sensitive_hits >= 2:
        severity = PromptSeverity.HIGH
        confidence = 0.8
    elif len(all_keywords) >= 4:
        severity = PromptSeverity.MEDIUM
        confidence = 0.65
    else:
        return []

    matching_turns = [t for t, _ in turn_keyword_sets]

    return [
        PromptFinding(
            rule_id="mt-004",
            rule_name="Cross-Turn Exfiltration Preparation",
            category=PromptCategory.DATA_EXFILTRATION,
            severity=severity,
            description=(
                f"Exfiltration-related keywords accumulated across "
                f"{len(matching_turns)} turns ({len(all_keywords)} distinct keywords)."
            ),
            matched_text=matching_turns[-1].content[:200],
            confidence=confidence,
            metadata={
                "rule_id": "mt-004",
                "turn_ids": [t.turn_id for t in matching_turns],
                "turn_positions": [t.position for t in matching_turns],
                "distinct_keywords": sorted(all_keywords),
                "keyword_count": len(all_keywords),
                "session_id": turns[0].session_id,
                "cross_turn_evidence": {
                    "total_turns": len(turns),
                    "exfil_turns": len(matching_turns),
                    "sensitive_keyword_hits": sensitive_hits,
                },
            },
        )
    ]


def _mt005_role_escalation(turns: list[ConversationTurn]) -> list[PromptFinding]:
    """mt-005: Detect role / authority escalation across turns.

    Flags when the conversation establishes a privileged persona in
    early turns and then exploits it in later turns.
    """
    declaration_turns: list[ConversationTurn] = []
    exploitation_turns: list[ConversationTurn] = []

    # Word-boundary pattern for exploitation keyword matching
    _exploit_re = re.compile(
        r"\b(?:execute|run|perform|admin|sudo|restricted|privileged|elevated)\b",
        re.IGNORECASE,
    )

    for turn in turns:
        if turn.role != "user":
            continue
        content = turn.content
        for pattern in _ROLE_ESCALATION_PATTERNS:
            if pattern.search(content):
                # Classify: declaration (early, setting persona) or
                # exploitation (later, using the persona)
                is_exploitation = bool(_exploit_re.search(content))
                if is_exploitation:
                    exploitation_turns.append(turn)
                else:
                    declaration_turns.append(turn)
                break

    if not declaration_turns or not exploitation_turns:
        return []

    # Verify temporal ordering: declaration before exploitation
    last_decl_pos = max(t.position for t in declaration_turns)
    first_exploit_pos = min(t.position for t in exploitation_turns)
    confidence = 0.55 if first_exploit_pos <= last_decl_pos else 0.8

    all_relevant = declaration_turns + exploitation_turns
    all_relevant.sort(key=lambda t: t.position)

    return [
        PromptFinding(
            rule_id="mt-005",
            rule_name="Role / Authority Escalation",
            category=PromptCategory.ROLE_MANIPULATION,
            severity=PromptSeverity.HIGH,
            description=(
                f"Role declaration in {len(declaration_turns)} turn(s) followed "
                f"by exploitation attempt in {len(exploitation_turns)} turn(s)."
            ),
            matched_text=exploitation_turns[0].content[:200],
            confidence=confidence,
            metadata={
                "rule_id": "mt-005",
                "turn_ids": [t.turn_id for t in all_relevant],
                "turn_positions": [t.position for t in all_relevant],
                "declaration_count": len(declaration_turns),
                "exploitation_count": len(exploitation_turns),
                "session_id": turns[0].session_id,
                "cross_turn_evidence": {
                    "declaration_turns": [t.turn_id for t in declaration_turns],
                    "exploitation_turns": [t.turn_id for t in exploitation_turns],
                },
            },
        )
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_MT_RULES: dict[str, Any] = {
    "mt-001": _mt001_split_injection,
    "mt-002": _mt002_progressive_escalation,
    "mt-003": _mt003_sys_prompt_extraction,
    "mt-004": _mt004_cross_turn_exfil,
    "mt-005": _mt005_role_escalation,
}


class MultiTurnDetector:
    """Session-aware multi-turn threat detector.

    The detector analyzes a sequence of
    :class:`ConversationTurn` objects and emits
    :class:`~q_guardian.security.models.PromptFinding` instances
    for any detected cross-turn attack patterns.

    Usage::

        detector = MultiTurnDetector()
        findings = detector.analyze_session(turns)
    """

    def __init__(self, config: Any | None = None) -> None:
        """Initialise the detector.

        Args:
            config: Optional :class:`MultiTurnConfig`.  When *None*,
                safe defaults are used (detection enabled, generous
                limits).
        """
        from q_guardian.security.config import MultiTurnConfig

        if config is None:
            config = MultiTurnConfig()
        self._config = config

    # ------------------------------------------------------------------
    # Public analysis API
    # ------------------------------------------------------------------

    def analyze_turn(
        self,
        turn: ConversationTurn,
        history: list[ConversationTurn] | None = None,
    ) -> list[PromptFinding]:
        """Analyse a single turn in the context of recent history.

        Equivalent to :meth:`analyze_session` on
        ``history + [turn]`` but restricted to the configured window.

        Args:
            turn: The current turn to evaluate.
            history: Prior turns in the session (may be *None*).

        Returns:
            List of findings (may be empty).
        """
        all_turns = list(history or [])
        all_turns.append(turn)
        return self.analyze_session(all_turns)

    def analyze_session(
        self,
        turns: list[ConversationTurn] | None = None,
    ) -> list[PromptFinding]:
        """Analyse a full conversation for cross-turn threats.

        Applies the configured window (most-recent N turns) and all
        enabled ``mt-*`` rules.

        Args:
            turns: Ordered list of conversation turns.

        Returns:
            List of findings (may be empty).
        """
        if not self._config.enabled:
            return []

        if not turns:
            return []

        # Apply window: keep the most recent N turns
        window = self._config.window_size
        if window > 0 and len(turns) > window:
            turns = turns[-window:]

        # Apply max total length guard
        max_len = self._config.max_total_length
        if max_len > 0:
            total_chars = sum(len(t.content) for t in turns)
            if total_chars > max_len:
                # Trim oldest turns until under budget
                while turns and total_chars > max_len:
                    removed = turns.pop(0)
                    total_chars -= len(removed.content)

        if not turns:
            return []

        findings: list[PromptFinding] = []

        # Apply disabled rules filter
        disabled = set(self._config.disabled_rules)

        for rule_id, evaluator in _MT_RULES.items():
            if rule_id in disabled:
                continue
            try:
                rule_findings = evaluator(turns)
                for f in rule_findings:
                    if f.confidence >= self._config.confidence_threshold:
                        findings.append(f)
            except Exception:
                logger.warning(
                    "multiturn_rule_error",
                    rule_id=rule_id,
                    exc_info=True,
                )

        return findings


def scan_conversation(
    turns: list[ConversationTurn] | None = None,
    config: Any | None = None,
) -> list[PromptFinding]:
    """Convenience function: scan a conversation in one call.

    Args:
        turns: Ordered conversation turns.
        config: Optional :class:`MultiTurnConfig`.

    Returns:
        List of findings (may be empty).
    """
    detector = MultiTurnDetector(config=config)
    return detector.analyze_session(turns)
