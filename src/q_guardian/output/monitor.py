"""Output monitoring orchestrator helpers (P3-3).

Builds the JSON-safe ``output_context`` payload consumed by the guarded
``om-*`` rules in :mod:`q_guardian.output.rules`, resolves configuration,
and prepares decoded payload variants for obfuscation analysis.

Detection logic lives in the rule evaluators; this module only assembles
provenance payloads by reusing existing P1-2 decoding, P3-5 untrusted-context
preparation, and the shared normalization pipeline.
"""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.security.config import OutputMonitoringConfig
from q_guardian.security.encoding import (
    decode_base64,
    decode_hex,
    decode_rot13,
    decode_url,
)
from q_guardian.security.indirect import ContentSegment, build_untrusted_context
from q_guardian.security.pipeline import PromptNormalizer

logger = structlog.get_logger("output.monitor")

_DECODERS = {
    "base64": decode_base64,
    "rot13": decode_rot13,
    "hex": decode_hex,
    "url": decode_url,
}


def resolve_output_config(raw: Any) -> OutputMonitoringConfig:
    """Resolve an output-monitoring configuration from user input.

    Args:
        raw: ``None``, an :class:`OutputMonitoringConfig`, or a plain
            dictionary of config fields.

    Returns:
        A validated configuration instance (defaults when unusable).
    """
    if isinstance(raw, OutputMonitoringConfig):
        return raw
    if isinstance(raw, dict):
        try:
            return OutputMonitoringConfig.model_validate(raw)
        except Exception:
            logger.warning("invalid_output_config", exc_info=True)
    return OutputMonitoringConfig()


def prepare_decoded_variants(
    normalized: str,
    config: OutputMonitoringConfig,
) -> list[str]:
    """Decode candidate encoded spans for om-006 marker inspection.

    Reuses the P1-2 decoders; no new codec logic is introduced. Each
    variant is truncated to ``decoded_preview_chars`` and at most
    ``max_decoded_variants`` variants are returned.

    Args:
        normalized: Normalized output text.
        config: Output monitoring configuration.

    Returns:
        List of decoded text variants (possibly empty).
    """
    from q_guardian.security.encoding import detect_all_encodings

    variants: list[str] = []
    seen: set[str] = set()
    if not normalized or config.max_decoded_variants <= 0:
        return variants

    from q_guardian.security.encoding import EncodingCandidate

    candidates: list[EncodingCandidate] = detect_all_encodings(normalized)
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    for candidate in candidates:
        if len(variants) >= config.max_decoded_variants:
            break
        decoder = _DECODERS.get(candidate.encoding)
        if decoder is None:
            continue
        try:
            decoded: str | None = decoder(candidate.matched_text)
        except Exception:
            decoded = None
        if not decoded or not decoded.strip():
            continue
        trimmed = decoded[: config.decoded_preview_chars]
        if trimmed in seen:
            continue
        seen.add(trimmed)
        variants.append(trimmed)
    return variants


def build_output_context(
    normalized: str,
    source_label: str,
    config: OutputMonitoringConfig,
    context_segments: list[ContentSegment] | None = None,
) -> dict[str, Any]:
    """Build the JSON-safe ``output_context`` payload for a scan.

    The payload carries the direction gate, the normalized output text,
    decoded variants for om-006, and (when supplied) prepared correlation
    segments — built through the P3-5 untrusted-context machinery so trust
    handling, caps, and truncation semantics are shared rather than
    duplicated. Word-shingle hashes are precomputed per segment for the
    om-007 propagation check.

    Args:
        normalized: Normalized output text.
        source_label: Provenance label describing the output origin.
        config: Output monitoring configuration.
        context_segments: Optional untrusted input segments to correlate.

    Returns:
        JSON-safe dictionary stored on ``features.metadata["output_context"]``.
    """
    from q_guardian.output.rules import _word_shingles

    payload: dict[str, Any] = {
        "direction": "output",
        "prepared": True,
        "source_label": source_label,
        "normalized": normalized[: config.max_output_length],
        "disabled_rules": list(config.disabled_rules),
        "quote_discount": config.quote_discount,
        "code_discount": config.code_discount,
        "secret_entropy_threshold": config.secret_entropy_threshold,
        "correlation_shingle_words": config.correlation_shingle_words,
        "correlation_min_shingles": config.correlation_min_shingles,
        "correlation_overlap_threshold": config.correlation_overlap_threshold,
        "decoded_variants": prepare_decoded_variants(normalized, config),
    }

    if context_segments:
        indirect_view = build_untrusted_context(context_segments)
        from q_guardian.security.indirect import prepare_context

        prepare_context(indirect_view)
        segments_out: list[dict[str, Any]] = []
        shingle_size = config.correlation_shingle_words
        for entry in indirect_view.get("segments", []):
            norm = str(entry.get("norm", ""))
            if not norm:
                continue
            enriched = dict(entry)
            enriched["shingles"] = _word_shingles(norm, shingle_size)
            segments_out.append(enriched)
        payload["segments"] = segments_out
        payload["segments_omitted"] = indirect_view.get("segments_omitted", 0)
        payload["trusted_count"] = indirect_view.get("trusted_count", 0)

    return payload


_NORMALIZER = PromptNormalizer()


def normalize_output(text: str) -> str:
    """Normalize output text using the shared prompt normalizer."""
    return _NORMALIZER.normalize(text)


__all__ = [
    "build_output_context",
    "normalize_output",
    "prepare_decoded_variants",
    "resolve_output_config",
]
