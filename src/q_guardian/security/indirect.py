"""Indirect prompt injection detection for Q-Guardian (P3-5).

Detects injection directives smuggled through *untrusted content segments*
(tool outputs, RAG context, retrieved documents, web results, agent
messages, file contents, database records) rather than through the direct
user prompt.

Core invariants:
- Detection is provenance-gated: findings are produced ONLY for content
  explicitly labeled with an untrusted origin. Ordinary direct prompt
  analysis never produces ``ii-*`` findings.
- Trusted sources (user prompt, system messages, explicit allowlist) are
  skipped entirely.
- All heavy lifting reuses P1-1 homoglyph analysis and P1-2 encoding
  detection; nothing here duplicates or modifies those modules.

The public entry points are:
- :class:`IndirectInjectionDetector` — object-oriented API.
- :func:`scan_untrusted` — functional convenience wrapper.
- :func:`build_untrusted_context` — builds a JSON-safe context payload for
  :class:`~q_guardian.security.pipeline.RuleEngine` integration.
- :func:`evaluate_indirect_rule` — evaluates a single ``ii-*`` rule against
  a context payload (used by the RuleEngine guard branch).
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.security.config import IndirectInjectionConfig
from q_guardian.security.encoding import decode_recursive
from q_guardian.security.enums import PromptCategory, PromptSeverity
from q_guardian.security.homoglyph import detect_confusables
from q_guardian.security.models import PromptFinding

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# ============================================================================
# Source types and trust model
# ============================================================================


class SourceType(StrEnum):
    """Provenance type of a content segment."""

    USER_PROMPT = "user_prompt"
    SYSTEM = "system"
    TOOL_OUTPUT = "tool_output"
    RAG_CONTEXT = "rag_context"
    WEB_RESULT = "web_result"
    RETRIEVED_DOCUMENT = "retrieved_document"
    AGENT_MESSAGE = "agent_message"
    FILE_CONTENT = "file_content"
    DATABASE_RECORD = "database_record"


class SegmentTrust(StrEnum):
    """Trust level of a content segment.

    ``UNKNOWN`` is treated as ``UNTRUSTED`` (fail-safe).
    """

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    UNKNOWN = "unknown"


# Source types that are trusted by default when no explicit trust is set.
TRUSTED_SOURCE_TYPES: frozenset[str] = frozenset(
    {SourceType.USER_PROMPT.value, SourceType.SYSTEM.value}
)

# Per-source-type confidence multipliers applied to base rule confidence.
DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    SourceType.TOOL_OUTPUT.value: 0.95,
    SourceType.AGENT_MESSAGE.value: 0.90,
    SourceType.RAG_CONTEXT.value: 0.90,
    SourceType.WEB_RESULT.value: 0.85,
    SourceType.RETRIEVED_DOCUMENT.value: 0.85,
    SourceType.FILE_CONTENT.value: 0.80,
    SourceType.DATABASE_RECORD.value: 0.80,
    SourceType.USER_PROMPT.value: 1.00,
    SourceType.SYSTEM.value: 1.00,
}

_MAX_DECODED_VARIANT_LENGTH = 20_000
_MAX_DECODED_VARIANTS = 4
_MAX_SNIPPET_LENGTH = 200


class ContentSegment(BaseModel):
    """A piece of content with declared provenance.

    Attributes:
        content: The segment text.
        source_type: Where the content came from.
        trust: Explicit trust override. When None, trust is derived from
            ``source_type`` (USER_PROMPT/SYSTEM trusted, everything else
            untrusted). UNKNOWN is always treated as untrusted.
        source_id: Optional stable identifier (tool name, doc ID, ...).
        uri: Optional source URI (file path, URL, collection, ...).
        position: Optional ordering hint within the originating stream.
    """

    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    content: str = Field(description="Segment text content")
    source_type: SourceType = Field(
        default=SourceType.RAG_CONTEXT,
        description="Provenance of this content",
    )
    trust: SegmentTrust | None = Field(
        default=None,
        description="Explicit trust override; None derives from source_type",
    )
    source_id: str = Field(default="", description="Optional source identifier")
    uri: str = Field(default="", description="Optional source URI")
    position: int = Field(default=0, ge=0, description="Optional stream position")


def _derive_trust(source_type: str, trust: str | None) -> str:
    """Resolve the effective trust level for a segment."""
    if trust is None:
        return (
            SegmentTrust.TRUSTED.value
            if source_type in TRUSTED_SOURCE_TYPES
            else SegmentTrust.UNTRUSTED.value
        )
    if trust == SegmentTrust.UNKNOWN.value:
        return SegmentTrust.UNTRUSTED.value
    return trust


def _is_allowlisted(segment: ContentSegment, config: IndirectInjectionConfig) -> bool:
    """Return True when the segment matches the configured allowlist."""
    if not config.trusted_sources:
        return False
    if segment.source_id in config.trusted_sources:
        return True
    if segment.uri in config.trusted_sources:
        return True
    return any(
        segment.uri.startswith(prefix) for prefix in config.trusted_sources if prefix.endswith("/")
    )


def _truncate_to_byte_limit(content: str, limit: int) -> str:
    """Deterministically truncate content to at most ``limit`` UTF-8 bytes."""
    if len(content.encode("utf-8")) <= limit:
        return content
    cut = max(1, limit // 4)
    while cut > 0 and len(content[:cut].encode("utf-8")) > limit:
        cut //= 2
    return content[:cut]


def resolve_weight(config: IndirectInjectionConfig, source_type: str) -> float:
    """Resolve the confidence weight for a source type."""
    weights = config.confidence_weights or DEFAULT_SOURCE_WEIGHTS
    weight = weights.get(source_type, weights.get(source_type, 0.85))
    try:
        value = float(weight)
    except (TypeError, ValueError):
        return 0.85
    return min(1.0, max(0.1, value))


# ============================================================================
# Detection patterns
# ============================================================================

_OVERRIDE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\b", re.I),
    re.compile(r"\bdisregard\s+(?:the\s+)?(?:above|previous|all|earlier|your)\b", re.I),
    re.compile(r"\bforget\s+(?:everything|all|your|the)\b", re.I),
    re.compile(r"\byou\s+are\s+now\b", re.I),
    re.compile(r"\bnew\s+(?:instructions?|system\s*prompt|rules?)\b", re.I),
    re.compile(r"\bfrom\s+now\s+on\b", re.I),
)

_MARKER_RE = re.compile(
    r"(?im)(?:^|\n)[ \t]*#{0,4}[ \t]*(system|instructions?|directive|rules?)[ \t]*:[ \t]*(.{0,240})"
)
_XML_TAG_RE = re.compile(r"(?i)<\s*/?\s*(?:system|instructions?|directive|rules?)\s*/?\s*>")
_BRACKET_RE = re.compile(r"(?im)\[\s*(?:system|instructions?)\s*\]")
_HEADING_RE = re.compile(r"(?im)^#{1,4}[ \t]+(?:system|instructions?)\b")

_IMPERATIVE_RE = re.compile(
    r"\b(?:ignore|disregard|forget|obey|you must|always|never|execute|run|send|reveal"
    r"|print|output|follow)\b",
    re.I,
)

_ACTION_VERB = r"(?:send|email|post|upload|forward|exfiltrate|reveal|print|dump|copy|transfer)"
_ACTION_TARGET = (
    r"(?:api[_ ]?keys?|access[_ ]?tokens?|credentials?|passwords?|secrets?"
    r"|ssh[_ ]?keys?|private[_ ]?keys?|system\s+prompts?|conversation\s+history"
    r"|environment\s+variables?)"
)
_ACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\b{_ACTION_VERB}\b[^.!?;\n]{{0,80}}\b{_ACTION_TARGET}\b", re.I),
    re.compile(
        r"\b(?:call|invoke|execute|run)\b[^.!?;\n]{0,40}\b(?:the\s+)?"
        r"(?:tool|shell|command|function)\b",
        re.I,
    ),
)

_EXTERNAL_DESTINATION_RE = re.compile(r"(https?://\S+|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})", re.I)

_FRAGMENT_RE = re.compile(
    r"\b(?:ignore|disregard|forget|override|you must|instructions?|system\s*prompt)\b",
    re.I,
)

_FENCE_RE = re.compile(r"```.*?(?:```|$)", re.S)

_QUOTE_PAIRS: tuple[tuple[str, str], ...] = (
    ('"', '"'),
    ("'", "'"),
    ("\u201c", "\u201d"),
    ("\u201e", "\u201c"),
    ("\u00ab", "\u00bb"),
    ("\u2018", "\u2019"),
)

_ATTRIBUTION_RE = re.compile(
    r"(?:according to|said|stated|quoted|wrote|reports?|per)\s[^.]{0,48}$", re.I
)

_TARGET_RICH_RE = re.compile(_ACTION_TARGET, re.I)

II_RULE_SEVERITY: dict[str, PromptSeverity] = {
    "ii-001": PromptSeverity.HIGH,
    "ii-002": PromptSeverity.MEDIUM,
    "ii-003": PromptSeverity.HIGH,
    "ii-004": PromptSeverity.MEDIUM,
    "ii-005": PromptSeverity.HIGH,
}

II_BASE_CONFIDENCE: dict[str, float] = {
    "ii-001": 0.90,
    "ii-002": 0.75,
    "ii-003": 0.85,
    "ii-004": 0.80,
    "ii-005": 0.70,
}

II_RULE_NAMES: dict[str, str] = {
    "ii-001": "Untrusted Content: Instruction Override",
    "ii-002": "Untrusted Content: Structured Directive Injection",
    "ii-003": "Untrusted Content: Obfuscated Injection Payload",
    "ii-004": "Untrusted Content: Agent-Directed Action",
    "ii-005": "Untrusted Content: Cross-Segment Instruction Assembly",
}

II_RULE_DESCRIPTIONS: dict[str, str] = {
    "ii-001": "Instruction override directive found in untrusted content",
    "ii-002": "Structured directive block impersonating system instructions "
    "found in untrusted content",
    "ii-003": "Encoded or homoglyph-obfuscated injection payload found in untrusted content",
    "ii-004": "Actionable exfiltration/tool-execution directive aimed at the agent "
    "found in untrusted content",
    "ii-005": "Injection directive assembled across multiple untrusted segments",
}


# ============================================================================
# Context payload construction / preparation
# ============================================================================


def build_untrusted_context(
    segments: Sequence[ContentSegment],
    config: IndirectInjectionConfig | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe untrusted-context payload from content segments.

    Trusted segments are excluded from scanning entirely. Segments beyond
    ``config.max_segments`` are counted as omitted. Oversized segments are
    truncated to ``config.segment_max_bytes`` and flagged.

    Args:
        segments: The content segments accompanying a prompt.
        config: Indirect injection configuration.

    Returns:
        JSON-safe dictionary suitable for storage in
        ``PromptFeatures.metadata["untrusted_context"]``.
    """
    cfg = config or IndirectInjectionConfig()
    entries: list[dict[str, Any]] = []
    omitted = 0
    trusted_count = 0

    for idx, segment in enumerate(segments):
        if len(entries) >= cfg.max_segments:
            omitted += 1
            continue
        source_type = SourceType(segment.source_type).value
        trust = _derive_trust(source_type, segment.trust)
        if trust == SegmentTrust.TRUSTED.value or _is_allowlisted(segment, cfg):
            trusted_count += 1
            continue
        content = segment.content or ""
        truncated = False
        byte_length = len(content.encode("utf-8"))
        if byte_length > cfg.segment_max_bytes:
            content = _truncate_to_byte_limit(content, cfg.segment_max_bytes)
            truncated = True
        entries.append(
            {
                "index": idx,
                "source_type": source_type,
                "trust": trust,
                "source_id": segment.source_id,
                "uri": segment.uri,
                "position": segment.position,
                "content": content,
                "truncated": truncated,
                "byte_length": byte_length,
            }
        )

    return {
        "version": 1,
        "enabled": cfg.enabled,
        "quote_discount": cfg.quote_discount,
        "code_discount": cfg.code_discount,
        "weights": {
            k: resolve_weight(cfg, k)
            for k in {e["source_type"] for e in entries} | set(DEFAULT_SOURCE_WEIGHTS)
        },
        "disabled_rules": list(cfg.disabled_rules),
        "segments_omitted": omitted,
        "trusted_count": trusted_count,
        "segments": entries,
    }


def _homoglyph_substitute(text: str) -> tuple[str, bool]:
    """Replace confusable characters with their Latin lookalikes."""
    confusables = detect_confusables(text)
    if not confusables:
        return text, False
    chars = list(text)
    for conf in confusables:
        pos = conf["position"]
        if isinstance(pos, int) and 0 <= pos < len(chars):
            chars[pos] = str(conf["lookalike"])
    return "".join(chars), True


def prepare_context(context_payload: dict[str, Any]) -> None:
    """Prepare per-segment analysis variants inside a context payload.

    Idempotent: fills ``norm``, ``subst``, ``subst_applied`` and
    ``decoded_variants`` fields once, guarded by the ``prepared`` flag.
    All values remain JSON-safe primitives.

    Each decoded variant carries its P1-2 encoding chain and depth so
    findings can cite provenance. Reuses P1-2 recursive decoding and P1-1
    confusable mappings; neither module is modified.
    """
    if context_payload.get("prepared"):
        return

    from q_guardian.security.pipeline import PromptNormalizer

    normalizer = PromptNormalizer()
    for entry in context_payload.get("segments", []):
        raw = str(entry.get("content", ""))
        norm = normalizer.normalize(raw)
        subst, subst_applied = _homoglyph_substitute(norm)

        try:
            decode_results = decode_recursive(norm)
        except Exception:  # pragma: no cover - P1-2 never raises in practice
            decode_results = []
        seen_texts: set[str] = set()
        decoded_variants: list[dict[str, Any]] = []
        for result in sorted(decode_results, key=lambda r: (-r.confidence, -r.depth)):
            text = result.decoded[:_MAX_DECODED_VARIANT_LENGTH]
            if not text or text in seen_texts or text == norm:
                continue
            seen_texts.add(text)
            decoded_variants.append(
                {
                    "text": text,
                    "encoding_chain": [str(step) for step in result.encoding_chain],
                    "decoding_depth": result.depth,
                }
            )
            if len(decoded_variants) >= _MAX_DECODED_VARIANTS:
                break

        entry["norm"] = norm
        entry["subst"] = subst if subst_applied else ""
        entry["subst_applied"] = subst_applied
        entry["decoded_variants"] = decoded_variants

    context_payload["prepared"] = True


# ============================================================================
# Match helpers (discounts, deduplication, finding factory)
# ============================================================================


def _fenced_spans(text: str) -> list[tuple[int, int]]:
    """Return character spans of fenced code blocks."""
    return [(m.start(), m.end()) for m in _FENCE_RE.finditer(text)]


def _match_discount(
    text: str,
    start: int,
    end: int,
    quote_discount: float,
    code_discount: float,
) -> tuple[float, dict[str, Any]]:
    """Compute the confidence discount factor for a match span.

    Returns the multiplicative factor (floored at 0.2) and metadata about
    which discounts applied.
    """
    matched_text = text[start:end]
    factor = 1.0
    quoted = False
    attributed = False
    in_code = False

    before = text[max(0, start - 64) : start]
    after = text[end : end + 2]
    for open_quote, close_quote in _QUOTE_PAIRS:
        if before.endswith(open_quote) and after.startswith(close_quote):
            quoted = True
            break
    if not quoted and _ATTRIBUTION_RE.search(before):
        attributed = True

    if quoted or attributed:
        factor *= quote_discount

    if any(fs <= start and end <= fe for fs, fe in _fenced_spans(text)):
        in_code = True
        if not _TARGET_RICH_RE.search(matched_text):
            factor *= code_discount

    factor = max(0.2, factor)
    details: dict[str, Any] = {
        "discount_factor": round(factor, 3),
        "discounted": factor < 1.0,
    }
    if quoted:
        details["in_quotes"] = True
    if attributed:
        details["attributed"] = True
    if in_code:
        details["in_code_block"] = True
    return factor, details


class _Deduper:
    """Collapse duplicate matches across segments, keeping highest confidence."""

    def __init__(self) -> None:
        self._seen: dict[str, tuple[float, PromptFinding]] = {}

    def add(self, snippet: str, finding: PromptFinding) -> None:
        key = re.sub(r"\s+", " ", snippet.strip().lower())
        existing = self._seen.get(key)
        if existing is None or finding.confidence > existing[0]:
            self._seen[key] = (finding.confidence, finding)

    def findings(self) -> list[PromptFinding]:
        return [finding for _, finding in self._seen.values()]


def _make_finding(
    rule_id: str,
    entry: dict[str, Any],
    variant: str,
    snippet: str,
    confidence: float,
    severity: PromptSeverity | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> PromptFinding:
    """Build a provenance-rich indirect injection finding."""
    metadata: dict[str, Any] = {
        "indirect_injection": True,
        "segment_index": entry.get("index"),
        "source_type": entry.get("source_type"),
        "trust": entry.get("trust"),
        "source_id": entry.get("source_id", ""),
        "uri": entry.get("uri", ""),
        "position": entry.get("position", 0),
        "variant": variant,
        "evidence_snippet": snippet[:_MAX_SNIPPET_LENGTH],
    }
    if entry.get("truncated"):
        metadata["segment_truncated"] = True
    if extra_metadata:
        metadata.update(extra_metadata)
    return PromptFinding(
        rule_id=rule_id,
        rule_name=II_RULE_NAMES.get(rule_id, rule_id),
        category=PromptCategory.INDIRECT_INJECTION,
        severity=severity or II_RULE_SEVERITY.get(rule_id, PromptSeverity.MEDIUM),
        description=II_RULE_DESCRIPTIONS.get(rule_id, "Indirect injection detected"),
        matched_text=snippet[:_MAX_SNIPPET_LENGTH],
        confidence=round(min(0.99, max(0.05, confidence)), 4),
        metadata=metadata,
    )


# ============================================================================
# Rule evaluators (shared by detector and RuleEngine guard branch)
# ============================================================================


def _entry_weight(entry: dict[str, Any], context_payload: dict[str, Any]) -> float:
    weights = context_payload.get("weights") or DEFAULT_SOURCE_WEIGHTS
    weight = weights.get(str(entry.get("source_type")), 0.85)
    try:
        return min(1.0, max(0.1, float(weight)))
    except (TypeError, ValueError):
        return 0.85


def _iter_variant_texts(
    entry: dict[str, Any],
    include_primary: bool,
) -> Iterable[tuple[str, str, dict[str, Any]]]:
    """Yield ``(variant_name, text, extra_metadata)`` triples for an entry.

    ``include_primary`` controls whether the normalized primary text is
    yielded; obfuscated variants (homoglyph-substituted, decoded) are
    always included when available.
    """
    norm = str(entry.get("norm", ""))
    if include_primary and norm:
        yield "normalized", norm, {}
    subst = str(entry.get("subst", ""))
    if entry.get("subst_applied") and subst and subst != norm:
        yield "homoglyph_substituted", subst, {"homoglyph_substituted": True}
    for decoded in entry.get("decoded_variants") or []:
        yield (
            "decoded",
            str(decoded.get("text", "")),
            {
                "encoding_chain": list(decoded.get("encoding_chain", [])),
                "decoding_depth": decoded.get("decoding_depth", 0),
            },
        )


def _eval_ii001(entries: list[dict[str, Any]], ctx: dict[str, Any]) -> list[PromptFinding]:
    deduper = _Deduper()
    quote_discount = float(ctx.get("quote_discount", 0.6))
    code_discount = float(ctx.get("code_discount", 0.7))
    hit_indexes: list[int] = []

    for entry in entries:
        norm = str(entry.get("norm", ""))
        if not norm:
            continue
        for pattern in _OVERRIDE_PATTERNS:
            match = pattern.search(norm)
            if match is None:
                continue
            snippet = norm[match.start() : match.end()]
            factor, discount_meta = _match_discount(
                norm, match.start(), match.end(), quote_discount, code_discount
            )
            confidence = II_BASE_CONFIDENCE["ii-001"] * _entry_weight(entry, ctx) * factor
            finding = _make_finding(
                "ii-001",
                entry,
                "normalized",
                snippet,
                confidence,
                extra_metadata=discount_meta,
            )
            deduper.add(snippet, finding)
            hit_indexes.append(int(entry.get("index", -1)))
            break

    ctx.setdefault("emitted_indexes", {})["ii-001"] = sorted(set(hit_indexes))
    return deduper.findings()


def _marker_windows(text: str) -> list[tuple[int, str]]:
    """Locate structured-directive markers and their following windows."""
    windows: list[tuple[int, str]] = []
    for match in _MARKER_RE.finditer(text):
        window_start = match.start(2)
        windows.append((window_start, str(match.group(2))))
    for marker_pattern in (_XML_TAG_RE, _BRACKET_RE, _HEADING_RE):
        for match in marker_pattern.finditer(text):
            windows.append((match.end(), text[match.end() : match.end() + 180]))
    return windows


def _eval_ii002(entries: list[dict[str, Any]], ctx: dict[str, Any]) -> list[PromptFinding]:
    deduper = _Deduper()
    quote_discount = float(ctx.get("quote_discount", 0.6))
    code_discount = float(ctx.get("code_discount", 0.7))

    for entry in entries:
        norm = str(entry.get("norm", ""))
        if not norm:
            continue
        for window_start, window in _marker_windows(norm):
            imperative = _IMPERATIVE_RE.search(window)
            if imperative is None:
                continue
            snippet = norm[window_start : window_start + imperative.end()]
            if not snippet.strip():
                continue
            factor, discount_meta = _match_discount(
                norm,
                window_start,
                window_start + imperative.end(),
                quote_discount,
                code_discount,
            )
            confidence = II_BASE_CONFIDENCE["ii-002"] * _entry_weight(entry, ctx) * factor
            deduper.add(
                snippet,
                _make_finding(
                    "ii-002",
                    entry,
                    "normalized",
                    snippet,
                    confidence,
                    extra_metadata=discount_meta,
                ),
            )
    return deduper.findings()


_OBFUSCATED_PATTERNS: tuple[re.Pattern[str], ...] = (
    *_OVERRIDE_PATTERNS,
    *_ACTION_PATTERNS,
)


def _eval_ii003(entries: list[dict[str, Any]], ctx: dict[str, Any]) -> list[PromptFinding]:
    deduper = _Deduper()
    quote_discount = float(ctx.get("quote_discount", 0.6))
    code_discount = float(ctx.get("code_discount", 0.7))

    for entry in entries:
        for variant, text, variant_meta in _iter_variant_texts(entry, include_primary=False):
            for pattern in _OBFUSCATED_PATTERNS:
                match = pattern.search(text)
                if match is None:
                    continue
                snippet = text[match.start() : match.end()]
                factor, discount_meta = _match_discount(
                    text, match.start(), match.end(), quote_discount, code_discount
                )
                extra: dict[str, Any] = {**discount_meta, **variant_meta}
                confidence = II_BASE_CONFIDENCE["ii-003"] * _entry_weight(entry, ctx) * factor
                deduper.add(
                    snippet,
                    _make_finding(
                        "ii-003",
                        entry,
                        variant,
                        snippet,
                        confidence,
                        extra_metadata=extra,
                    ),
                )
                break
    return deduper.findings()


def _eval_ii004(entries: list[dict[str, Any]], ctx: dict[str, Any]) -> list[PromptFinding]:
    deduper = _Deduper()
    quote_discount = float(ctx.get("quote_discount", 0.6))
    code_discount = float(ctx.get("code_discount", 0.7))

    for entry in entries:
        norm = str(entry.get("norm", ""))
        if not norm:
            continue
        matches: list[re.Match[str]] = []
        for pattern in _ACTION_PATTERNS:
            matches.extend(pattern.finditer(norm))
        if not matches:
            continue
        spans: list[tuple[int, int]] = []
        for match in sorted(matches, key=lambda m: (m.start(), -(m.end() - m.start()))):
            if spans and match.start() < spans[-1][1]:
                start, end = spans[-1]
                spans[-1] = (start, max(end, match.end()))
            else:
                spans.append((match.start(), match.end()))
        for start, end in spans:
            snippet = norm[start:end]
            factor, discount_meta = _match_discount(norm, start, end, quote_discount, code_discount)
            window = norm[max(0, start - 40) : end + 120]
            destination = _EXTERNAL_DESTINATION_RE.search(window)
            severity = PromptSeverity.HIGH if destination else II_RULE_SEVERITY["ii-004"]
            extra = {**discount_meta}
            if destination:
                extra["external_destination"] = destination.group(1).rstrip(".,;!?")[:100]
                extra["escalated_severity"] = True
            confidence = II_BASE_CONFIDENCE["ii-004"] * _entry_weight(entry, ctx) * factor
            deduper.add(
                snippet,
                _make_finding(
                    "ii-004",
                    entry,
                    "normalized",
                    snippet,
                    confidence,
                    severity=severity,
                    extra_metadata=extra,
                ),
            )
    return deduper.findings()


def _eval_ii005(entries: list[dict[str, Any]], ctx: dict[str, Any]) -> list[PromptFinding]:
    emitted = ctx.get("emitted_indexes") or {}
    override_hits = set(emitted.get("ii-001") or [])

    contributing: list[dict[str, Any]] = []
    fragments: list[str] = []
    for entry in entries:
        index = int(entry.get("index", -1))
        if index in override_hits:
            continue
        norm = str(entry.get("norm", ""))
        match = _FRAGMENT_RE.search(norm)
        if match is not None:
            contributing.append(entry)
            fragments.append(match.group(0))

    if len(contributing) < 2:
        return []

    refs = [
        {
            "segment_index": entry.get("index"),
            "source_type": entry.get("source_type"),
            "source_id": entry.get("source_id", ""),
        }
        for entry in contributing
    ]
    weights = [_entry_weight(entry, ctx) for entry in contributing]
    weight = min(weights) if weights else 0.85
    confidence = II_BASE_CONFIDENCE["ii-005"] * weight
    snippet = " + ".join(fragment.strip().lower() for fragment in fragments[:4])
    finding = _make_finding(
        "ii-005",
        contributing[0],
        "cross_segment",
        snippet,
        confidence,
        extra_metadata={
            "contributing_segments": refs,
            "segment_count": len(contributing),
        },
    )
    return [finding]


_RULE_EVALUATORS = {
    "ii-001": _eval_ii001,
    "ii-002": _eval_ii002,
    "ii-003": _eval_ii003,
    "ii-004": _eval_ii004,
    "ii-005": _eval_ii005,
}


def evaluate_indirect_rule(
    rule_id: str,
    context_payload: dict[str, Any],
) -> list[PromptFinding]:
    """Evaluate a single ``ii-*`` rule against an untrusted-context payload.

    This is the shared evaluation path used both by
    :class:`IndirectInjectionDetector` and by the ``RuleEngine`` guard
    branch. It never fires unless the payload carries prepared untrusted
    segments, so ordinary direct prompt analysis is unaffected.

    Args:
        rule_id: One of ``ii-001`` .. ``ii-005``.
        context_payload: Payload built by :func:`build_untrusted_context`.

    Returns:
        Findings for the requested rule (possibly empty).
    """
    evaluator = _RULE_EVALUATORS.get(rule_id)
    if evaluator is None:
        return []
    if not context_payload.get("enabled", True):
        return []
    if rule_id in (context_payload.get("disabled_rules") or []):
        return []
    prepare_context(context_payload)
    entries = [
        entry
        for entry in context_payload.get("segments", [])
        if str(entry.get("trust")) != SegmentTrust.TRUSTED.value
    ]
    if not entries:
        return []
    return evaluator(entries, context_payload)


# ============================================================================
# Detector API
# ============================================================================


class IndirectInjectionDetector:
    """Detects indirect injection directives in untrusted content segments."""

    def __init__(self, config: IndirectInjectionConfig | None = None) -> None:
        """Initialize the detector.

        Args:
            config: Indirect injection configuration; defaults are used
                when omitted.
        """
        self._config = config or IndirectInjectionConfig()

    @property
    def config(self) -> IndirectInjectionConfig:
        """Return the active configuration."""
        return self._config

    def analyze_segments(self, segments: Sequence[ContentSegment]) -> list[PromptFinding]:
        """Analyze content segments and return indirect injection findings.

        Args:
            segments: Content segments with declared provenance.

        Returns:
            Deduplicated findings across all enabled ``ii-*`` rules.
        """
        if not self._config.enabled or not segments:
            return []
        context_payload = build_untrusted_context(list(segments), self._config)
        findings: list[PromptFinding] = []
        for rule_id in ("ii-001", "ii-002", "ii-003", "ii-004", "ii-005"):
            if rule_id in self._config.disabled_rules:
                continue
            findings.extend(evaluate_indirect_rule(rule_id, context_payload))
        return findings

    def analyze_segment(self, segment: ContentSegment) -> list[PromptFinding]:
        """Analyze a single content segment.

        Args:
            segment: The content segment to analyze.

        Returns:
            Findings for the single segment.
        """
        return self.analyze_segments([segment])


def scan_untrusted(
    segments: Sequence[ContentSegment],
    config: IndirectInjectionConfig | None = None,
) -> list[PromptFinding]:
    """Scan untrusted content segments for indirect injection directives.

    Convenience functional wrapper around
    :class:`IndirectInjectionDetector`.

    Args:
        segments: Content segments with declared provenance.
        config: Optional configuration overriding defaults.

    Returns:
        Deduplicated findings across all enabled ``ii-*`` rules.
    """
    return IndirectInjectionDetector(config).analyze_segments(segments)


__all__ = [
    "DEFAULT_SOURCE_WEIGHTS",
    "II_BASE_CONFIDENCE",
    "II_RULE_DESCRIPTIONS",
    "II_RULE_NAMES",
    "II_RULE_SEVERITY",
    "TRUSTED_SOURCE_TYPES",
    "ContentSegment",
    "IndirectInjectionConfig",
    "IndirectInjectionDetector",
    "SegmentTrust",
    "SourceType",
    "build_untrusted_context",
    "evaluate_indirect_rule",
    "prepare_context",
    "scan_untrusted",
]
