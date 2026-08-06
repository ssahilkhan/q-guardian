"""Sentence-transformers based embedding providers.

All providers share one implementation
(:class:`SentenceTransformersProvider`) and differ only in their default
model and registry name. The ``sentence-transformers`` library is imported
lazily inside :meth:`load`, so this package has **no hard dependency** on
it: installing the library makes real embeddings available, and without it
the providers raise a clear :class:`EmbeddingNotAvailableError` on load.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from q_guardian.embeddings.base import EmbeddingProvider
from q_guardian.embeddings.errors import (
    EmbeddingNotAvailableError,
    EmbeddingNotLoadedError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_HAS_SENTENCE_TRANSFORMERS: bool | None = None


def _sentence_transformers_available() -> bool:
    global _HAS_SENTENCE_TRANSFORMERS
    if _HAS_SENTENCE_TRANSFORMERS is None:
        try:
            import sentence_transformers  # noqa: F401

            _HAS_SENTENCE_TRANSFORMERS = True
        except ImportError:
            _HAS_SENTENCE_TRANSFORMERS = False
    return _HAS_SENTENCE_TRANSFORMERS


def _as_floats(vector: Any) -> list[float]:
    """Coerce a numpy array / list of numbers into a list of floats."""
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(v) for v in vector]


class SentenceTransformersProvider(EmbeddingProvider):
    """Generic sentence-transformers embedding provider.

    Args:
        model_name: Hugging Face model id (defaults to ``default_model``).
        model_factory: Optional callable ``(model_name) -> model`` used to
            build the model. Tests inject a fake here; when omitted the real
            ``sentence_transformers.SentenceTransformer`` is imported lazily.
        normalize_embeddings: Passed to the model's ``encode`` call.
        latency_window: Rolling latency window size.
    """

    default_model = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(
        self,
        *,
        model_name: str | None = None,
        model_factory: Callable[[str], Any] | None = None,
        normalize_embeddings: bool = True,
        latency_window: int = 64,
    ) -> None:
        super().__init__(latency_window=latency_window)
        self._model_name = model_name or self.default_model
        self._model_factory = model_factory
        self._normalize_embeddings = normalize_embeddings
        self._model: Any = None
        self._dimension: int | None = None

    @property
    def name(self) -> str:
        return "sentence-transformers"

    @property
    def model_id(self) -> str:
        return self._model_name

    @property
    def backend(self) -> str:
        return "sentence-transformers"

    def load(self) -> None:
        if self._loaded and self._model is not None:
            return
        if self._model is None:
            self._model = self._build_model()
        if self._dimension is None:
            self._dimension = self._read_dimension(self._model)
        self._loaded = True

    def unload(self) -> None:
        self._model = None
        self._loaded = False

    def dimension(self) -> int:
        if self._dimension is None:
            self._require_loaded()
        return int(self._dimension or 0)

    def health(self) -> bool:
        return self._loaded and self._model is not None

    def _build_model(self) -> Any:
        if self._model_factory is not None:
            return self._model_factory(self._model_name)
        if not _sentence_transformers_available():
            msg = (
                f"provider {self.name!r} requires the optional dependency "
                "'sentence-transformers' (pip install sentence-transformers); "
                "it was not found on import"
            )
            raise EmbeddingNotAvailableError(msg)
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self._model_name)

    def _read_dimension(self, model: Any) -> int:
        getter = getattr(model, "get_sentence_embedding_dimension", None)
        if callable(getter):
            try:
                return int(getter())
            except (TypeError, ValueError):
                pass
        probe = self._embed_impl("")
        if not probe:
            msg = f"provider {self.name!r} produced an empty probe embedding"
            raise EmbeddingNotAvailableError(msg)
        return len(probe)

    def _embed_impl(self, text: str) -> list[float]:
        if self._model is None:
            msg = f"provider {self.name!r} has no loaded model"
            raise EmbeddingNotLoadedError(msg)
        vector = self._model.encode(text, normalize_embeddings=self._normalize_embeddings)
        return _as_floats(vector)

    def _embed_batch_impl(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            msg = f"provider {self.name!r} has no loaded model"
            raise EmbeddingNotLoadedError(msg)
        vectors = self._model.encode(texts, normalize_embeddings=self._normalize_embeddings)
        return [_as_floats(v) for v in vectors]


class MiniLMProvider(SentenceTransformersProvider):
    """All-MiniLM-L6-v2 (384-dim) sentence embeddings."""

    default_model = "sentence-transformers/all-MiniLM-L6-v2"

    @property
    def name(self) -> str:
        return "minilm"


class BGEProvider(SentenceTransformersProvider):
    """BAAI/bge-small-en-v1.5 (384-dim) embeddings."""

    default_model = "BAAI/bge-small-en-v1.5"

    @property
    def name(self) -> str:
        return "bge"


class E5Provider(SentenceTransformersProvider):
    """intfloat/multilingual-e5-small (384-dim) embeddings."""

    default_model = "intfloat/multilingual-e5-small"

    @property
    def name(self) -> str:
        return "e5"
