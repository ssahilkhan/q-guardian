"""Tests for the classical-model feature-space contract (F-09 fix).

Guards the canonical 12-dim extractor and proves that a model trained on a
mismatched vector width fails loudly instead of silently degrading.
"""

from __future__ import annotations

import numpy as np
import pytest

from q_guardian.ml.base import CORE_FEATURE_NAMES, extract_core_features
from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.security.models import PromptFeatures


def _features() -> PromptFeatures:
    return PromptFeatures(
        length=120,
        word_count=24,
        line_count=2,
        token_estimate=30,
        special_char_count=7,
        code_block_count=0,
        url_count=1,
        repeated_patterns=["abc"],
        entropy=3.4,
        suspicious_keywords=["ignore previous"],
        uppercase_ratio=0.1,
        digit_ratio=0.05,
    )


class TestCanonicalExtractor:
    def test_vector_width_matches_declared_names(self) -> None:
        assert len(extract_core_features(_features())) == len(CORE_FEATURE_NAMES) == 12

    def test_values_follow_documented_order(self) -> None:
        features = _features()
        vector = extract_core_features(features)
        assert vector[0] == 120  # length
        assert vector[10] == 1.0  # suspicious_keyword_count
        assert vector[11] == 1.0  # repeated_pattern_count

    def test_model_extractors_use_canonical_mapping(self) -> None:
        detector = IsolationForestDetector()
        assert detector._extract_vector(_features()) == extract_core_features(_features())


class TestDimensionGuard:
    async def test_trained_model_rejects_mismatched_vectors_loudly(self) -> None:
        detector = IsolationForestDetector()
        rng = np.random.default_rng(42)
        # Train on deliberately wrong-width (5-dim) vectors.
        detector.train(rng.normal(size=(60, 5)).tolist())
        with pytest.raises(ValueError, match="feature dimension mismatch"):
            await detector.detect("hello", _features())

    async def test_correctly_trained_model_detects_without_error(self) -> None:
        detector = IsolationForestDetector()
        rng = np.random.default_rng(42)
        benign = [extract_core_features(_features()) for _ in range(40)]
        noise = rng.normal(loc=5.0, scale=50.0, size=(40, 12)).tolist()
        detector.train(benign + noise)
        result = await detector.detect("hello world", _features())  # must not raise
        assert result.detector_name == "isolation-forest"
