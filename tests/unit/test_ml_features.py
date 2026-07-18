"""Tests for MLFeatureProvider."""

from __future__ import annotations

import pytest

from q_guardian.ml.config import MLConfig
from q_guardian.ml.feature_pipeline import MLFeatureProvider
from q_guardian.security.models import PromptFeatures


def _make_features(**overrides) -> PromptFeatures:
    defaults = dict(
        length=100,
        word_count=20,
        line_count=3,
        token_estimate=25,
        entropy=3.5,
        uppercase_ratio=0.1,
        digit_ratio=0.05,
        special_char_count=5,
        code_block_count=1,
        url_count=0,
        markdown_usage=True,
        has_unicode_escaped=False,
        has_html_tags=False,
        suspicious_keywords=["ignore"],
        repeated_patterns=[],
    )
    defaults.update(overrides)
    return PromptFeatures(**defaults)


class TestMLFeatureProvider:
    def setup_method(self) -> None:
        self.provider = MLFeatureProvider()

    @pytest.mark.asyncio
    async def test_extract_features_basic(self) -> None:
        features = _make_features()
        result = await self.provider.extract_features("Hello world test prompt", features)
        assert "feature_vector" in result
        assert "feature_names" in result
        assert len(result["feature_vector"]) == len(result["feature_names"])

    @pytest.mark.asyncio
    async def test_feature_names_count(self) -> None:
        names = self.provider.feature_names
        assert len(names) > 20  # Should have many features

    @pytest.mark.asyncio
    async def test_keyword_features(self) -> None:
        features = _make_features(suspicious_keywords=["ignore", "override"])
        result = await self.provider.extract_features("test prompt", features)
        assert result["suspicious_keyword_count"] == 2

    @pytest.mark.asyncio
    async def test_statistical_features(self) -> None:
        features = _make_features(length=500, word_count=100, entropy=4.5)
        result = await self.provider.extract_features("test", features)
        assert result["length"] == 500
        assert result["word_count"] == 100
        assert result["entropy"] == 4.5

    @pytest.mark.asyncio
    async def test_pattern_features(self) -> None:
        features = _make_features(code_block_count=3, url_count=2, markdown_usage=True)
        result = await self.provider.extract_features("test", features)
        assert result["code_block_count"] == 3
        assert result["url_count"] == 2
        assert result["markdown_usage"] == 1

    @pytest.mark.asyncio
    async def test_empty_prompt(self) -> None:
        features = _make_features(length=0, word_count=0, entropy=0.0)
        result = await self.provider.extract_features("", features)
        assert result["feature_vector"] is not None
        assert len(result["feature_vector"]) == len(self.provider.feature_names)

    def test_extract_vector_sync(self) -> None:
        features = _make_features()
        fv = self.provider.extract_vector("Hello world", features)
        assert len(fv.features) == len(self.provider.feature_names)
        assert len(fv.feature_names) == len(self.provider.feature_names)

    @pytest.mark.asyncio
    async def test_char_distribution(self) -> None:
        features = _make_features()
        result = await self.provider.extract_features("Hello World! 123", features)
        assert "unique_char_ratio" in result
        assert "avg_word_length" in result
        assert "punctuation_ratio" in result
        assert "whitespace_ratio" in result

    @pytest.mark.asyncio
    async def test_name(self) -> None:
        assert self.provider.name == "ml-feature-provider"
