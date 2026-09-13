"""Tests for the Hugging Face dataset loader with authentication."""

from __future__ import annotations

import pytest

from q_guardian.ml.datasets.huggingface_loader import HuggingFaceLoader


class TestHuggingFaceLoaderAuth:
    def test_init_without_token(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        loader = HuggingFaceLoader()
        assert loader.token is None
        assert loader.has_token is False

    def test_init_with_explicit_token(self):
        loader = HuggingFaceLoader(token="hf_explicit_token")
        assert loader.token == "hf_explicit_token"
        assert loader.has_token is True

    def test_init_with_env_token(self, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_env_token")
        loader = HuggingFaceLoader()
        assert loader.token == "hf_env_token"
        assert loader.has_token is True

    def test_explicit_token_overrides_env(self, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_env_token")
        loader = HuggingFaceLoader(token="hf_explicit_token")
        assert loader.token == "hf_explicit_token"

    @pytest.mark.asyncio
    async def test_load_unavailable_without_datasets_lib(self):
        loader = HuggingFaceLoader()
        if not loader.is_available:
            with pytest.raises(ImportError, match="Hugging Face.*datasets.*library is not installed"):
                await loader.load("some-dataset")

    @pytest.mark.asyncio
    async def test_load_gated_error_message(self):
        loader = HuggingFaceLoader()
        if loader.is_available:
            # Mock the datasets library to raise a gated error
            import datasets

            original_load_dataset = datasets.load_dataset

            def mock_load_dataset(*args, **kwargs):
                raise Exception("401 Client Error: Unauthorized for url - gated dataset")

            datasets.load_dataset = mock_load_dataset

            try:
                with pytest.raises(ValueError, match="gated"):
                    await loader.load("org/gated-dataset")
            finally:
                datasets.load_dataset = original_load_dataset

    @pytest.mark.asyncio
    async def test_check_access_public(self):
        loader = HuggingFaceLoader()
        if loader.is_available:
            result = await loader.check_access("deepset/prompt-injections")
            # Result should indicate accessible (may need token for some)
            assert "accessible" in result
            assert "requires_auth" in result
            assert "error" in result

    @pytest.mark.asyncio
    async def test_check_access_with_token(self):
        loader = HuggingFaceLoader(token="hf_test_token")
        if loader.is_available:
            result = await loader.check_access("org/some-dataset")
            assert "accessible" in result
            assert "requires_auth" in result
            assert "error" in result