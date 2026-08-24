"""Homoglyph / confusable character detection for Q-Guardian.

Provides Unicode confusable mappings and detection utilities for identifying
suspicious character substitutions (e.g., Cyrillic '\u0430' U+0430 for Latin 'a' U+0061)
and suspicious mixed-script text.

The module uses explicit code-point mappings rather than visual similarity
heuristics to ensure deterministic, maintainable detection with minimal
false positives.
"""

from __future__ import annotations

import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# Confusable Mappings
# ---------------------------------------------------------------------------
#
# Structure: { confusable_char: { "code_point": "U+XXXX", "script": "Cyrillic",
#                                  "lookalike": "a", "lookalike_code_point": "U+0061",
#                                  "lookalike_script": "Latin" } }
#
# Only includes characters that are genuine security-relevant confusables
# (commonly used in homograph attacks), not all visually similar characters.

# Cyrillic -> Latin confusables (most common in homograph attacks)
_CYRILLIC_CONFUSABLES: dict[str, dict[str, str]] = {
    # Lowercase
    "\u0430": {
        "code_point": "U+0430",
        "script": "Cyrillic",
        "lookalike": "a",
        "lookalike_code_point": "U+0061",
        "lookalike_script": "Latin",
    },
    "\u0431": {
        "code_point": "U+0431",
        "script": "Cyrillic",
        "lookalike": "b",
        "lookalike_code_point": "U+0062",
        "lookalike_script": "Latin",
    },
    "\u0432": {
        "code_point": "U+0432",
        "script": "Cyrillic",
        "lookalike": "b",
        "lookalike_code_point": "U+0062",
        "lookalike_script": "Latin",
    },
    "\u0433": {
        "code_point": "U+0433",
        "script": "Cyrillic",
        "lookalike": "g",
        "lookalike_code_point": "U+0067",
        "lookalike_script": "Latin",
    },
    "\u0434": {
        "code_point": "U+0434",
        "script": "Cyrillic",
        "lookalike": "d",
        "lookalike_code_point": "U+0064",
        "lookalike_script": "Latin",
    },
    "\u0435": {
        "code_point": "U+0435",
        "script": "Cyrillic",
        "lookalike": "e",
        "lookalike_code_point": "U+0065",
        "lookalike_script": "Latin",
    },
    "\u0436": {
        "code_point": "U+0436",
        "script": "Cyrillic",
        "lookalike": "x",
        "lookalike_code_point": "U+0078",
        "lookalike_script": "Latin",
    },
    "\u0437": {
        "code_point": "U+0437",
        "script": "Cyrillic",
        "lookalike": "z",
        "lookalike_code_point": "U+007A",
        "lookalike_script": "Latin",
    },
    "\u0438": {
        "code_point": "U+0438",
        "script": "Cyrillic",
        "lookalike": "i",
        "lookalike_code_point": "U+0069",
        "lookalike_script": "Latin",
    },
    "\u0439": {
        "code_point": "U+0439",
        "script": "Cyrillic",
        "lookalike": "j",
        "lookalike_code_point": "U+006A",
        "lookalike_script": "Latin",
    },
    "\u043a": {
        "code_point": "U+043A",
        "script": "Cyrillic",
        "lookalike": "k",
        "lookalike_code_point": "U+006B",
        "lookalike_script": "Latin",
    },
    "\u043c": {
        "code_point": "U+043C",
        "script": "Cyrillic",
        "lookalike": "m",
        "lookalike_code_point": "U+006D",
        "lookalike_script": "Latin",
    },
    "\u043e": {
        "code_point": "U+043E",
        "script": "Cyrillic",
        "lookalike": "o",
        "lookalike_code_point": "U+006F",
        "lookalike_script": "Latin",
    },
    "\u043f": {
        "code_point": "U+043F",
        "script": "Cyrillic",
        "lookalike": "p",
        "lookalike_code_point": "U+0070",
        "lookalike_script": "Latin",
    },
    "\u0440": {
        "code_point": "U+0440",
        "script": "Cyrillic",
        "lookalike": "p",
        "lookalike_code_point": "U+0070",
        "lookalike_script": "Latin",
    },
    "\u0441": {
        "code_point": "U+0441",
        "script": "Cyrillic",
        "lookalike": "c",
        "lookalike_code_point": "U+0063",
        "lookalike_script": "Latin",
    },
    "\u0442": {
        "code_point": "U+0442",
        "script": "Cyrillic",
        "lookalike": "t",
        "lookalike_code_point": "U+0074",
        "lookalike_script": "Latin",
    },
    "\u0443": {
        "code_point": "U+0443",
        "script": "Cyrillic",
        "lookalike": "y",
        "lookalike_code_point": "U+0079",
        "lookalike_script": "Latin",
    },
    "\u0445": {
        "code_point": "U+0445",
        "script": "Cyrillic",
        "lookalike": "x",
        "lookalike_code_point": "U+0078",
        "lookalike_script": "Latin",
    },
    "\u0448": {
        "code_point": "U+0448",
        "script": "Cyrillic",
        "lookalike": "w",
        "lookalike_code_point": "U+0077",
        "lookalike_script": "Latin",
    },
    "\u044d": {
        "code_point": "U+044D",
        "script": "Cyrillic",
        "lookalike": "e",
        "lookalike_code_point": "U+0065",
        "lookalike_script": "Latin",
    },
    "\u044e": {
        "code_point": "U+044E",
        "script": "Cyrillic",
        "lookalike": "o",
        "lookalike_code_point": "U+006F",
        "lookalike_script": "Latin",
    },
    # Uppercase
    "\u0410": {
        "code_point": "U+0410",
        "script": "Cyrillic",
        "lookalike": "A",
        "lookalike_code_point": "U+0041",
        "lookalike_script": "Latin",
    },
    "\u0412": {
        "code_point": "U+0412",
        "script": "Cyrillic",
        "lookalike": "B",
        "lookalike_code_point": "U+0042",
        "lookalike_script": "Latin",
    },
    "\u0415": {
        "code_point": "U+0415",
        "script": "Cyrillic",
        "lookalike": "E",
        "lookalike_code_point": "U+0045",
        "lookalike_script": "Latin",
    },
    "\u041a": {
        "code_point": "U+041A",
        "script": "Cyrillic",
        "lookalike": "K",
        "lookalike_code_point": "U+004B",
        "lookalike_script": "Latin",
    },
    "\u041c": {
        "code_point": "U+041C",
        "script": "Cyrillic",
        "lookalike": "M",
        "lookalike_code_point": "U+004D",
        "lookalike_script": "Latin",
    },
    "\u041e": {
        "code_point": "U+041E",
        "script": "Cyrillic",
        "lookalike": "O",
        "lookalike_code_point": "U+004F",
        "lookalike_script": "Latin",
    },
    "\u0420": {
        "code_point": "U+0420",
        "script": "Cyrillic",
        "lookalike": "P",
        "lookalike_code_point": "U+0050",
        "lookalike_script": "Latin",
    },
    "\u0421": {
        "code_point": "U+0421",
        "script": "Cyrillic",
        "lookalike": "C",
        "lookalike_code_point": "U+0043",
        "lookalike_script": "Latin",
    },
    "\u0422": {
        "code_point": "U+0422",
        "script": "Cyrillic",
        "lookalike": "T",
        "lookalike_code_point": "U+0054",
        "lookalike_script": "Latin",
    },
    "\u0425": {
        "code_point": "U+0425",
        "script": "Cyrillic",
        "lookalike": "X",
        "lookalike_code_point": "U+0058",
        "lookalike_script": "Latin",
    },
}

# Greek -> Latin confusables
_GREEK_CONFUSABLES: dict[str, dict[str, str]] = {
    # Lowercase
    "\u03b1": {
        "code_point": "U+03B1",
        "script": "Greek",
        "lookalike": "a",
        "lookalike_code_point": "U+0061",
        "lookalike_script": "Latin",
    },
    "\u03b2": {
        "code_point": "U+03B2",
        "script": "Greek",
        "lookalike": "b",
        "lookalike_code_point": "U+0062",
        "lookalike_script": "Latin",
    },
    "\u03b5": {
        "code_point": "U+03B5",
        "script": "Greek",
        "lookalike": "e",
        "lookalike_code_point": "U+0065",
        "lookalike_script": "Latin",
    },
    "\u03b7": {
        "code_point": "U+03B7",
        "script": "Greek",
        "lookalike": "n",
        "lookalike_code_point": "U+006E",
        "lookalike_script": "Latin",
    },
    "\u03b9": {
        "code_point": "U+03B9",
        "script": "Greek",
        "lookalike": "i",
        "lookalike_code_point": "U+0069",
        "lookalike_script": "Latin",
    },
    "\u03ba": {
        "code_point": "U+03BA",
        "script": "Greek",
        "lookalike": "k",
        "lookalike_code_point": "U+006B",
        "lookalike_script": "Latin",
    },
    "\u03bc": {
        "code_point": "U+03BC",
        "script": "Greek",
        "lookalike": "m",
        "lookalike_code_point": "U+006D",
        "lookalike_script": "Latin",
    },
    "\u03bf": {
        "code_point": "U+03BF",
        "script": "Greek",
        "lookalike": "o",
        "lookalike_code_point": "U+006F",
        "lookalike_script": "Latin",
    },
    "\u03c1": {
        "code_point": "U+03C1",
        "script": "Greek",
        "lookalike": "p",
        "lookalike_code_point": "U+0070",
        "lookalike_script": "Latin",
    },
    "\u03c3": {
        "code_point": "U+03C3",
        "script": "Greek",
        "lookalike": "c",
        "lookalike_code_point": "U+0063",
        "lookalike_script": "Latin",
    },
    "\u03c4": {
        "code_point": "U+03C4",
        "script": "Greek",
        "lookalike": "t",
        "lookalike_code_point": "U+0074",
        "lookalike_script": "Latin",
    },
    "\u03c5": {
        "code_point": "U+03C5",
        "script": "Greek",
        "lookalike": "y",
        "lookalike_code_point": "U+0079",
        "lookalike_script": "Latin",
    },
    "\u03c7": {
        "code_point": "U+03C7",
        "script": "Greek",
        "lookalike": "x",
        "lookalike_code_point": "U+0078",
        "lookalike_script": "Latin",
    },
    "\u03c9": {
        "code_point": "U+03C9",
        "script": "Greek",
        "lookalike": "w",
        "lookalike_code_point": "U+0077",
        "lookalike_script": "Latin",
    },
    # Uppercase
    "\u0391": {
        "code_point": "U+0391",
        "script": "Greek",
        "lookalike": "A",
        "lookalike_code_point": "U+0041",
        "lookalike_script": "Latin",
    },
    "\u0392": {
        "code_point": "U+0392",
        "script": "Greek",
        "lookalike": "B",
        "lookalike_code_point": "U+0042",
        "lookalike_script": "Latin",
    },
    "\u0395": {
        "code_point": "U+0395",
        "script": "Greek",
        "lookalike": "E",
        "lookalike_code_point": "U+0045",
        "lookalike_script": "Latin",
    },
    "\u0397": {
        "code_point": "U+0397",
        "script": "Greek",
        "lookalike": "H",
        "lookalike_code_point": "U+0048",
        "lookalike_script": "Latin",
    },
    "\u0399": {
        "code_point": "U+0399",
        "script": "Greek",
        "lookalike": "I",
        "lookalike_code_point": "U+0049",
        "lookalike_script": "Latin",
    },
    "\u039a": {
        "code_point": "U+039A",
        "script": "Greek",
        "lookalike": "K",
        "lookalike_code_point": "U+004B",
        "lookalike_script": "Latin",
    },
    "\u039c": {
        "code_point": "U+039C",
        "script": "Greek",
        "lookalike": "M",
        "lookalike_code_point": "U+004D",
        "lookalike_script": "Latin",
    },
    "\u039f": {
        "code_point": "U+039F",
        "script": "Greek",
        "lookalike": "O",
        "lookalike_code_point": "U+004F",
        "lookalike_script": "Latin",
    },
    "\u03a1": {
        "code_point": "U+03A1",
        "script": "Greek",
        "lookalike": "P",
        "lookalike_code_point": "U+0050",
        "lookalike_script": "Latin",
    },
    "\u03a4": {
        "code_point": "U+03A4",
        "script": "Greek",
        "lookalike": "T",
        "lookalike_code_point": "U+0054",
        "lookalike_script": "Latin",
    },
    "\u03a7": {
        "code_point": "U+03A7",
        "script": "Greek",
        "lookalike": "X",
        "lookalike_code_point": "U+0058",
        "lookalike_script": "Latin",
    },
    "\u03a9": {
        "code_point": "U+03A9",
        "script": "Greek",
        "lookalike": "O",
        "lookalike_code_point": "U+004F",
        "lookalike_script": "Latin",
    },
}

# Combined confusable map for fast lookup
_CONFUSABLE_MAP: dict[str, dict[str, str]] = {}
_CONFUSABLE_MAP.update(_CYRILLIC_CONFUSABLES)
_CONFUSABLE_MAP.update(_GREEK_CONFUSABLES)

# Script detection ranges
_CYRILLIC_RANGE = (0x0400, 0x04FF)
_GREEK_RANGE = (0x0370, 0x03FF)
_LATIN_BASIC_RANGE = (0x0000, 0x007F)
_LATIN_EXTENDED_A_RANGE = (0x0100, 0x017F)
_LATIN_EXTENDED_B_RANGE = (0x0180, 0x024F)


def _get_script(char: str) -> str | None:
    """Determine the script of a character."""
    code = ord(char)
    if _CYRILLIC_RANGE[0] <= code <= _CYRILLIC_RANGE[1]:
        return "Cyrillic"
    if _GREEK_RANGE[0] <= code <= _GREEK_RANGE[1]:
        return "Greek"
    if _LATIN_BASIC_RANGE[0] <= code <= _LATIN_BASIC_RANGE[1]:
        return "Latin"
    if _LATIN_EXTENDED_A_RANGE[0] <= code <= _LATIN_EXTENDED_A_RANGE[1]:
        return "Latin"
    if _LATIN_EXTENDED_B_RANGE[0] <= code <= _LATIN_EXTENDED_B_RANGE[1]:
        return "Latin"
    # Check Unicode script property for other cases
    try:
        script = unicodedata.name(char).split()[0]
        if script in ("CYRILLIC", "GREEK", "LATIN"):
            return script.capitalize()
    except (ValueError, IndexError):
        pass
    return None


def is_ascii(text: str) -> bool:
    """Fast check if text contains only ASCII characters."""
    return all(ord(c) < 128 for c in text)


def detect_confusables(text: str) -> list[dict[str, Any]]:
    """Detect known confusable characters in text.

    Args:
        text: Input text to analyze.

    Returns:
        List of detection results, each containing:
        - char: The confusable character
        - position: Character index in the input
        - code_point: Unicode code point of the confusable
        - script: Script of the confusable
        - lookalike: The Latin character it resembles
        - lookalike_code_point: Code point of the lookalike
        - lookalike_script: Script of the lookalike
    """
    results = []
    for i, char in enumerate(text):
        if char in _CONFUSABLE_MAP:
            info = _CONFUSABLE_MAP[char]
            results.append(
                {
                    "char": char,
                    "position": i,
                    "code_point": info["code_point"],
                    "script": info["script"],
                    "lookalike": info["lookalike"],
                    "lookalike_code_point": info["lookalike_code_point"],
                    "lookalike_script": info["lookalike_script"],
                }
            )
    return results


def detect_mixed_script(text: str, min_confusable_ratio: float = 0.1) -> list[dict[str, Any]]:
    """Detect suspicious mixed-script text.

    Focuses on cases where a confusable character from one script appears
    in predominantly Latin text, or where multiple scripts are mixed in
    a suspicious way (e.g., within a single word/token).

    Args:
        text: Input text to analyze.
        min_confusable_ratio: Minimum ratio of confusable chars to total
                              non-ASCII chars to flag as suspicious.

    Returns:
        List of suspicious mixed-script segments, each containing:
        - segment: The suspicious text segment
        - start: Start position
        - end: End position
        - scripts: Set of scripts detected
        - confusable_count: Number of confusable characters
        - dominant_script: The dominant script in the segment
    """
    if not text or is_ascii(text):
        return []

    results = []
    words = text.split()

    for word in words:
        if not word or is_ascii(word):
            continue

        scripts_in_word = set()
        confusable_chars = []

        for i, char in enumerate(word):
            script = _get_script(char)
            if script:
                scripts_in_word.add(script)

            if char in _CONFUSABLE_MAP:
                confusable_chars.append((i, char, _CONFUSABLE_MAP[char]["script"]))

        # Check for suspicious mixed-script patterns
        if len(scripts_in_word) >= 2:
            latin_present = "Latin" in scripts_in_word
            cyrillic_present = "Cyrillic" in scripts_in_word
            greek_present = "Greek" in scripts_in_word

            # Suspicious combinations: Latin + Cyrillic or Latin + Greek
            # with at least one confusable character
            if (latin_present and (cyrillic_present or greek_present)) and confusable_chars:
                results.append(
                    {
                        "segment": word,
                        "scripts": list(scripts_in_word),
                        "confusable_count": len(confusable_chars),
                        "confusable_chars": [
                            {"char": c, "script": s} for _, c, s in confusable_chars
                        ],
                    }
                )

    return results


def _is_suspicious_confusable(text: str, confusable: dict[str, Any]) -> bool:
    """Determine if a confusable character is in a suspicious context.

    A confusable is suspicious if:
    - It appears in a word that also contains Latin characters
    - It appears adjacent to Latin text (in same or adjacent word)
    - The overall text is predominantly Latin

    Not suspicious if:
    - The entire text is in a single non-Latin script (legitimate foreign text)
    """
    # Check if the text has Latin characters
    has_latin = any(_get_script(c) == "Latin" for c in text if c.isalpha())
    if not has_latin:
        return False  # Pure non-Latin text is not suspicious

    # Check if the confusable's word contains Latin, or is adjacent to Latin words
    words = text.split()
    for i, word in enumerate(words):
        if confusable["char"] in word:
            # Check if this word has Latin
            word_has_latin = any(_get_script(c) == "Latin" for c in word if c.isalpha())
            if word_has_latin:
                return True

            # Check adjacent words for Latin
            if i > 0:
                prev_word = words[i - 1]
                prev_has_latin = any(_get_script(c) == "Latin" for c in prev_word if c.isalpha())
                if prev_has_latin:
                    return True
            if i < len(words) - 1:
                next_word = words[i + 1]
                next_has_latin = any(_get_script(c) == "Latin" for c in next_word if c.isalpha())
                if next_has_latin:
                    return True

            # Check if word is mixed script (Latin + other)
            scripts_in_word = set()
            for c in word:
                if c.isalpha():
                    script = _get_script(c)
                    if script:
                        scripts_in_word.add(script)
            if "Latin" in scripts_in_word and len(scripts_in_word) > 1:
                return True

    return False


def analyze_homoglyphs(text: str) -> dict[str, Any]:
    """Full homoglyph analysis of text.

    Combines confusable detection and mixed-script detection.
    Only flags confusable characters that appear in suspicious contexts
    (mixed with Latin script).

    Args:
        text: Input text to analyze.

    Returns:
        Dictionary with:
        - confusables: List of suspicious confusable character detections
        - mixed_script: List of suspicious mixed-script segments
        - has_confusables: Boolean flag (only for suspicious confusables)
        - has_mixed_script: Boolean flag
    """
    all_confusables = detect_confusables(text)
    mixed_script = detect_mixed_script(text)

    # Filter confusables to only include suspicious ones
    suspicious_confusables = [c for c in all_confusables if _is_suspicious_confusable(text, c)]

    return {
        "confusables": suspicious_confusables,
        "mixed_script": mixed_script,
        "has_confusables": len(suspicious_confusables) > 0,
        "has_mixed_script": len(mixed_script) > 0,
    }


def get_confusable_count(text: str) -> int:
    """Fast count of confusable characters in text."""
    return sum(1 for c in text if c in _CONFUSABLE_MAP)


def is_likely_homograph_attack(text: str, threshold: int = 1) -> bool:
    """Quick heuristic check for likely homograph attack.

    Args:
        text: Input text.
        threshold: Minimum number of confusable chars to flag.

    Returns:
        True if text likely contains homograph attack.
    """
    if is_ascii(text):
        return False
    return get_confusable_count(text) >= threshold
