"""Unit tests for embedding explainability: EmbeddingMeta and EmbeddingTrace."""

from __future__ import annotations

from q_guardian.embeddings.explain import EmbeddingMeta, EmbeddingTrace


class TestEmbeddingMeta:
    def test_required_fields(self):
        meta = EmbeddingMeta(provider="hash-ngram", model="qguardian/hash-ngram-v1", dimension=16)
        assert meta.latency_ms == 0.0
        assert meta.mode == ""
        assert meta.cached is False
        assert meta.fallback is False

    def test_is_frozen(self):
        import pytest

        meta = EmbeddingMeta(provider="p", model="m", dimension=1)
        with pytest.raises(AttributeError, match="cannot assign"):
            meta.cached = True

    def test_to_dict(self):
        meta = EmbeddingMeta(provider="p", model="m", dimension=3, latency_ms=1.5, mode="hybrid")
        data = meta.to_dict()
        assert data == {
            "provider": "p",
            "model": "m",
            "dimension": 3,
            "latency_ms": 1.5,
            "mode": "hybrid",
            "cached": False,
            "fallback": False,
        }

    def test_from_dict_roundtrip(self):
        meta = EmbeddingMeta(
            provider="p",
            model="m",
            dimension=3,
            latency_ms=2.0,
            mode="embedding",
            cached=True,
            fallback=True,
        )
        restored = EmbeddingMeta.from_dict(meta.to_dict())
        assert restored == meta

    def test_from_dict_defaults(self):
        meta = EmbeddingMeta.from_dict({"provider": "p", "model": "m", "dimension": 4})
        assert meta.latency_ms == 0.0
        assert meta.mode == ""
        assert meta.cached is False

    def test_is_cache_hit(self):
        assert EmbeddingMeta(provider="p", model="m", dimension=1, cached=True).is_cache_hit is True
        assert EmbeddingMeta(provider="p", model="m", dimension=1).is_cache_hit is False

    def test_from_dict_coerces_types(self):
        meta = EmbeddingMeta.from_dict(
            {"provider": "p", "model": "m", "dimension": "8", "latency_ms": "1.5", "cached": 1}
        )
        assert meta.dimension == 8
        assert meta.latency_ms == 1.5
        assert meta.cached is True


class TestEmbeddingTrace:
    def _meta(self, provider="hash-ngram", latency=1.0, cached=False):
        return EmbeddingMeta(
            provider=provider,
            model="qguardian/hash-ngram-v1",
            dimension=16,
            latency_ms=latency,
            cached=cached,
        )

    def test_empty_trace(self):
        trace = EmbeddingTrace()
        assert trace.count() == 0
        assert trace.providers() == []
        assert trace.models() == []
        assert trace.latency_stats() == {"count": 0, "mean_ms": 0.0, "max_ms": 0.0, "total_ms": 0.0}

    def test_record_and_count(self):
        trace = EmbeddingTrace()
        trace.record(self._meta())
        trace.record(self._meta())
        assert trace.count() == 2

    def test_records_returns_copy(self):
        trace = EmbeddingTrace()
        trace.record(self._meta())
        records = trace.records()
        records.clear()
        assert trace.count() == 1

    def test_providers_unique_sorted(self):
        trace = EmbeddingTrace()
        trace.record(self._meta(provider="b"))
        trace.record(self._meta(provider="a"))
        trace.record(self._meta(provider="b"))
        assert trace.providers() == ["a", "b"]

    def test_models_unique_sorted(self):
        trace = EmbeddingTrace()
        trace.record(self._meta())
        assert trace.models() == ["qguardian/hash-ngram-v1"]

    def test_latency_stats_ignore_cached(self):
        trace = EmbeddingTrace()
        trace.record(self._meta(latency=2.0, cached=False))
        trace.record(self._meta(latency=4.0, cached=False))
        trace.record(self._meta(latency=999.0, cached=True))
        stats = trace.latency_stats()
        assert stats["count"] == 2
        assert stats["mean_ms"] == 3.0
        assert stats["max_ms"] == 4.0
        assert stats["total_ms"] == 6.0

    def test_latency_stats_p95(self):
        trace = EmbeddingTrace()
        for value in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
            trace.record(self._meta(latency=value))
        assert trace.latency_stats()["p95_ms"] == 9.0

    def test_to_dict(self):
        trace = EmbeddingTrace()
        trace.record(self._meta(latency=1.0))
        data = trace.to_dict()
        assert data["count"] == 1
        assert data["providers"] == ["hash-ngram"]
        assert "latency" in data

    def test_clear(self):
        trace = EmbeddingTrace()
        trace.record(self._meta())
        trace.clear()
        assert trace.count() == 0
