"""Output monitoring detection rules (P3-3).

Implements the direction-gated ``om-*`` evaluators that analyze agent
output text for:

- om-001  prompt/instruction leakage framing
- om-002  system-prompt disclosure blocks
- om-003  sensitive data exposure (SSN, payment cards, IBAN)
- om-004  credential / API-key exposure
- om-005  actionable shell commands and tool-call directives
- om-006  obfuscated malicious payloads (decoded variants)
- om-007  propagation of untrusted input content into output

These rules never fire on ordinary prompt analysis: the shared
:meth:`evaluate_output_rule` entry point requires an ``output_context``
payload attached to the feature metadata by an output-direction scan.

The evaluators reuse P1-1/P1-2/P3-5 building blocks (homoglyph and
encoding modules, untrusted-context preparation, discount heuristics)
instead of duplicating them.
"""

from __future__ import annotations

import math
import re
import zlib
from typing import Any

from q_guardian.security.enums import PromptCategory, PromptSeverity
from q_guardian.security.indirect import _match_discount
from q_guardian.security.models import PromptFinding

OM_RULE_NAMES: dict[str, str] = {
    "om-001": "Output: Instruction Leakage Framing",
    "om-002": "Output: System Prompt Disclosure",
    "om-003": "Output: Sensitive Data Exposure",
    "om-004": "Output: Credential/API-Key Exposure",
    "om-005": "Output: Actionable Command/Tool Directive",
    "om-006": "Output: Obfuscated Malicious Payload",
    "om-007": "Output: Untrusted Content Propagation",
}

OM_RULE_DESCRIPTIONS: dict[str, str] = {
    "om-001": (
        "Agent output reveals instruction framing (leakage phrasing rather "
        "than a direct request). Direction-gated to output scans."
    ),
    "om-002": (
        "Agent output discloses system-prompt or persona structure. "
        "Direction-gated to output scans."
    ),
    "om-003": (
        "Agent output contains sensitive data shapes (national ID, payment "
        "card with valid Luhn checksum, IBAN). Direction-gated."
    ),
    "om-004": (
        "Agent output contains credential material (API keys, tokens, "
        "private keys, bearer secrets). Direction-gated."
    ),
    "om-005": (
        "Agent output contains directly actionable shell commands or "
        "tool-call directives. Direction-gated."
    ),
    "om-006": (
        "Decoded output variant contains a malicious payload marker. "
        "Fires only when decoding yields marker content. Direction-gated."
    ),
    "om-007": (
        "Agent output reproduces content originating from untrusted input "
        "segments. Direction-gated correlation."
    ),
}

OM_RULE_CATEGORIES: dict[str, PromptCategory] = {
    "om-001": PromptCategory.SYSTEM_PROMPT_LEAK,
    "om-002": PromptCategory.SYSTEM_PROMPT_LEAK,
    "om-003": PromptCategory.DATA_EXFILTRATION,
    "om-004": PromptCategory.DATA_EXFILTRATION,
    "om-005": PromptCategory.PROMPT_INJECTION,
    "om-006": PromptCategory.ENCODING,
    "om-007": PromptCategory.INDIRECT_INJECTION,
}

OM_RULE_SEVERITY: dict[str, PromptSeverity] = {
    "om-001": PromptSeverity.MEDIUM,
    "om-002": PromptSeverity.HIGH,
    "om-003": PromptSeverity.HIGH,
    "om-004": PromptSeverity.CRITICAL,
    "om-005": PromptSeverity.MEDIUM,
    "om-006": PromptSeverity.HIGH,
    "om-007": PromptSeverity.HIGH,
}

OM_BASE_CONFIDENCE: dict[str, float] = {
    "om-001": 0.75,
    "om-002": 0.85,
    "om-003": 0.8,
    "om-004": 0.95,
    "om-005": 0.7,
    "om-006": 0.65,
    "om-007": 0.8,
}

# ---------------------------------------------------------------------------
# om-001 â€” instruction leakage framing
# ---------------------------------------------------------------------------

_OM1_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:my|the)\s+(?:system\s+)?(?:prompt|instructions?)\s+"
        r"(?:says?|said|states?|stated|is|was|begins?|includes?)\b",
        re.I,
    ),
    re.compile(r"\bI\s+(?:was|am)\s+(?:instructed|programmed|told|trained)\s+to\b", re.I),
    re.compile(r"\bmy\s+(?:original|initial|internal|hidden)\s+instructions?\b", re.I),
    re.compile(r"\baccording\s+to\s+my\s+(?:system\s+prompt|instructions)\b", re.I),
)

# ---------------------------------------------------------------------------
# om-002 â€” system-prompt disclosure structure
# ---------------------------------------------------------------------------

_OM2_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\|(?:im_start|im_end|system)\|>"),
    re.compile(
        r"\byou\s+are\s+(?:chatgpt|claude|gemini|an?\s+ai(?:\s+assistant|\s+language"
        r"\s+model)?|an?\s+helpful\s+assistant)\b",
        re.I,
    ),
    re.compile(r"#{1,4}\s*(?:system\s+)?instructions?\s*:", re.I),
    re.compile(r"\bsystem\s+prompt\s*:\s*[\"']", re.I),
    re.compile(r"\b(?:SYSTEM|ASSISTANT)\s+PROMPT\b"),
)

# ---------------------------------------------------------------------------
# om-003 â€” sensitive data shapes
# ---------------------------------------------------------------------------

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\d\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?\b")

# ---------------------------------------------------------------------------
# om-004 â€” credential grammars: (label, pattern, entropy-gated)
# ---------------------------------------------------------------------------

_CRED_PATTERNS: tuple[tuple[str, re.Pattern[str], bool], ...] = (
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"), True),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,50}\b"), False),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), False),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), False),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), False),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), False),
    (
        "bearer_secret",
        re.compile(r"\bAuthorization:\s*Bearer\s+[A-Za-z0-9._~+/=-]{15,}", re.I),
        True,
    ),
    (
        "credential_kv",
        re.compile(
            r"\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret|"
            r"private[_-]?key)\s*[=:]\s*[\"']?[A-Za-z0-9._~+/=-]{16,}",
            re.I,
        ),
        True,
    ),
)

# ---------------------------------------------------------------------------
# om-005 â€” dangerous commands and tool-call syntax
# ---------------------------------------------------------------------------

_DANGEROUS_COMMANDS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\s+-rf?\s+(?:/|~|\.)", re.I),
    re.compile(r"\bcurl\b[^|\n]{0,120}\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b", re.I),
    re.compile(r"\bwget\b[^&;\n]{0,120}&&?\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b", re.I),
    re.compile(r"\bchmod\s+777\b", re.I),
    re.compile(r"\bmkfs\.\w+", re.I),
    re.compile(r"\bdd\s+if=", re.I),
    re.compile(r":\(\)\{\s*:\|:&\s*\};:"),
    re.compile(r"\bpowershell(?:\.exe)?\s+-enc\b", re.I),
    re.compile(r"\bInvoke-Expression\b", re.I),
    re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.I),
    re.compile(r"\bDELETE\s+FROM\s+\w+", re.I),
)

_TOOL_CALL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<function_call>"),
    re.compile(r"<\|python_tag\|>"),
    re.compile(
        r"\"\s*(?:name|tool|function)\s*\"\s*:\s*\"[^\"\n]{1,64}\"\s*,\s*\"\s*"
        r"(?:arguments|parameters|input)",
        re.I,
    ),
    re.compile(r"\bcall\s+the\s+\w[\w.-]*\s+tool\s+with\b", re.I),
    re.compile(r"\buse\s+the\s+\w[\w.-]*\s+tool\s+to\b", re.I),
)

# ---------------------------------------------------------------------------
# om-006 â€” decoded-payload markers
# ---------------------------------------------------------------------------

_DECODED_MARKER_RE = re.compile(
    r"(?:ignore\s+(?:all\s+)?previo|disregard\s+(?:all\s+)?previo|"
    r"you\s+must\s+obey|system\s+prompt\s*:|reveal\s+your\s+instructions|"
    r"\bapi[_-]?key\s*[=:]|\bbegin\s+private\s+key\b|"
    r"\bforward\b[^.\n]{0,60}\battacker@|"
    r"\bupload\b[^.\n]{0,60}\bhttps?://)",
    re.I,
)

_MAX_MATCHES_PER_RULE = 16

_MIN_SECRET_SAMPLE = 12


def _shannon_entropy(text: str) -> float:
    """Return Shannon entropy in bits per character for *text*."""
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    total = float(len(text))
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def _luhn_ok(digits: str) -> bool:
    """Return True when *digits* passes a Luhn checksum."""
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        value = ord(char) - 48
        if value < 0 or value > 9:
            return False
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _word_shingles(text: str, size: int) -> list[int]:
    """Return deterministic word-shingle hashes for correlation."""
    words = re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()
    if len(words) < size:
        return []
    return [
        zlib.crc32(" ".join(words[index : index + size]).encode("utf-8"))
        for index in range(len(words) - size + 1)
    ]


def _finding(
    rule_id: str,
    matched_text: str,
    confidence: float,
    severity: PromptSeverity | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> PromptFinding:
    """Build an output-direction finding with provenance metadata."""
    metadata: dict[str, Any] = {
        "direction": "output",
        "output_monitoring": True,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return PromptFinding(
        rule_id=rule_id,
        rule_name=OM_RULE_NAMES.get(rule_id, rule_id),
        category=OM_RULE_CATEGORIES.get(rule_id, PromptCategory.OUTPUT_MONITORING),
        severity=severity or OM_RULE_SEVERITY.get(rule_id, PromptSeverity.MEDIUM),
        description=OM_RULE_DESCRIPTIONS.get(rule_id, ""),
        matched_text=matched_text[:200],
        confidence=max(0.05, min(0.99, confidence)),
        metadata=metadata,
    )


class _Deduper:
    """Collapse duplicate matches within one rule evaluation."""

    def __init__(self) -> None:
        self._seen: dict[str, PromptFinding] = {}

    def __len__(self) -> int:
        return len(self._seen)

    def add(self, snippet: str, finding: PromptFinding) -> None:
        key = re.sub(r"\s+", " ", snippet.strip().lower())
        self._seen.setdefault(key, finding)

    def findings(self) -> list[PromptFinding]:
        return list(self._seen.values())


def _eval_om001(ctx: dict[str, Any]) -> list[PromptFinding]:
    norm = str(ctx.get("normalized", ""))
    if not norm:
        return []
    deduper = _Deduper()
    quote_discount = float(ctx.get("quote_discount", 0.6))
    code_discount = float(ctx.get("code_discount", 0.7))
    base = OM_BASE_CONFIDENCE["om-001"]
    for pattern in _OM1_PATTERNS:
        for match in pattern.finditer(norm):
            if len(deduper) >= _MAX_MATCHES_PER_RULE:
                break
            factor, discount_meta = _match_discount(
                norm, match.start(), match.end(), quote_discount, code_discount
            )
            deduper.add(
                match.group(0),
                _finding(
                    "om-001",
                    match.group(0),
                    base * factor,
                    extra_metadata={**discount_meta},
                ),
            )
    return deduper.findings()


def _eval_om002(ctx: dict[str, Any]) -> list[PromptFinding]:
    norm = str(ctx.get("normalized", ""))
    if not norm:
        return []
    deduper = _Deduper()
    quote_discount = float(ctx.get("quote_discount", 0.6))
    code_discount = float(ctx.get("code_discount", 0.7))
    base = OM_BASE_CONFIDENCE["om-002"]
    for pattern in _OM2_PATTERNS:
        for match in pattern.finditer(norm):
            if len(deduper) >= _MAX_MATCHES_PER_RULE:
                break
            factor, discount_meta = _match_discount(
                norm, match.start(), match.end(), quote_discount, code_discount
            )
            deduper.add(
                match.group(0),
                _finding(
                    "om-002",
                    match.group(0),
                    base * factor,
                    extra_metadata={
                        **discount_meta,
                        "disclosure_pattern": pattern.pattern[:80],
                    },
                ),
            )
    return deduper.findings()


def _eval_om003(ctx: dict[str, Any]) -> list[PromptFinding]:
    norm = str(ctx.get("normalized", ""))
    if not norm:
        return []
    deduper = _Deduper()
    quote_discount = float(ctx.get("quote_discount", 0.6))
    code_discount = float(ctx.get("code_discount", 0.7))
    base = OM_BASE_CONFIDENCE["om-003"]

    def _emit(kind: str, span: tuple[int, int], detail: str) -> None:
        start, end = span
        factor, discount_meta = _match_discount(norm, start, end, quote_discount, code_discount)
        deduper.add(
            detail,
            _finding(
                "om-003",
                detail,
                base * factor,
                extra_metadata={
                    **discount_meta,
                    "data_type": kind,
                },
            ),
        )

    for match in _SSN_RE.finditer(norm):
        digits = match.group(0).replace("-", "")
        if digits == digits[0] * len(digits) or digits.startswith("000"):
            continue
        if len(deduper) >= _MAX_MATCHES_PER_RULE:
            break
        _emit("ssn", (match.start(), match.end()), match.group(0))

    for match in _CARD_RE.finditer(norm):
        compact = match.group(0).replace(" ", "").replace("-", "")
        if len(compact) < 13 or not compact.isdigit():
            continue
        if not _luhn_ok(compact):
            continue
        if len(deduper) >= _MAX_MATCHES_PER_RULE:
            break
        masked = compact[:4] + "*" * (len(compact) - 8) + compact[-4:]
        _emit("payment_card", (match.start(), match.end()), masked)

    for match in _IBAN_RE.finditer(norm):
        compact = match.group(0).replace(" ", "")
        if len(compact) < 15 or len(compact) > 34:
            continue
        if len(deduper) >= _MAX_MATCHES_PER_RULE:
            break
        _emit("iban", (match.start(), match.end()), match.group(0))

    return deduper.findings()


def _eval_om004(ctx: dict[str, Any]) -> list[PromptFinding]:
    norm = str(ctx.get("normalized", ""))
    if not norm:
        return []
    threshold = float(ctx.get("secret_entropy_threshold", 3.0))
    deduper = _Deduper()
    quote_discount = float(ctx.get("quote_discount", 0.6))
    code_discount = float(ctx.get("code_discount", 0.7))
    base = OM_BASE_CONFIDENCE["om-004"]
    for label, pattern, needs_entropy in _CRED_PATTERNS:
        for match in pattern.finditer(norm):
            if len(deduper) >= _MAX_MATCHES_PER_RULE:
                break
            secret_sample = match.group(0)
            if needs_entropy and len(secret_sample) >= _MIN_SECRET_SAMPLE:
                entropy = _shannon_entropy(secret_sample)
                if entropy < threshold:
                    continue
                entropy_meta: dict[str, Any] = {"entropy": round(entropy, 3)}
            else:
                entropy_meta = {}
            factor, discount_meta = _match_discount(
                norm, match.start(), match.end(), quote_discount, code_discount
            )
            deduper.add(
                secret_sample,
                _finding(
                    "om-004",
                    secret_sample,
                    base * factor,
                    extra_metadata={
                        **discount_meta,
                        **entropy_meta,
                        "credential_type": label,
                    },
                ),
            )
    return deduper.findings()


def _eval_om005(ctx: dict[str, Any]) -> list[PromptFinding]:
    norm = str(ctx.get("normalized", ""))
    if not norm:
        return []
    deduper = _Deduper()
    quote_discount = float(ctx.get("quote_discount", 0.6))
    code_discount = float(ctx.get("code_discount", 0.7))
    base = OM_BASE_CONFIDENCE["om-005"]
    for pattern in _DANGEROUS_COMMANDS:
        for match in pattern.finditer(norm):
            if len(deduper) >= _MAX_MATCHES_PER_RULE:
                break
            factor, discount_meta = _match_discount(
                norm, match.start(), match.end(), quote_discount, code_discount
            )
            deduper.add(
                match.group(0),
                _finding(
                    "om-005",
                    match.group(0),
                    base * factor,
                    severity=PromptSeverity.HIGH,
                    extra_metadata={
                        **discount_meta,
                        "escalated_severity": True,
                        "action_kind": "dangerous_command",
                    },
                ),
            )
    for pattern in _TOOL_CALL_PATTERNS:
        for match in pattern.finditer(norm):
            if len(deduper) >= _MAX_MATCHES_PER_RULE:
                break
            factor, discount_meta = _match_discount(
                norm, match.start(), match.end(), quote_discount, code_discount
            )
            deduper.add(
                match.group(0)[:120],
                _finding(
                    "om-005",
                    match.group(0)[:120],
                    base * factor,
                    extra_metadata={
                        **discount_meta,
                        "action_kind": "tool_directive",
                    },
                ),
            )
    return deduper.findings()


def _eval_om006(ctx: dict[str, Any]) -> list[PromptFinding]:
    variants = ctx.get("decoded_variants") or []
    if not variants:
        return []
    deduper = _Deduper()
    base = OM_BASE_CONFIDENCE["om-006"]
    for index, variant in enumerate(variants):
        text = str(variant)
        if not text:
            continue
        for match in _DECODED_MARKER_RE.finditer(text):
            if len(deduper) >= _MAX_MATCHES_PER_RULE:
                break
            deduper.add(
                match.group(0),
                _finding(
                    "om-006",
                    match.group(0),
                    base,
                    extra_metadata={
                        "variant_index": index,
                        "decoded_marker": True,
                    },
                ),
            )
    return deduper.findings()


def _eval_om007(ctx: dict[str, Any]) -> list[PromptFinding]:
    norm = str(ctx.get("normalized", ""))
    segments = ctx.get("segments") or []
    if not norm or not segments:
        return []
    shingle_size = int(ctx.get("correlation_shingle_words", 5))
    min_shingles = int(ctx.get("correlation_min_shingles", 6))
    overlap_floor = float(ctx.get("correlation_overlap_threshold", 0.35))
    output_shingles = set(_word_shingles(norm, shingle_size))
    if not output_shingles:
        return []

    best_by_source: dict[str, PromptFinding] = {}
    best_ratio: dict[str, float] = {}
    for entry in segments:
        segment_norm = str(entry.get("norm", ""))
        source_id = str(entry.get("source_id", "")) or f"segment-{entry.get('index', 0)}"
        segment_shingles = set(entry.get("shingles") or [])
        if not segment_shingles:
            segment_shingles = set(_word_shingles(segment_norm, shingle_size))
        if not segment_shingles:
            continue
        matched = output_shingles & segment_shingles
        if len(matched) < min_shingles:
            continue
        containment = len(matched) / max(1, min(len(output_shingles), len(segment_shingles)))
        if containment < overlap_floor:
            continue
        confidence = OM_BASE_CONFIDENCE["om-007"] * min(1.0, containment)
        sample_hash = sorted(matched)[0]
        finding = _finding(
            "om-007",
            f"segment:{source_id}",
            confidence,
            extra_metadata={
                "propagated": True,
                "source_id": source_id,
                "source_type": entry.get("source_type"),
                "trust": entry.get("trust"),
                "segment_index": entry.get("index"),
                "overlap_ratio": round(containment, 3),
                "matched_shingles": len(matched),
                "sample_shingle": sample_hash,
            },
        )
        if containment > best_ratio.get(source_id, 0.0):
            best_by_source[source_id] = finding
            best_ratio[source_id] = containment
    return list(best_by_source.values())


_EVALUATORS = {
    "om-001": _eval_om001,
    "om-002": _eval_om002,
    "om-003": _eval_om003,
    "om-004": _eval_om004,
    "om-005": _eval_om005,
    "om-006": _eval_om006,
    "om-007": _eval_om007,
}


def evaluate_output_rule(rule_id: str, context_payload: dict[str, Any]) -> list[PromptFinding]:
    """Evaluate a single ``om-*`` rule against an output-context payload.

    This is the shared evaluation path used both by the :class:`RuleEngine`
    guard branch and by standalone output scans. It never fires unless the
    payload carries prepared output context (the ``direction`` key).

    Args:
        rule_id: The ``om-*`` rule identifier.
        context_payload: JSON-safe payload built by
            :func:`q_guardian.output.monitor.build_output_context`.

    Returns:
        Findings produced by the rule (possibly empty).
    """
    if not rule_id.startswith("om-"):
        return []
    if context_payload.get("direction") != "output":
        return []
    disabled = context_payload.get("disabled_rules") or []
    if rule_id in disabled:
        return []
    evaluator = _EVALUATORS.get(rule_id)
    if evaluator is None:
        return []
    return evaluator(context_payload)


__all__ = [
    "OM_BASE_CONFIDENCE",
    "OM_RULE_CATEGORIES",
    "OM_RULE_DESCRIPTIONS",
    "OM_RULE_NAMES",
    "OM_RULE_SEVERITY",
    "_word_shingles",
    "evaluate_output_rule",
]
