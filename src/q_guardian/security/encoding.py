"""Safe encoding detection and decoding utilities for Q-Guardian.

Provides safe, bounded decoding utilities for common encoding/obfuscation
mechanisms used in prompt injection attacks. All decoders are bounded,
preserve the original input, and never execute or evaluate decoded content.
"""

from __future__ import annotations

import base64
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any

# ============================================================================
# Safety Limits
# ============================================================================

# Maximum input length to process (matches existing max_prompt_length)
MAX_INPUT_LENGTH: int = 100_000

# Maximum decoded output length per decoding attempt
MAX_DECODED_LENGTH: int = 50_000

# Maximum recursive decoding depth
MAX_DECODE_DEPTH: int = 3

# Maximum number of decoding attempts per input (one per encoding type)
MAX_DECODE_ATTEMPTS: int = 4

# Maximum safe preview length for findings/metadata
MAX_PREVIEW_LENGTH: int = 200

# Minimum candidate lengths to reduce false positives
MIN_BASE64_LENGTH: int = 20
MIN_ROT13_LENGTH: int = 30
MIN_HEX_LENGTH: int = 20
MIN_URL_ENCODED_DENSITY: float = 0.05  # 5% of chars must be %XX (lowered for sparse encoding)

# ============================================================================
# Result Types
# ============================================================================


@dataclass(frozen=True)
class DecodeResult:
    """Result of a successful decode operation."""

    encoding: str
    original: str
    decoded: str
    depth: int
    encoding_chain: tuple[str, ...]
    confidence: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class EncodingCandidate:
    """A detected encoding candidate before decoding."""

    encoding: str
    matched_text: str
    position: int
    confidence: float
    metadata: dict[str, Any]


# ============================================================================
# Base64 Detection & Decoding
# ============================================================================

# Standard Base64 alphabet
_BASE64_STANDARD_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
# URL-safe Base64 alphabet
_BASE64_URLSAFE_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")

# Regex for standard Base64 (with optional padding)
_BASE64_STANDARD_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
# Regex for URL-safe Base64 (with optional padding)
_BASE64_URLSAFE_RE = re.compile(r"^[A-Za-z0-9_-]+=*$")


def _is_valid_base64_alphabet(text: str, url_safe: bool = False) -> bool:
    """Check if text contains only valid Base64 alphabet characters."""
    alphabet = _BASE64_URLSAFE_ALPHABET if url_safe else _BASE64_STANDARD_ALPHABET
    return all(c in alphabet for c in text)


def _has_valid_base64_padding(text: str) -> bool:
    """Validate Base64 padding is correct."""
    if "=" not in text:
        return True  # Unpadded is acceptable
    # Count padding chars
    pad_count = text.count("=")
    if pad_count > 2:
        return False
    # Padding must be at the end
    if not text.endswith("=" * pad_count):
        return False
    # Check that padding aligns with 4-char blocks
    return len(text) % 4 == 0


def _looks_like_base64(text: str, min_length: int = MIN_BASE64_LENGTH) -> tuple[bool, bool]:
    """Heuristic check if text looks like Base64.
    Returns (is_base64, is_url_safe).
    """
    if len(text) < min_length:
        return False, False

    # Quick reject: too many non-alphanumeric chars that aren't Base64 symbols
    non_alnum = sum(1 for c in text if not c.isalnum())
    if non_alnum > len(text) * 0.15:  # More than 15% special chars
        return False, False

    # Check standard Base64
    if (
        _BASE64_STANDARD_RE.match(text)
        and _has_valid_base64_padding(text)
        and _is_valid_base64_alphabet(text, url_safe=False)
    ):
        return True, False

    # Check URL-safe Base64
    if _BASE64_URLSAFE_RE.match(text) and _is_valid_base64_alphabet(text, url_safe=True):
        return True, True

    return False, False


def decode_base64(
    text: str,
    max_length: int = MAX_DECODED_LENGTH,
    min_length: int = MIN_BASE64_LENGTH,
) -> str | None:
    """Safely decode Base64 text.
    Returns decoded string or None if decoding fails.
    """
    if len(text) > MAX_INPUT_LENGTH:
        return None

    is_b64, is_url_safe = _looks_like_base64(text, min_length=min_length)
    if not is_b64:
        return None

    try:
        if is_url_safe:
            decoded_bytes = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        else:
            decoded_bytes = base64.b64decode(text + "=" * (-len(text) % 4))

        if len(decoded_bytes) > max_length:
            return None

        # Try to decode as UTF-8
        return decoded_bytes.decode("utf-8")
    except Exception:
        return None


def detect_base64_candidates(
    text: str,
    min_length_override: int | None = None,
) -> list[EncodingCandidate]:
    """Detect potential Base64 encoded segments in text."""
    candidates: list[EncodingCandidate] = []

    min_len = min_length_override if min_length_override is not None else MIN_BASE64_LENGTH
    if len(text) < min_len:
        return candidates

    # Look for Base64-like segments (word boundaries)
    # Split on whitespace and common delimiters
    segments = re.split(r"[\s\n\r\t,;|]+", text)

    for segment in segments:
        if len(segment) < min_len:
            continue

        is_b64, _ = _looks_like_base64(segment, min_length=min_len)
        if not is_b64:
            continue

        decoded = decode_base64(segment, min_length=min_len)
        if decoded is None:
            continue

        # Boost confidence if decoded text looks like meaningful text
        confidence = 0.5
        if decoded and _is_meaningful_text(decoded):
            confidence = 0.75

        candidates.append(
            EncodingCandidate(
                encoding="base64",
                matched_text=segment[:MAX_PREVIEW_LENGTH],
                position=text.find(segment),
                confidence=confidence,
                metadata={
                    "url_safe": False,
                    "decoded_preview": decoded[:MAX_PREVIEW_LENGTH],
                    "decoded_length": len(decoded),
                },
            )
        )

    return candidates


# ============================================================================
# ROT13 Detection & Decoding
# ============================================================================

# ROT13 translation table
_ROT13_TRANS = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm",
)


def decode_rot13(text: str, max_length: int = MAX_DECODED_LENGTH) -> str | None:
    """Safely apply ROT13 transformation."""
    if len(text) > max_length:
        return None
    return text.translate(_ROT13_TRANS)


def _is_meaningful_text(text: str) -> bool:
    """Heuristic: check if text contains meaningful English words."""
    if not text or len(text) < 10:
        return False

    # Count alphabetic characters
    alpha_count = sum(1 for c in text if c.isalpha())
    if alpha_count == 0:
        return False

    alpha_ratio = alpha_count / len(text)
    if alpha_ratio < 0.5:
        return False

    # Check for common English words
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    if len(words) < 2:
        return False

    common_words = {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "her",
        "was",
        "one",
        "our",
        "out",
        "day",
        "get",
        "has",
        "him",
        "his",
        "how",
        "its",
        "may",
        "new",
        "now",
        "old",
        "see",
        "two",
        "who",
        "boy",
        "did",
        "she",
        "use",
        "way",
        "ign",
        "ore",
        "pre",
        "vious",
        "instruct",
        "injection",
        "jailbreak",
        "bypass",
        "override",
        "system",
        "prompt",
        "ignore",
        "forget",
        "reveal",
        "secret",
        "password",
        "token",
        "admin",
        "root",
        "sudo",
        "hack",
        "hello",
        "world",
        "test",
        "this",
        "that",
        "with",
        "from",
        "have",
        "been",
        "will",
        "would",
        "could",
        "should",
        "what",
        "when",
        "where",
        "which",
        "there",
        "their",
        "here",
        "more",
        "some",
        "any",
        "many",
        "such",
        "into",
        "over",
        "under",
        "after",
        "before",
        "during",
        "while",
        "since",
        "until",
        "unless",
        "because",
        "though",
        "although",
        "however",
        "therefore",
    }

    # Exclude rot13/ebg13 from matching as meaningful (these are encoding artifacts)
    filtered_words = [w for w in words if w not in ("rot13", "ebg13", "rot", "ebg")]

    matches = sum(1 for w in filtered_words if w in common_words)
    # Require actual dictionary word matches (not just vowel presence)
    # This avoids false positives on ROT13 text which happens to have vowels
    return matches >= 1


def detect_rot13_candidates(
    text: str,
    min_length_override: int | None = None,
) -> list[EncodingCandidate]:
    """Detect potential ROT13 encoded segments."""
    candidates: list[EncodingCandidate] = []

    min_len = min_length_override if min_length_override is not None else MIN_ROT13_LENGTH
    if len(text) < min_len:
        return candidates

    # ROT13 only affects alphabetic characters
    # Check if text is mostly alphabetic
    alpha_count = sum(1 for c in text if c.isalpha())
    if alpha_count / len(text) < 0.6:  # Less strict: 60% alphabetic
        return candidates

    # Additional check: ROT13 text should not look like Base64
    # Base64 contains +, /, = which ROT13 doesn't produce
    if any(c in text for c in "+/="):
        return candidates

    # Check if it looks like Base64 (high mix of upper/lower/digits)
    upper = sum(1 for c in text if c.isupper())
    lower = sum(1 for c in text if c.islower())
    digit = sum(1 for c in text if c.isdigit())
    total = len(text)
    if digit / total > 0.1 and upper / total > 0.2 and lower / total > 0.2:
        # Looks like Base64, not ROT13
        return candidates

    # Additional check: the original text should NOT look like meaningful English
    # If the original text is already meaningful English, it's probably not ROT13 encoded
    if _is_meaningful_text(text):
        return candidates

    decoded = decode_rot13(text)
    if decoded is None:
        return candidates

    confidence = 0.3
    if _is_meaningful_text(decoded):
        confidence = 0.6

    candidates.append(
        EncodingCandidate(
            encoding="rot13",
            matched_text=text[:MAX_PREVIEW_LENGTH],
            position=0,
            confidence=confidence,
            metadata={
                "decoded_preview": decoded[:MAX_PREVIEW_LENGTH],
                "decoded_length": len(decoded),
            },
        )
    )

    return candidates


# ============================================================================
# Hex Detection & Decoding
# ============================================================================

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_HEX_SEPARATED_RE = re.compile(r"^([0-9a-fA-F]{2}[-\s:])*[0-9a-fA-F]{2}$")


def decode_hex(text: str, max_length: int = MAX_DECODED_LENGTH) -> str | None:
    """Safely decode hexadecimal text."""
    # Remove common separators
    clean = re.sub(r"[-\s:]", "", text)

    if len(clean) < MIN_HEX_LENGTH or len(clean) % 2 != 0:
        return None

    if not _HEX_RE.match(clean):
        return None

    if len(clean) > max_length * 2:
        return None

    try:
        decoded_bytes = bytes.fromhex(clean)
        if len(decoded_bytes) > max_length:
            return None
        return decoded_bytes.decode("utf-8")
    except Exception:
        return None


def detect_hex_candidates(
    text: str,
    min_length_override: int | None = None,
) -> list[EncodingCandidate]:
    """Detect potential hex-encoded segments."""
    candidates: list[EncodingCandidate] = []

    min_len = min_length_override if min_length_override is not None else MIN_HEX_LENGTH
    if len(text) < min_len:
        return candidates

    # Check contiguous hex
    segments = re.split(r"[\s\n\r\t,;|]+", text)

    for segment in segments:
        if len(segment) < MIN_HEX_LENGTH:
            continue

        # Try contiguous hex
        clean = re.sub(r"[-\s:]", "", segment)
        if len(clean) >= MIN_HEX_LENGTH and len(clean) % 2 == 0 and _HEX_RE.match(clean):
            decoded = decode_hex(segment)
            if decoded is not None:
                # For hex, we accept any valid UTF-8 decode (may be further encoded)
                confidence = 0.7
                # Boost confidence if decoded text looks meaningful
                if _is_meaningful_text(decoded):
                    confidence = 0.85
                candidates.append(
                    EncodingCandidate(
                        encoding="hex",
                        matched_text=segment[:MAX_PREVIEW_LENGTH],
                        position=text.find(segment),
                        confidence=confidence,
                        metadata={
                            "format": "contiguous",
                            "decoded_preview": decoded[:MAX_PREVIEW_LENGTH],
                            "decoded_length": len(decoded),
                        },
                    )
                )

        # Check byte-separated hex (e.g., "48 65 6c 6c 6f" or "48-65-6c-6c-6f")
        if _HEX_SEPARATED_RE.match(segment):
            decoded = decode_hex(segment)
            if decoded is not None:
                confidence = 0.75
                if _is_meaningful_text(decoded):
                    confidence = 0.85
                candidates.append(
                    EncodingCandidate(
                        encoding="hex",
                        matched_text=segment[:MAX_PREVIEW_LENGTH],
                        position=text.find(segment),
                        confidence=confidence,
                        metadata={
                            "format": "separated",
                            "decoded_preview": decoded[:MAX_PREVIEW_LENGTH],
                            "decoded_length": len(decoded),
                        },
                    )
                )

    return candidates


# ============================================================================
# URL Percent-Encoding Detection & Decoding
# ============================================================================

_URL_ENCODED_RE = re.compile(r"%[0-9A-Fa-f]{2}")


def decode_url(text: str, max_length: int = MAX_DECODED_LENGTH) -> str | None:
    """Safely decode URL percent-encoded text."""
    if len(text) > max_length:
        return None

    try:
        # urllib.parse.unquote handles double encoding and malformed sequences safely
        decoded = urllib.parse.unquote(text)
        if len(decoded) > max_length:
            return None
        return decoded
    except Exception:
        return None


def _url_encoded_density(text: str) -> float:
    """Calculate the density of %XX sequences in text."""
    matches = _URL_ENCODED_RE.findall(text)
    encoded_chars = len(matches) * 3  # Each %XX is 3 chars
    return encoded_chars / len(text) if text else 0.0


def detect_url_candidates(
    text: str,
    min_length_override: int | None = None,
) -> list[EncodingCandidate]:
    """Detect potential URL percent-encoded segments."""
    candidates: list[EncodingCandidate] = []

    min_len = min_length_override if min_length_override is not None else 20
    # Only enforce minimum length if text is longer than the threshold
    # This allows short but clearly encoded strings to be detected
    if len(text) < min_len and min_length_override is not None:
        # Only enforce minimum length if override was explicitly provided
        # For recursive calls, we use min_length_override as a hint, not a hard limit
        pass

    density = _url_encoded_density(text)
    if density < MIN_URL_ENCODED_DENSITY:
        # Check for high-density encoded runs
        matches = list(_URL_ENCODED_RE.finditer(text))
        if len(matches) < 3:
            return candidates

    decoded = decode_url(text)
    if decoded is None or decoded == text:
        return candidates

    confidence = 0.4
    if _is_meaningful_text(decoded):
        confidence = 0.7

    candidates.append(
        EncodingCandidate(
            encoding="url",
            matched_text=text[:MAX_PREVIEW_LENGTH],
            position=0,
            confidence=confidence,
            metadata={
                "density": density,
                "decoded_preview": decoded[:MAX_PREVIEW_LENGTH],
                "decoded_length": len(decoded),
            },
        )
    )

    return candidates


# ============================================================================
# Unified Encoding Detection
# ============================================================================

ENCODING_DETECTORS = [
    ("base64", detect_base64_candidates),
    ("rot13", detect_rot13_candidates),
    ("hex", detect_hex_candidates),
    ("url", detect_url_candidates),
]


def detect_all_encodings(
    text: str,
    min_length_override: int | None = None,
) -> list[EncodingCandidate]:
    """Run all encoding detectors on text."""
    all_candidates: list[EncodingCandidate] = []

    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH]

    for encoding_name, detector in ENCODING_DETECTORS:
        try:
            # Pass min_length_override to detectors that support it
            # Only pass as a suggestion to lower the threshold, not raise it
            if encoding_name in ("base64", "hex", "rot13", "url"):
                candidates = detector(text, min_length_override)
            else:
                candidates = detector(text)
            all_candidates.extend(candidates)
        except Exception:
            # Never let detector errors crash the pipeline
            pass

    # Sort by confidence descending
    all_candidates.sort(key=lambda c: c.confidence, reverse=True)
    return all_candidates


# ============================================================================
# Recursive Decoding with Depth Control
# ============================================================================


def decode_recursive(
    text: str,
    max_depth: int = MAX_DECODE_DEPTH,
    max_attempts: int = MAX_DECODE_ATTEMPTS,
) -> list[DecodeResult]:
    """Recursively decode text through multiple encoding layers.

    Returns a list of successful decodes with their encoding chains.
    """
    results: list[DecodeResult] = []
    seen_outputs: set[str] = set()

    def _decode_recursive(
        current_text: str,
        depth: int,
        encoding_chain: tuple[str, ...],
    ) -> None:
        if depth >= max_depth:
            return
        if len(encoding_chain) >= max_depth:
            return

        # Use shorter minimum lengths for recursive calls to detect nested encodings
        min_len = max(8, MIN_BASE64_LENGTH // (depth + 1))
        candidates = detect_all_encodings(current_text, min_length_override=min_len)
        attempts = 0

        for candidate in candidates:
            if attempts >= MAX_DECODE_ATTEMPTS:
                break

            # Decode using the appropriate decoder
            decoded = None
            if candidate.encoding == "base64":
                decoded = decode_base64(candidate.matched_text, min_length=min_len)
            elif candidate.encoding == "rot13":
                decoded = decode_rot13(candidate.matched_text)
            elif candidate.encoding == "hex":
                decoded = decode_hex(candidate.matched_text)
            elif candidate.encoding == "url":
                decoded = decode_url(candidate.matched_text)

            if decoded is None or decoded in seen_outputs:
                continue

            seen_outputs.add(decoded)
            attempts += 1

            new_chain = (*encoding_chain, candidate.encoding)
            result = DecodeResult(
                encoding=candidate.encoding,
                original=current_text,
                decoded=decoded,
                depth=depth + 1,
                encoding_chain=new_chain,
                confidence=candidate.confidence,
                metadata=candidate.metadata,
            )
            results.append(result)

            # Recurse on decoded content
            _decode_recursive(decoded, depth + 1, new_chain)

    _decode_recursive(text, 0, ())
    return results


def get_best_decode_result(text: str) -> DecodeResult | None:
    """Get the single best decode result (highest confidence)."""
    results = decode_recursive(text)
    if not results:
        return None
    return max(results, key=lambda r: r.confidence)
