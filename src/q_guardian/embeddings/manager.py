"""EmbeddingManager — provider registry, caching, batching and fallback.

Responsibilities:

- register/unregister providers (keyed by ``provider.name`` or an alias)
- lazy loading (providers are loaded on first use, not at registration)
- in-memory LRU caching keyed by ``(provider_id, text)`` plus an optional
  JSON-backed disk cache
- batching (configurable batch size when calling ``embed_batch``)
- health monitoring (per-provider health + manager-level error records)
- provider selection (a default provider, switchable at runtime)
- fallback (when the selected provider fails, retry with a fallback
  provider and record the event)
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from q_guardian.embeddings.errors import EmbeddingError
from q_guardian.embeddings.explain import EmbeddingMeta
from q_guardian.embeddings.providers.hasher import HashEmbeddingProvider

if TYPE_CHECKING:
    from q_guardian.embeddings.base import EmbeddingProvider

_CACHE_KEY_SEPARATOR = "\x00"


def _cache_key(provider_id: str, text: str) -> str:
    raw = f"{provider_id}{_CACHE_KEY_SEPARATOR}{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """JSON-backed disk cache of embedding vectors.

    Vectors are stored per provider in ``<directory>/<provider_id>.json``
    keyed by the sha256 of ``(provider_id, text)``. Safe to share across
    runs and processes; corrupted files are treated as empty.
    """

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._directory

    def _path(self, provider_id: str) -> Path:
        return self._directory / f"{provider_id}.json"

    def save(self, provider_id: str, vectors: dict[str, list[float]]) -> None:
        self._path(provider_id).write_text(json.dumps(vectors), encoding="utf-8")

    def load(self, provider_id: str) -> dict[str, list[float]]:
        path = self._path(provider_id)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        return {str(k): [float(v) for v in vals] for k, vals in data.items()}

    def contains(self, provider_id: str, key: str) -> bool:
        return key in self.load(provider_id)

    def clear(self, provider_id: str | None = None) -> None:
        if provider_id is None:
            for path in self._directory.glob("*.json"):
                path.unlink(missing_ok=True)
            return
        self._path(provider_id).unlink(missing_ok=True)

    def snapshot(self) -> dict[str, dict[str, list[float]]]:
        return {path.stem: self.load(path.stem) for path in sorted(self._directory.glob("*.json"))}


class EmbeddingManager:
    """Registry + lazy-loading + caching + batching + fallback for embeddings.

    Args:
        providers: Initial providers to register.
        default_provider_id: Provider used when no ``provider_id`` is given.
            Defaults to the first registered provider.
        fallback_provider_id: Provider used when the selected provider fails
            (``None`` disables fallback).
        cache_size: Max in-memory vectors per cache.
        batch_size: Default chunk size for ``embed_batch``.
        cache_dir: Optional directory for the JSON disk cache.
    """

    def __init__(
        self,
        *,
        providers: list[EmbeddingProvider] | None = None,
        default_provider_id: str | None = None,
        fallback_provider_id: str | None = None,
        cache_size: int = 2048,
        batch_size: int = 32,
        cache_dir: str | Path | None = None,
    ) -> None:
        self._providers: dict[str, EmbeddingProvider] = {}
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_size = max(1, cache_size)
        self._batch_size = max(1, batch_size)
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._disk_cache = EmbeddingCache(self._cache_dir) if self._cache_dir else None
        self._default_id: str | None = default_provider_id
        self._fallback_id: str | None = fallback_provider_id
        self._fallback_events: list[dict[str, Any]] = []
        self._errors: list[dict[str, Any]] = []
        self._cache_stats = {"hits": 0, "misses": 0}
        self._compute_time_ms = 0.0
        self._embed_calls = 0
        if providers:
            self.register_all(providers)

    @classmethod
    def default(
        cls,
        *,
        dimension: int = 16,
        cache_dir: str | Path | None = None,
        cache_size: int = 2048,
    ) -> EmbeddingManager:
        """Build a manager with the dependency-free hash provider as default."""
        manager = cls(cache_dir=cache_dir, cache_size=cache_size)
        manager.register(HashEmbeddingProvider(dimension=dimension), default=True)
        return manager

    # ── Registration / selection ───────────────────────────────────────

    def register(
        self,
        provider: EmbeddingProvider,
        *,
        provider_id: str | None = None,
        default: bool = False,
    ) -> str:
        """Register a provider; returns its effective id.

        Raises:
            EmbeddingError: If a provider with the same id already exists.
        """
        pid = provider_id or provider.name
        if pid in self._providers:
            msg = f"embedding provider already registered: {pid}"
            raise EmbeddingError(msg)
        self._providers[pid] = provider
        if default or self._default_id is None:
            self._default_id = pid
        return pid

    def register_all(self, providers: list[EmbeddingProvider]) -> None:
        for provider in providers:
            self.register(provider)

    def unregister(self, provider_id: str) -> EmbeddingProvider:
        if provider_id not in self._providers:
            msg = f"unknown embedding provider: {provider_id}"
            raise KeyError(msg)
        provider = self._providers.pop(provider_id)
        if self._default_id == provider_id:
            self._default_id = next(iter(self._providers), None)
        return provider

    def select(self, provider_id: str) -> None:
        """Set the default provider used when none is specified."""
        self._get_provider(provider_id)
        self._default_id = provider_id

    def set_fallback(self, provider_id: str) -> None:
        """Set (or disable with ``None``) the fallback provider."""
        if provider_id is not None:
            self._get_provider(provider_id)
        self._fallback_id = provider_id

    def provider_ids(self) -> list[str]:
        return list(self._providers)

    @property
    def default_provider_id(self) -> str | None:
        return self._default_id

    @property
    def default_provider(self) -> EmbeddingProvider | None:
        if self._default_id is None:
            return None
        return self._providers[self._default_id]

    def provider(self, provider_id: str | None = None) -> EmbeddingProvider:
        """Return the provider object (no load)."""
        pid = provider_id or self._default_id
        if pid is None:
            msg = "no embedding provider registered"
            raise EmbeddingError(msg)
        return self._get_provider(pid)

    def _get_provider(self, provider_id: str) -> EmbeddingProvider:
        if provider_id not in self._providers:
            msg = f"unknown embedding provider: {provider_id}"
            raise KeyError(msg)
        return self._providers[provider_id]

    # ── Lazy loading / health ──────────────────────────────────────────

    def _ensure_loaded(self, provider: EmbeddingProvider) -> None:
        if not provider.is_loaded:
            provider.load()

    def health(self) -> dict[str, Any]:
        """Per-provider health plus aggregate + recent errors."""
        status = {pid: provider.health() for pid, provider in self._providers.items()}
        recent_errors = self._errors[-5:]
        return {
            "providers": status,
            "healthy": bool(status) and all(status.values()),
            "registered": len(self._providers),
            "default": self._default_id,
            "fallback": self._fallback_id,
            "recent_errors": recent_errors,
        }

    def unload_all(self) -> None:
        for provider in self._providers.values():
            provider.unload()

    # ── Metadata / dimension ───────────────────────────────────────────

    def dimension(self, provider_id: str | None = None) -> int:
        provider = self.provider(provider_id)
        self._ensure_loaded(provider)
        return provider.dimension()

    def metadata(self, provider_id: str | None = None) -> dict[str, Any]:
        provider = self.provider(provider_id)
        return provider.metadata()

    # ── Single-text embedding ──────────────────────────────────────────

    def embed(self, text: str, provider_id: str | None = None) -> list[float]:
        """Embed ``text`` with caching, lazy loading and fallback."""
        vector, _meta = self.embed_with_meta(text, provider_id=provider_id)
        return vector

    def embed_with_meta(
        self,
        text: str,
        provider_id: str | None = None,
    ) -> tuple[list[float], EmbeddingMeta]:
        """Like :meth:`embed` but also returns an :class:`EmbeddingMeta`."""
        pid = provider_id or self._default_id
        if pid is None:
            msg = "no embedding provider registered"
            raise EmbeddingError(msg)
        provider = self._get_provider(pid)

        key = _cache_key(pid, text)
        cached = self._retrieve(pid, key)
        if cached is not None:
            self._cache_stats["hits"] += 1
            return cached, self._meta_for(provider, cached, cached=True)

        self._cache_stats["misses"] += 1
        vector, used = self._compute_with_fallback(text, provider, provider_id=pid)
        self._store(pid, key, vector)
        return vector, self._meta_for(used, vector, cached=False)

    def _compute_with_fallback(
        self,
        text: str,
        provider: EmbeddingProvider,
        *,
        provider_id: str,
    ) -> tuple[list[float], EmbeddingProvider]:
        try:
            self._ensure_loaded(provider)
            vector, _latency = self._compute(text, provider)
            return vector, provider
        except Exception as exc:
            self._record_error(provider_id, exc)
            if self._fallback_id is None or self._fallback_id == provider_id:
                raise
            fallback = self._get_provider(self._fallback_id)
            self._record_fallback(provider_id, exc, text)
            self._ensure_loaded(fallback)
            vector, _latency = self._compute(text, fallback)
            return vector, fallback

    def _compute(self, text: str, provider: EmbeddingProvider) -> tuple[list[float], float]:
        start = time.perf_counter_ns()
        vector = provider.embed(text)
        latency_ms = max((time.perf_counter_ns() - start) / 1e6, 0.001)
        self._compute_time_ms += latency_ms
        self._embed_calls += 1
        return vector, latency_ms

    # ── Batched embedding ──────────────────────────────────────────────

    def embed_batch(
        self,
        texts: list[str],
        provider_id: str | None = None,
        batch_size: int | None = None,
    ) -> list[list[float]]:
        vectors, _metas = self.embed_batch_with_meta(
            texts, provider_id=provider_id, batch_size=batch_size
        )
        return vectors

    def embed_batch_with_meta(
        self,
        texts: list[str],
        provider_id: str | None = None,
        batch_size: int | None = None,
    ) -> tuple[list[list[float]], list[EmbeddingMeta]]:
        """Batch-embed texts, reusing cache hits and chunking by batch size."""
        pid = provider_id or self._default_id
        if pid is None:
            msg = "no embedding provider registered"
            raise EmbeddingError(msg)
        provider = self._get_provider(pid)

        results: list[list[float]] = []
        metas: list[EmbeddingMeta] = []
        missing: list[int] = []
        missing_texts: list[str] = []

        for index, text in enumerate(texts):
            key = _cache_key(pid, text)
            cached = self._retrieve(pid, key)
            if cached is not None:
                self._cache_stats["hits"] += 1
                results.append(list(cached))
                metas.append(self._meta_for(provider, cached, cached=True))
            else:
                self._cache_stats["misses"] += 1
                results.append([])  # placeholder, replaced below
                metas.append(self._meta_for(provider, [], cached=False))
                missing.append(index)
                missing_texts.append(text)

        if missing_texts:
            computed, used = self._batch_with_fallback(
                missing_texts, provider, provider_id=pid, batch_size=batch_size
            )
            for index, vector, text in zip(missing, computed, missing_texts, strict=True):
                key = _cache_key(pid, text)
                self._store(pid, key, vector)
                results[index] = vector
                metas[index] = self._meta_for(used, vector, cached=False)
        return results, metas

    def _batch_with_fallback(
        self,
        texts: list[str],
        provider: EmbeddingProvider,
        *,
        provider_id: str,
        batch_size: int | None,
    ) -> tuple[list[list[float]], EmbeddingProvider]:
        chunk_size = batch_size or self._batch_size
        try:
            self._ensure_loaded(provider)
            vectors = self._batch_chunks(texts, provider, chunk_size)
            return vectors, provider
        except Exception as exc:
            self._record_error(provider_id, exc)
            if self._fallback_id is None or self._fallback_id == provider_id:
                raise
            fallback = self._get_provider(self._fallback_id)
            self._record_fallback(provider_id, exc, text=texts[0] if texts else "")
            self._ensure_loaded(fallback)
            vectors = self._batch_chunks(texts, fallback, chunk_size)
            return vectors, fallback

    def _batch_chunks(
        self,
        texts: list[str],
        provider: EmbeddingProvider,
        chunk_size: int,
    ) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), chunk_size):
            chunk = texts[start : start + chunk_size]
            start_time = time.perf_counter_ns()
            chunk_vectors = provider.embed_batch(chunk)
            latency_ms = max((time.perf_counter_ns() - start_time) / 1e6, 0.001)
            self._compute_time_ms += latency_ms
            self._embed_calls += len(chunk)
            vectors.extend(chunk_vectors)
        return vectors

    # ── Cache management ───────────────────────────────────────────────

    def _retrieve(self, provider_id: str, key: str) -> list[float] | None:
        """Look up a vector in the in-memory cache, then the disk cache.

        Disk hits are promoted into the in-memory cache so repeated calls
        stay fast. Returns ``None`` on a miss.
        """
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return list(cached)
        if self._disk_cache is not None and self._disk_cache.contains(provider_id, key):
            stored = self._disk_cache.load(provider_id).get(key)
            if stored is not None:
                self._cache[key] = stored
                self._cache.move_to_end(key)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
                return list(stored)
        return None

    def _store(self, provider_id: str, key: str, vector: list[float]) -> None:
        self._cache[key] = list(vector)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        if self._disk_cache is not None:
            self._disk_cache.save(provider_id, {key: vector})

    def cached_count(self) -> int:
        return len(self._cache)

    def cache_stats(self) -> dict[str, int]:
        return dict(self._cache_stats)

    def clear_cache(self) -> None:
        self._cache.clear()
        self._cache_stats = {"hits": 0, "misses": 0}

    # ── Fallback / error records ───────────────────────────────────────

    def fallback_events(self) -> list[dict[str, Any]]:
        return list(self._fallback_events)

    def fallback_count(self) -> int:
        return len(self._fallback_events)

    def _record_fallback(self, provider_id: str, error: Exception, text: str) -> None:
        self._fallback_events.append(
            {
                "provider": provider_id,
                "fallback": self._fallback_id,
                "error": str(error),
                "text_preview": text[:120],
            }
        )

    def _record_error(self, provider_id: str, error: Exception) -> None:
        self._errors.append(
            {"provider": provider_id, "error": str(error), "type": type(error).__name__}
        )

    # ── Explainability helpers ─────────────────────────────────────────

    def _meta_for(
        self,
        provider: EmbeddingProvider,
        vector: list[float],
        *,
        cached: bool,
    ) -> EmbeddingMeta:
        return EmbeddingMeta(
            provider=provider.name,
            model=provider.model_id,
            dimension=len(vector),
            latency_ms=0.0 if cached else self._last_latency_ms(),
            cached=cached,
            fallback=provider.name != (self._default_id or ""),
        )

    def _last_latency_ms(self) -> float:
        """Mean latency per embed call over all computed vectors so far."""
        if self._embed_calls == 0:
            return 0.0
        return round(self._compute_time_ms / self._embed_calls, 4)

    def stats(self) -> dict[str, Any]:
        """Manager-level statistics (cache, compute time, fallbacks)."""
        return {
            "cache": self.cache_stats(),
            "cached_vectors": self.cached_count(),
            "embed_calls": self._embed_calls,
            "compute_time_ms": round(self._compute_time_ms, 4),
            "fallback_events": self.fallback_count(),
            "health": self.health(),
        }


def build_manager(
    *,
    default_provider: EmbeddingProvider | None = None,
    fallback_provider: EmbeddingProvider | None = None,
    providers: list[EmbeddingProvider] | None = None,
    cache_dir: str | Path | None = None,
) -> EmbeddingManager:
    """Convenience factory for wiring an :class:`EmbeddingManager`.

    Ensures at least one provider is registered (a hash provider when none
    is supplied) so ``embed`` never fails with "no provider".
    """
    all_providers = list(providers or [])
    if default_provider is not None and default_provider not in all_providers:
        all_providers.append(default_provider)
    if fallback_provider is not None and fallback_provider not in all_providers:
        all_providers.append(fallback_provider)
    if not all_providers:
        all_providers.append(HashEmbeddingProvider())

    manager = EmbeddingManager(cache_dir=cache_dir)
    default_id: str | None = None
    for provider in all_providers:
        pid = manager.register(provider)
        if provider is default_provider:
            default_id = pid
    if default_id is None:
        default_id = all_providers[0].name
    manager.select(default_id)
    if fallback_provider is not None:
        manager.set_fallback(fallback_provider.name)
    return manager
