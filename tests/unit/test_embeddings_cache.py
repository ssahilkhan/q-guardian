"""Unit tests for the JSON-backed disk embedding cache."""

from __future__ import annotations

import json

from q_guardian.embeddings.manager import EmbeddingCache


class TestEmbeddingCache:
    def test_directory_created(self, tmp_path):
        cache = EmbeddingCache(tmp_path / "nested" / "cache")
        assert cache.directory.exists()

    def test_save_and_load_roundtrip(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        cache.save("hash-ngram", {"k1": [0.1, 0.2]})
        assert cache.load("hash-ngram") == {"k1": [0.1, 0.2]}

    def test_load_missing_provider_returns_empty(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        assert cache.load("nope") == {}

    def test_load_corrupted_file_returns_empty(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        cache._path("hash-ngram").write_text("{not json", encoding="utf-8")
        assert cache.load("hash-ngram") == {}

    def test_load_coerces_values_to_float(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        cache._path("p").write_text(json.dumps({"k": [1, 2, 3]}), encoding="utf-8")
        assert cache.load("p") == {"k": [1.0, 2.0, 3.0]}

    def test_contains(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        cache.save("p", {"key-a": [1.0]})
        assert cache.contains("p", "key-a") is True
        assert cache.contains("p", "key-b") is False

    def test_clear_specific_provider(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        cache.save("p1", {"a": [1.0]})
        cache.save("p2", {"b": [2.0]})
        cache.clear("p1")
        assert cache.load("p1") == {}
        assert cache.load("p2") == {"b": [2.0]}

    def test_clear_all(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        cache.save("p1", {"a": [1.0]})
        cache.save("p2", {"b": [2.0]})
        cache.clear()
        assert cache.load("p1") == {}
        assert cache.load("p2") == {}

    def test_snapshot_groups_by_provider(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        cache.save("p1", {"a": [1.0]})
        cache.save("p2", {"b": [2.0]})
        snapshot = cache.snapshot()
        assert set(snapshot) == {"p1", "p2"}
        assert snapshot["p1"] == {"a": [1.0]}

    def test_snapshot_empty(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        assert cache.snapshot() == {}

    def test_provider_file_named_after_provider_id(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        cache.save("hash-ngram", {"a": [1.0]})
        assert (tmp_path / "hash-ngram.json").exists()

    def test_overwrite_replaces_file(self, tmp_path):
        cache = EmbeddingCache(tmp_path)
        cache.save("p", {"a": [1.0]})
        cache.save("p", {"b": [2.0]})
        assert cache.load("p") == {"b": [2.0]}
