"""Unit tests for EmbeddingManager: registration, caching, batching, fallback."""

from __future__ import annotations

import pytest

from q_guardian.embeddings.errors import EmbeddingError, EmbeddingNotAvailableError
from q_guardian.embeddings.manager import EmbeddingManager, build_manager
from q_guardian.embeddings.providers.hasher import HashEmbeddingProvider


class _ExplodingProvider(HashEmbeddingProvider):
    """Hash provider that always fails once loaded."""

    @property
    def name(self) -> str:
        return "exploding"

    def _embed_impl(self, text: str) -> list[float]:
        raise EmbeddingNotAvailableError(f"boom: {text}")

    def _embed_batch_impl(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingNotAvailableError("boom batch")


class _NamedHashProvider(HashEmbeddingProvider):
    def __init__(self, name: str, dimension: int = 8) -> None:
        super().__init__(dimension=dimension)
        self._name = name

    @property
    def name(self) -> str:
        return self._name


class TestEmbeddingManagerRegistration:
    def test_register_returns_id(self):
        manager = EmbeddingManager()
        pid = manager.register(HashEmbeddingProvider())
        assert pid == "hash-ngram"

    def test_first_registered_becomes_default(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider())
        assert manager.default_provider_id == "hash-ngram"

    def test_duplicate_register_raises(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider())
        with pytest.raises(EmbeddingError, match="already registered"):
            manager.register(HashEmbeddingProvider())

    def test_register_with_alias(self):
        manager = EmbeddingManager()
        pid = manager.register(HashEmbeddingProvider(), provider_id="alias")
        assert pid == "alias"
        assert manager.provider("alias") is not None

    def test_register_default_flag(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(), provider_id="a")
        manager.register(HashEmbeddingProvider(), provider_id="b", default=True)
        assert manager.default_provider_id == "b"

    def test_register_all(self):
        manager = EmbeddingManager()
        manager.register_all([HashEmbeddingProvider(dimension=8), _ExplodingProvider()])
        assert len(manager.provider_ids()) == 2

    def test_unregister_removes(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider())
        manager.unregister("hash-ngram")
        assert manager.provider_ids() == []

    def test_unregister_unknown_raises(self):
        manager = EmbeddingManager()
        with pytest.raises(KeyError):
            manager.unregister("nope")

    def test_unregister_default_moves_default(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=8), provider_id="a")
        manager.register(HashEmbeddingProvider(dimension=4), provider_id="b")
        manager.unregister("a")
        assert manager.default_provider_id == "b"

    def test_select_switches_default(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=8), provider_id="a")
        manager.register(HashEmbeddingProvider(dimension=4), provider_id="b")
        manager.select("b")
        assert manager.default_provider_id == "b"

    def test_select_unknown_raises(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider())
        with pytest.raises(KeyError):
            manager.select("nope")

    def test_set_fallback(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=8), provider_id="a")
        manager.register(HashEmbeddingProvider(dimension=4), provider_id="b")
        manager.set_fallback("b")
        assert manager.fallback_count() == 0

    def test_set_fallback_unknown_raises(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider())
        with pytest.raises(KeyError):
            manager.set_fallback("nope")

    def test_set_fallback_none_disables(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=8), provider_id="a")
        manager.set_fallback("a")
        manager.set_fallback(None)
        assert manager.default_provider_id == "a"

    def test_provider_without_any_registered_raises(self):
        manager = EmbeddingManager()
        with pytest.raises(EmbeddingError, match="no embedding provider"):
            manager.provider()

    def test_provider_by_id(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=8), provider_id="a")
        assert manager.provider("a").name == "hash-ngram"


class TestEmbeddingManagerLazyLoading:
    def test_provider_not_loaded_at_registration(self):
        provider = HashEmbeddingProvider()
        manager = EmbeddingManager()
        manager.register(provider)
        assert provider.is_loaded is False

    def test_embed_loads_provider_lazily(self):
        provider = HashEmbeddingProvider()
        manager = EmbeddingManager()
        manager.register(provider)
        manager.embed("hello")
        assert provider.is_loaded is True

    def test_dimension_loads_provider(self):
        provider = HashEmbeddingProvider(dimension=6)
        manager = EmbeddingManager()
        manager.register(provider)
        assert manager.dimension() == 6
        assert provider.is_loaded is True

    def test_unload_all(self):
        provider = HashEmbeddingProvider()
        manager = EmbeddingManager()
        manager.register(provider)
        manager.embed("hello")
        manager.unload_all()
        assert provider.is_loaded is False


class TestEmbeddingManagerEmbedding:
    def test_embed_returns_vector(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5))
        assert len(manager.embed("hello")) == 5

    def test_embed_uses_default_provider(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5), provider_id="a")
        manager.register(HashEmbeddingProvider(dimension=9), provider_id="b")
        manager.select("b")
        assert len(manager.embed("hello")) == 9

    def test_embed_with_provider_override(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5), provider_id="a")
        manager.register(HashEmbeddingProvider(dimension=9), provider_id="b")
        assert len(manager.embed("hello", provider_id="a")) == 5

    def test_embed_with_meta_not_cached(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5))
        vector, meta = manager.embed_with_meta("hello")
        assert len(vector) == 5
        assert meta.cached is False
        assert meta.fallback is False
        assert meta.provider == "hash-ngram"
        assert meta.dimension == 5
        assert meta.latency_ms > 0.0

    def test_embed_with_meta_cached_second_call(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5))
        _vector, first = manager.embed_with_meta("hello")
        vector, second = manager.embed_with_meta("hello")
        assert first.cached is False
        assert second.cached is True
        assert second.latency_ms == 0.0
        assert second.is_cache_hit is True
        assert vector == _vector

    def test_cache_stats(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5))
        manager.embed("a")
        manager.embed("a")
        manager.embed("b")
        stats = manager.cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 2

    def test_cached_count(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5))
        manager.embed("a")
        manager.embed("b")
        assert manager.cached_count() == 2

    def test_clear_cache(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5))
        manager.embed("a")
        manager.embed("a")
        manager.clear_cache()
        assert manager.cached_count() == 0
        assert manager.cache_stats() == {"hits": 0, "misses": 0}

    def test_lru_eviction(self):
        manager = EmbeddingManager(cache_size=2)
        manager.register(HashEmbeddingProvider(dimension=5))
        manager.embed("a")
        manager.embed("b")
        manager.embed("c")
        assert manager.cached_count() == 2
        stats = manager.cache_stats()
        assert stats["misses"] == 3

    def test_stats_report(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5))
        manager.embed("hello")
        stats = manager.stats()
        assert stats["cache"]["misses"] == 1
        assert stats["cached_vectors"] == 1
        assert stats["embed_calls"] == 1
        assert "health" in stats


class TestEmbeddingManagerBatching:
    def test_embed_batch(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=4))
        vectors = manager.embed_batch(["a", "b", "c"])
        assert len(vectors) == 3
        assert all(len(v) == 4 for v in vectors)

    def test_embed_batch_chunking(self):
        calls: list[int] = []

        class _CountingProvider(HashEmbeddingProvider):
            def _embed_batch_impl(self, texts: list[str]) -> list[list[float]]:
                calls.append(len(texts))
                return [self._embed_impl(t) for t in texts]

        manager = EmbeddingManager(batch_size=2)
        provider = _CountingProvider(dimension=4)
        manager.register(provider)
        vectors = manager.embed_batch(["a", "b", "c", "d", "e"])
        assert len(vectors) == 5
        assert calls == [2, 2, 1]

    def test_embed_batch_with_meta_flags(self):
        manager = EmbeddingManager(batch_size=2)
        manager.register(HashEmbeddingProvider(dimension=4))
        manager.embed("a")
        _v, metas = manager.embed_batch_with_meta(["a", "b", "a"])
        cached_flags = [m.cached for m in metas]
        assert cached_flags == [True, False, True]

    def test_embed_batch_custom_batch_size(self):
        calls: list[int] = []

        class _CountingProvider(HashEmbeddingProvider):
            def _embed_batch_impl(self, texts: list[str]) -> list[list[float]]:
                calls.append(len(texts))
                return [self._embed_impl(t) for t in texts]

        manager = EmbeddingManager(batch_size=8)
        manager.register(_CountingProvider(dimension=4))
        manager.embed_batch(["a", "b", "c"], batch_size=1)
        assert calls == [1, 1, 1]

    def test_embed_batch_equals_embed(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=4))
        batch = manager.embed_batch(["hello"])
        assert batch[0] == manager.embed("hello")


class TestEmbeddingManagerFallback:
    def test_fallback_used_on_primary_failure(self):
        manager = EmbeddingManager()
        manager.register(_ExplodingProvider(), provider_id="primary")
        manager.register(HashEmbeddingProvider(dimension=5), provider_id="backup")
        manager.select("primary")
        manager.set_fallback("backup")
        vector, meta = manager.embed_with_meta("hello")
        assert len(vector) == 5
        assert meta.fallback is True
        assert meta.provider == "hash-ngram"

    def test_fallback_event_recorded(self):
        manager = EmbeddingManager()
        manager.register(_ExplodingProvider(), provider_id="primary")
        manager.register(HashEmbeddingProvider(dimension=5), provider_id="backup")
        manager.select("primary")
        manager.set_fallback("backup")
        manager.embed("hello")
        events = manager.fallback_events()
        assert len(events) == 1
        assert events[0]["provider"] == "primary"
        assert events[0]["fallback"] == "backup"
        assert "boom" in events[0]["error"]
        assert manager.fallback_count() == 1

    def test_no_fallback_re_raises(self):
        manager = EmbeddingManager()
        manager.register(_ExplodingProvider(), provider_id="primary")
        manager.select("primary")
        with pytest.raises(EmbeddingNotAvailableError):
            manager.embed("hello")

    def test_fallback_same_as_primary_re_raises(self):
        manager = EmbeddingManager()
        manager.register(_ExplodingProvider(), provider_id="primary")
        manager.select("primary")
        manager.set_fallback("primary")
        with pytest.raises(EmbeddingNotAvailableError):
            manager.embed("hello")

    def test_error_recorded(self):
        manager = EmbeddingManager()
        manager.register(_ExplodingProvider(), provider_id="primary")
        manager.select("primary")
        with pytest.raises(EmbeddingNotAvailableError):
            manager.embed("hello")
        health = manager.health()
        assert len(health["recent_errors"]) == 1
        assert health["recent_errors"][0]["provider"] == "primary"

    def test_batch_fallback(self):
        manager = EmbeddingManager()
        manager.register(_ExplodingProvider(), provider_id="primary")
        manager.register(HashEmbeddingProvider(dimension=5), provider_id="backup")
        manager.select("primary")
        manager.set_fallback("backup")
        vectors, metas = manager.embed_batch_with_meta(["a", "b"])
        assert len(vectors) == 2
        assert all(m.fallback for m in metas)

    def test_health_structure(self):
        manager = EmbeddingManager()
        manager.register(HashEmbeddingProvider(dimension=5), provider_id="a")
        manager.register(HashEmbeddingProvider(dimension=5), provider_id="b")
        manager.select("a")
        manager.set_fallback("b")
        health = manager.health()
        assert health["registered"] == 2
        assert health["default"] == "a"
        assert health["fallback"] == "b"
        assert set(health["providers"]) == {"a", "b"}
        assert health["healthy"] is False


class TestEmbeddingManagerDiskCache:
    def test_disk_cache_persists_across_instances(self, tmp_path):
        manager1 = EmbeddingManager(cache_dir=tmp_path)
        manager1.register(HashEmbeddingProvider(dimension=5))
        manager1.embed("persist me")

        manager2 = EmbeddingManager(cache_dir=tmp_path)
        manager2.register(HashEmbeddingProvider(dimension=5))
        vector, meta = manager2.embed_with_meta("persist me")
        assert meta.cached is True
        assert len(vector) == 5

    def test_disk_cache_keyed_by_provider(self, tmp_path):
        manager1 = EmbeddingManager(cache_dir=tmp_path)
        manager1.register(HashEmbeddingProvider(dimension=8), provider_id="a")
        manager1.embed("same text")

        manager2 = EmbeddingManager(cache_dir=tmp_path)
        manager2.register(HashEmbeddingProvider(dimension=8), provider_id="a")
        manager2.register(HashEmbeddingProvider(dimension=4), provider_id="b")
        manager2.select("b")
        _v, meta = manager2.embed_with_meta("same text")
        assert meta.cached is False

    def test_disk_cache_corrupted_is_ignored(self, tmp_path):
        manager1 = EmbeddingManager(cache_dir=tmp_path)
        manager1.register(HashEmbeddingProvider(dimension=5))
        manager1.embed("hello")
        (tmp_path / "hash-ngram.json").write_text("{corrupt", encoding="utf-8")

        manager2 = EmbeddingManager(cache_dir=tmp_path)
        manager2.register(HashEmbeddingProvider(dimension=5))
        _v, meta = manager2.embed_with_meta("hello")
        assert meta.cached is False
        assert len(manager2.embed("hello")) == 5


class TestEmbeddingManagerDefault:
    def test_default_factory_uses_hash_provider(self):
        manager = EmbeddingManager.default(dimension=8)
        assert manager.default_provider_id == "hash-ngram"
        assert len(manager.embed("hello")) == 8

    def test_default_factory_dimension(self):
        manager = EmbeddingManager.default(dimension=12)
        assert manager.dimension() == 12

    def test_default_factory_cache_dir(self, tmp_path):
        manager = EmbeddingManager.default(cache_dir=tmp_path)
        manager.embed("hello")
        assert (tmp_path / "hash-ngram.json").exists()

    def test_build_manager_with_default_provider(self):
        manager = build_manager(
            default_provider=HashEmbeddingProvider(dimension=6),
            fallback_provider=_ExplodingProvider(),
        )
        assert manager.default_provider_id == "hash-ngram"
        assert manager.fallback_count() == 0
        assert len(manager.embed("hello")) == 6

    def test_build_manager_no_providers(self):
        manager = build_manager()
        assert manager.default_provider_id == "hash-ngram"
        assert len(manager.embed("hello")) == 16

    def test_build_manager_extra_providers(self):
        manager = build_manager(
            default_provider=_NamedHashProvider("a", dimension=6),
            fallback_provider=_NamedHashProvider("b", dimension=4),
            providers=[_NamedHashProvider("c", dimension=2)],
        )
        assert set(manager.provider_ids()) == {"a", "b", "c"}
        assert manager.default_provider_id == "a"

    def test_build_manager_fallback_used(self):
        manager = build_manager(
            default_provider=_ExplodingProvider(),
            fallback_provider=HashEmbeddingProvider(dimension=3),
        )
        manager.select("exploding")
        vector = manager.embed("hello")
        assert len(vector) == 3
        assert manager.fallback_count() == 1
