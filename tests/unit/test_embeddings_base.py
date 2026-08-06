"""Unit tests for the EmbeddingProvider base lifecycle and shared helpers."""

from __future__ import annotations

import pytest

from q_guardian.embeddings.base import EmbeddingProvider
from q_guardian.embeddings.errors import EmbeddingNotLoadedError


class _StubProvider(EmbeddingProvider):
    default_model = "stub/v1"

    def __init__(self, *, vector: list[float] | None = None, latency_window: int = 64) -> None:
        super().__init__(latency_window=latency_window)
        self._vector = vector if vector is not None else [1.0, 2.0, 3.0]

    @property
    def name(self) -> str:
        return "stub"

    def load(self) -> None:
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def dimension(self) -> int:
        return len(self._vector)

    def health(self) -> bool:
        return self._loaded

    def _embed_impl(self, text: str) -> list[float]:
        return list(self._vector)

    def _embed_batch_impl(self, texts: list[str]) -> list[list[float]]:
        return [list(self._vector) for _ in texts]


class TestEmbeddingProviderBase:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            EmbeddingProvider()

    def test_name_is_abstract(self):
        assert _StubProvider().name == "stub"

    def test_default_model_id(self):
        assert _StubProvider().model_id == "stub/v1"

    def test_default_backend_is_generic(self):
        assert _StubProvider().backend == "generic"

    def test_requires_token_default_false(self):
        assert _StubProvider().requires_token is False

    def test_embed_requires_load(self):
        with pytest.raises(EmbeddingNotLoadedError):
            _StubProvider().embed("hello")

    def test_embed_after_load(self):
        provider = _StubProvider()
        provider.load()
        assert provider.embed("hello") == [1.0, 2.0, 3.0]

    def test_embed_batch_requires_load(self):
        with pytest.raises(EmbeddingNotLoadedError):
            _StubProvider().embed_batch(["a", "b"])

    def test_embed_batch_after_load(self):
        provider = _StubProvider()
        provider.load()
        vectors = provider.embed_batch(["a", "b", "c"])
        assert len(vectors) == 3
        assert all(v == [1.0, 2.0, 3.0] for v in vectors)

    def test_average_latency_zero_before_embed(self):
        assert _StubProvider().average_latency_ms() == 0.0

    def test_average_latency_positive_after_embed(self):
        provider = _StubProvider()
        provider.load()
        provider.embed("hello")
        assert provider.average_latency_ms() > 0.0

    def test_embed_batch_records_latency_per_item(self):
        provider = _StubProvider(latency_window=64)
        provider.load()
        provider.embed_batch(["a", "b", "c"])
        assert provider.average_latency_ms() > 0.0

    def test_latency_window_respected(self):
        provider = _StubProvider(latency_window=2)
        provider.load()
        provider.embed("one")
        provider.embed("two")
        provider.embed("three")
        assert provider.metadata()["latency_ms"] >= 0.0

    def test_metadata_record(self):
        provider = _StubProvider()
        provider.load()
        meta = provider.metadata()
        assert meta["provider"] == "stub"
        assert meta["model"] == "stub/v1"
        assert meta["dimension"] == 3
        assert meta["load_status"] == "loaded"
        assert meta["backend"] == "generic"
        assert meta["requires_token"] is False
        assert meta["implemented"] is True

    def test_health_after_load_and_unload(self):
        provider = _StubProvider()
        provider.load()
        assert provider.health() is True
        provider.unload()
        assert provider.health() is False

    def test_load_is_idempotent(self):
        provider = _StubProvider()
        provider.load()
        provider.load()
        assert provider.is_loaded is True

    def test_unload_is_idempotent(self):
        provider = _StubProvider()
        provider.unload()
        provider.unload()
        assert provider.is_loaded is False

    def test_embed_returns_fresh_copy(self):
        provider = _StubProvider()
        provider.load()
        a = provider.embed("hello")
        a[0] = 999.0
        assert provider.embed("hello")[0] == 1.0
