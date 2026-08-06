"""Unit tests for the embedding exception hierarchy."""

from __future__ import annotations

import pytest

from q_guardian.embeddings.errors import (
    EmbeddingError,
    EmbeddingNotAvailableError,
    EmbeddingNotLoadedError,
    EmbeddingProviderError,
)


class TestEmbeddingErrors:
    def test_base_error_derives_from_exception(self):
        assert issubclass(EmbeddingError, Exception)

    def test_not_loaded_derives_from_base(self):
        assert issubclass(EmbeddingNotLoadedError, EmbeddingError)

    def test_not_available_derives_from_base(self):
        assert issubclass(EmbeddingNotAvailableError, EmbeddingError)

    def test_provider_error_derives_from_base(self):
        assert issubclass(EmbeddingProviderError, EmbeddingError)

    def test_caught_as_base_error(self):
        with pytest.raises(EmbeddingError):
            raise EmbeddingNotLoadedError("boom")

    def test_message_preserved(self):
        with pytest.raises(EmbeddingNotAvailableError, match="missing library"):
            raise EmbeddingNotAvailableError("missing library")

    def test_all_exported_from_package(self):
        from q_guardian.embeddings import (  # noqa: F401
            EmbeddingError,
            EmbeddingNotAvailableError,
            EmbeddingNotLoadedError,
            EmbeddingProviderError,
        )

        assert EmbeddingError is not None
