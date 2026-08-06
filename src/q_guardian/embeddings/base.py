"""Embedding provider interface and shared lifecycle helpers.

Every embedding backend (sentence-transformers models, the dependency-free
hash embedder, and the future cloud placeholders) implements
:class:`EmbeddingProvider`. The rest of the subsystem (manager, fusion,
benchmarking, explainability) operates against this single interface, so
providers stay interchangeable behind dependency injection.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import deque
from statistics import fmean
from typing import Any

from q_guardian.embeddings.errors import EmbeddingNotLoadedError

_PROVIDER_KEY = "provider"
_MODEL_KEY = "model"
_DIMENSION_KEY = "dimension"
_LATENCY_KEY = "latency_ms"

_MIN_LATENCY_SECONDS = 1e-6  # floor: never report sub-microsecond latency as zero


class EmbeddingProvider(ABC):
    """Common interface implemented by every embedding backend.

    Lifecycle: :meth:`load` (idempotent, may be lazy via the manager) →
    :meth:`embed`/:meth:`embed_batch` → :meth:`unload`. :meth:`metadata`
    returns a stable, JSON-serializable record (provider, model, dimension,
    rolling latency) used for explainability and reports.

    Subclasses implement the ``_embed_impl``/``_embed_batch_impl`` hooks;
    the public ``embed``/``embed_batch`` methods wrap them with a load guard
    and latency accounting so every provider reports the same numbers.
    """

    default_model: str = ""

    def __init__(self, *, latency_window: int = 64) -> None:
        self._latencies: deque[float] = deque(maxlen=latency_window)
        self._loaded = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier (used as the registry key)."""

    @property
    def model_id(self) -> str:
        """Identifier of the underlying embedding model."""
        return self.default_model

    @property
    def backend(self) -> str:
        """Backend family: ``sentence-transformers``, ``hash`` or ``cloud``."""
        return "generic"

    @property
    def requires_token(self) -> bool:
        """Whether a token/credential is required to use this provider."""
        return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @abstractmethod
    def load(self) -> None:
        """Load the model into memory. Idempotent."""

    @abstractmethod
    def unload(self) -> None:
        """Release the model. Idempotent."""

    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the produced embeddings."""

    @abstractmethod
    def health(self) -> bool:
        """True when the provider is loaded and ready to embed."""

    def embed(self, text: str) -> list[float]:
        """Embed a single text into a dense vector."""
        self._require_loaded()
        start = time.perf_counter_ns()
        vector = self._embed_impl(text)
        self._record_latency((time.perf_counter_ns() - start) / 1e9)
        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts, allowing model-specific batched encoding."""
        self._require_loaded()
        start = time.perf_counter_ns()
        vectors = self._embed_batch_impl(texts)
        per_item = (time.perf_counter_ns() - start) / 1e9 / max(len(texts), 1)
        for _ in texts:
            self._record_latency(per_item)
        return vectors

    def metadata(self) -> dict[str, Any]:
        """Stable metadata record used for explainability and reports."""
        return {
            _PROVIDER_KEY: self.name,
            _MODEL_KEY: self.model_id,
            _DIMENSION_KEY: self.dimension(),
            _LATENCY_KEY: self.average_latency_ms(),
            "load_status": "loaded" if self.is_loaded else "unloaded",
            "backend": self.backend,
            "requires_token": self.requires_token,
            "implemented": True,
        }

    # ── Shared helpers ─────────────────────────────────────────────────

    def average_latency_ms(self) -> float:
        """Rolling mean inference latency in milliseconds."""
        if not self._latencies:
            return 0.0
        return round(fmean(self._latencies), 4)

    def _record_latency(self, seconds: float) -> None:
        self._latencies.append(max(seconds, _MIN_LATENCY_SECONDS) * 1000.0)

    def _require_loaded(self) -> None:
        if not self._loaded:
            msg = f"provider {self.name!r} is not loaded; call load() first"
            raise EmbeddingNotLoadedError(msg)

    @abstractmethod
    def _embed_impl(self, text: str) -> list[float]:
        """Provider-specific single-text embedding (no load guard)."""

    @abstractmethod
    def _embed_batch_impl(self, texts: list[str]) -> list[list[float]]:
        """Provider-specific batched embedding (no load guard)."""
