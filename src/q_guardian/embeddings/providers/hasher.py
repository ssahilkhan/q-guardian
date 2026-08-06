"""Dependency-free, deterministic hash embedding provider.

Implements the same :class:`EmbeddingProvider` interface using feature
hashing over word tokens, word n-grams and (capped) character trigrams.
It needs no model download and no optional dependency, so it is the
framework's built-in offline provider: the default used by
``EmbeddingManager.default()`` and the automatic fallback behind cloud or
sentence-transformers providers in test/offline environments.

The vector is L2-normalized and fully deterministic for a fixed
``(dimension, seed)``.
"""

from __future__ import annotations

import hashlib
import math
import re

from q_guardian.embeddings.base import EmbeddingProvider

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")
_MAX_CHAR_NGRAMS = 2000


def hash_vector(text: str, dimension: int, seed: int = 42) -> list[float]:
    """Compute a deterministic hashed n-gram embedding of ``text``."""
    vector = [0.0] * dimension
    if not text:
        return vector

    lowered = " ".join(text.lower().split())
    tokens: list[str] = []
    for word in _WORD_SPLIT.split(lowered):
        if not word:
            continue
        tokens.append(word)
        for size in (2, 3):
            tokens.extend(word[i : i + size] for i in range(len(word) - size + 1))

    # Whole-text character trigrams add long-range lexical signal; cap the
    # count so very long prompts stay cheap.
    trigram_limit = min(len(lowered) - 2, _MAX_CHAR_NGRAMS)
    tokens.extend(lowered[i : i + 3] for i in range(max(trigram_limit, 0)))

    for token in tokens:
        digest = hashlib.sha256(f"{seed}:{token}".encode()).digest()
        idx = int.from_bytes(digest[:8], "big") % dimension
        sign = 1.0 if digest[8] & 1 else -1.0
        vector[idx] += sign

    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0.0:
        vector = [v / norm for v in vector]
    return vector


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic offline embedding based on hashed n-grams.

    Args:
        dimension: Dimensionality of the produced vectors (default 16).
        seed: Hash seed; different seeds produce different vector spaces.
        latency_window: Rolling latency window size.
    """

    default_model = "qguardian/hash-ngram-v1"

    def __init__(
        self,
        *,
        dimension: int = 16,
        seed: int = 42,
        latency_window: int = 64,
    ) -> None:
        super().__init__(latency_window=latency_window)
        if dimension < 1:
            msg = f"dimension must be >= 1, got {dimension}"
            raise ValueError(msg)
        self._dimension = dimension
        self._seed = seed

    @property
    def name(self) -> str:
        return "hash-ngram"

    @property
    def backend(self) -> str:
        return "hash"

    def load(self) -> None:
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def dimension(self) -> int:
        return self._dimension

    def health(self) -> bool:
        return self._loaded

    def _embed_impl(self, text: str) -> list[float]:
        return hash_vector(text, self._dimension, self._seed)

    def _embed_batch_impl(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_impl(text) for text in texts]
