"""Feature extraction pipeline for ML models.

Independent of any specific ML model. Produces numeric feature vectors
that can be consumed by any model implementing BaseThreatModel, and
are reusable by Module 6 (Quantum Analysis).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import structlog

from q_guardian.ml.config import MLConfig
from q_guardian.ml.data import FeatureVector
from q_guardian.security.extensibility import FeatureProvider
from q_guardian.security.models import PromptFeatures

logger = structlog.get_logger("ml.feature_pipeline")

_KEYWORDS = [
    "ignore", "forget", "override", "bypass", "jailbreak", "system",
    "prompt", "injection", "reveal", "secret", "password", "admin",
    "root", "sudo", "execute", "inject", "malicious", "exploit",
    "hack", "attack", "payload", "exfiltrate", "dump", "extract",
]


class MLFeatureProvider(FeatureProvider):
    """Extracts numeric feature vectors for ML models.

    Produces a fixed-size feature vector from prompt text and
    base PromptFeatures. The output is model-agnostic and
    reusable by classical ML and quantum models.

    Features include:
    - Statistical features (length, entropy, ratios)
    - Keyword features (suspicious keyword counts)
    - Pattern features (code blocks, URLs, encoding indicators)
    - Character distribution features (n-gram diversity)
    """

    def __init__(self, config: MLConfig | None = None) -> None:
        self._config = config or MLConfig()
        self._feature_names: list[str] = []

    @property
    def name(self) -> str:
        return "ml-feature-provider"

    @property
    def feature_names(self) -> list[str]:
        """Return the ordered list of feature names."""
        if not self._feature_names:
            self._feature_names = self._compute_feature_names()
        return list(self._feature_names)

    async def extract_features(
        self, prompt: str, base_features: PromptFeatures
    ) -> dict[str, Any]:
        """Extract additional ML features.

        Args:
            prompt: The normalized prompt text.
            base_features: Features from PromptFeatureExtractor.

        Returns:
            Dictionary of additional features including 'feature_vector'.
        """
        features: dict[str, Any] = {}

        # Statistical features
        features["length"] = base_features.length
        features["word_count"] = base_features.word_count
        features["line_count"] = base_features.line_count
        features["token_estimate"] = base_features.token_estimate
        features["entropy"] = base_features.entropy
        features["uppercase_ratio"] = base_features.uppercase_ratio
        features["digit_ratio"] = base_features.digit_ratio
        features["special_char_count"] = base_features.special_char_count

        # Keyword features
        features["suspicious_keyword_count"] = len(base_features.suspicious_keywords)
        keyword_flags = self._keyword_flags(prompt)
        features.update(keyword_flags)

        # Pattern features
        features["code_block_count"] = base_features.code_block_count
        features["url_count"] = base_features.url_count
        features["markdown_usage"] = int(base_features.markdown_usage)
        features["has_unicode_escaped"] = int(base_features.has_unicode_escaped)
        features["has_html_tags"] = int(base_features.has_html_tags)
        features["repeated_pattern_count"] = len(base_features.repeated_patterns)

        # Character distribution
        char_dist = self._char_distribution(prompt)
        features.update(char_dist)

        # Build numeric vector
        vector = self._build_vector(features)
        features["feature_vector"] = vector
        features["feature_names"] = self.feature_names

        return features

    def extract_vector(
        self, prompt: str, base_features: PromptFeatures
    ) -> FeatureVector:
        """Synchronously extract a FeatureVector (for training pipelines).

        Args:
            prompt: The normalized prompt text.
            base_features: Features from PromptFeatureExtractor.

        Returns:
            FeatureVector with numeric features.
        """
        features: dict[str, Any] = {}
        features["length"] = base_features.length
        features["word_count"] = base_features.word_count
        features["line_count"] = base_features.line_count
        features["token_estimate"] = base_features.token_estimate
        features["entropy"] = base_features.entropy
        features["uppercase_ratio"] = base_features.uppercase_ratio
        features["digit_ratio"] = base_features.digit_ratio
        features["special_char_count"] = base_features.special_char_count
        features["suspicious_keyword_count"] = len(base_features.suspicious_keywords)
        keyword_flags = self._keyword_flags(prompt)
        features.update(keyword_flags)
        features["code_block_count"] = base_features.code_block_count
        features["url_count"] = base_features.url_count
        features["markdown_usage"] = int(base_features.markdown_usage)
        features["has_unicode_escaped"] = int(base_features.has_unicode_escaped)
        features["has_html_tags"] = int(base_features.has_html_tags)
        features["repeated_pattern_count"] = len(base_features.repeated_patterns)
        char_dist = self._char_distribution(prompt)
        features.update(char_dist)

        vector = self._build_vector(features)
        return FeatureVector(
            features=vector,
            feature_names=self.feature_names,
        )

    def _keyword_flags(self, prompt: str) -> dict[str, int]:
        """Count occurrences of each suspicious keyword."""
        lower = prompt.lower()
        return {f"kw_{kw}": lower.count(kw) for kw in _KEYWORDS}

    def _char_distribution(self, prompt: str) -> dict[str, float]:
        """Compute character distribution features."""
        if not prompt:
            return {
                "unique_char_ratio": 0.0,
                "avg_word_length": 0.0,
                "punctuation_ratio": 0.0,
                "whitespace_ratio": 0.0,
            }

        chars = list(prompt)
        unique_chars = len(set(chars))
        total = len(chars)

        words = prompt.split()
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)

        punct_count = sum(1 for c in chars if not c.isalnum() and not c.isspace())
        space_count = sum(1 for c in chars if c.isspace())

        return {
            "unique_char_ratio": unique_chars / total,
            "avg_word_length": avg_word_len,
            "punctuation_ratio": punct_count / total,
            "whitespace_ratio": space_count / total,
        }

    def _build_vector(self, features: dict[str, Any]) -> list[float]:
        """Build an ordered numeric vector from the feature dict."""
        vector: list[float] = []
        for name in self.feature_names:
            val = features.get(name, 0.0)
            if isinstance(val, bool):
                vector.append(1.0 if val else 0.0)
            elif isinstance(val, (int, float)):
                vector.append(float(val))
            else:
                vector.append(0.0)
        return vector

    def _compute_feature_names(self) -> list[str]:
        """Compute the ordered list of feature names."""
        names: list[str] = [
            "length", "word_count", "line_count", "token_estimate",
            "entropy", "uppercase_ratio", "digit_ratio", "special_char_count",
            "suspicious_keyword_count",
        ]
        names.extend(f"kw_{kw}" for kw in _KEYWORDS)
        names.extend([
            "code_block_count", "url_count", "markdown_usage",
            "has_unicode_escaped", "has_html_tags", "repeated_pattern_count",
            "unique_char_ratio", "avg_word_length", "punctuation_ratio",
            "whitespace_ratio",
        ])
        return names
