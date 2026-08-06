"""Unit tests for sentence-transformers and cloud placeholder providers."""

from __future__ import annotations

import pytest

from q_guardian.embeddings.errors import (
    EmbeddingNotAvailableError,
    EmbeddingNotLoadedError,
)
from q_guardian.embeddings.providers.cloud import (
    AzureOpenAIEmbeddingProvider,
    CohereEmbeddingProvider,
    OpenAIEmbeddingProvider,
    VoyageAIEmbeddingProvider,
)
from q_guardian.embeddings.providers.sentence_transformers import (
    BGEProvider,
    E5Provider,
    MiniLMProvider,
    SentenceTransformersProvider,
    _as_floats,
)


class _FakeSentenceModel:
    """Minimal stand-in for sentence_transformers.SentenceTransformer."""

    def get_sentence_embedding_dimension(self) -> int:
        return 384

    def encode(self, texts: str | list[str], normalize_embeddings: bool = True) -> object:
        if isinstance(texts, str):
            return [0.1] * 384
        return [[0.1] * 384 for _ in texts]


class _Factory:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, model_name: str) -> _FakeSentenceModel:
        self.calls.append(model_name)
        return _FakeSentenceModel()


class TestSentenceTransformersProvider:
    def test_provider_names(self):
        assert MiniLMProvider().name == "minilm"
        assert BGEProvider().name == "bge"
        assert E5Provider().name == "e5"
        assert SentenceTransformersProvider().name == "sentence-transformers"

    def test_default_models(self):
        assert MiniLMProvider().model_id == "sentence-transformers/all-MiniLM-L6-v2"
        assert BGEProvider().model_id == "BAAI/bge-small-en-v1.5"
        assert E5Provider().model_id == "intfloat/multilingual-e5-small"

    def test_custom_model_name(self):
        provider = SentenceTransformersProvider(model_name="custom/model")
        assert provider.model_id == "custom/model"

    def test_backend(self):
        assert MiniLMProvider().backend == "sentence-transformers"

    def test_load_with_factory_sets_dimension(self):
        provider = MiniLMProvider(model_factory=_Factory())
        provider.load()
        assert provider.dimension() == 384
        assert provider.is_loaded is True

    def test_factory_receives_model_name(self):
        factory = _Factory()
        provider = MiniLMProvider(model_name="my-model", model_factory=factory)
        provider.load()
        assert factory.calls == ["my-model"]

    def test_embed_returns_floats(self):
        provider = MiniLMProvider(model_factory=_Factory())
        provider.load()
        vector = provider.embed("hello")
        assert len(vector) == 384
        assert all(isinstance(v, float) for v in vector)

    def test_embed_batch(self):
        provider = MiniLMProvider(model_factory=_Factory())
        provider.load()
        vectors = provider.embed_batch(["a", "b"])
        assert len(vectors) == 2
        assert len(vectors[0]) == 384

    def test_embed_before_load_raises(self):
        provider = MiniLMProvider(model_factory=_Factory())
        with pytest.raises(EmbeddingNotLoadedError):
            provider.embed("hello")

    def test_unload_resets_model(self):
        provider = MiniLMProvider(model_factory=_Factory())
        provider.load()
        provider.unload()
        assert provider.health() is False
        with pytest.raises(EmbeddingNotLoadedError):
            provider.embed("hello")

    def test_missing_library_raises_not_available(self, monkeypatch):
        provider = MiniLMProvider()
        monkeypatch.setattr(
            "q_guardian.embeddings.providers.sentence_transformers._sentence_transformers_available",
            lambda: False,
        )
        with pytest.raises(EmbeddingNotAvailableError, match="sentence-transformers"):
            provider.load()

    def test_dimension_via_probe_when_no_getter(self):
        class _ProbeModel:
            def encode(self, texts, normalize_embeddings=True):
                if isinstance(texts, str):
                    return [0.5, 0.25]
                return [[0.5, 0.25] for _ in texts]

        provider = SentenceTransformersProvider(model_factory=lambda name: _ProbeModel())
        provider.load()
        assert provider.dimension() == 2

    def test_metadata(self):
        provider = MiniLMProvider(model_factory=_Factory())
        provider.load()
        meta = provider.metadata()
        assert meta["provider"] == "minilm"
        assert meta["backend"] == "sentence-transformers"
        assert meta["dimension"] == 384


class TestAsFloats:
    class _NumpyLike:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def tolist(self) -> list[float]:
            return self._values

    def test_passthrough_list(self):
        assert _as_floats([1, 2, 3]) == [1.0, 2.0, 3.0]

    def test_coerces_numpy_like(self):
        assert _as_floats(self._NumpyLike([1.5, 2])) == [1.5, 2.0]


class TestCloudPlaceholders:
    def test_openai_identity(self):
        provider = OpenAIEmbeddingProvider()
        assert provider.name == "openai-embeddings"
        assert provider.required_env == "OPENAI_API_KEY"
        assert provider.model_id == "text-embedding-3-small"
        assert provider.dimension() == 1536
        assert provider.requires_token is True

    def test_azure_identity(self):
        provider = AzureOpenAIEmbeddingProvider()
        assert provider.name == "azure-openai-embeddings"
        assert provider.required_env == "AZURE_OPENAI_API_KEY"

    def test_voyage_identity(self):
        provider = VoyageAIEmbeddingProvider()
        assert provider.name == "voyage-ai"
        assert provider.required_env == "VOYAGE_API_KEY"
        assert provider.dimension() == 1024

    def test_cohere_identity(self):
        provider = CohereEmbeddingProvider()
        assert provider.name == "cohere-embeddings"
        assert provider.required_env == "COHERE_API_KEY"
        assert provider.model_id == "embed-english-v3.0"

    def test_backend_is_cloud_placeholder(self):
        assert OpenAIEmbeddingProvider().backend == "cloud-placeholder"

    def test_dimension_override(self):
        assert OpenAIEmbeddingProvider(dimension=128).dimension() == 128

    def test_load_without_credentials_raises(self):
        with pytest.raises(EmbeddingNotAvailableError, match="not implemented yet"):
            OpenAIEmbeddingProvider().load()

    def test_load_with_api_key_allows_load(self):
        provider = OpenAIEmbeddingProvider(api_key="secret")
        provider.load()
        assert provider.is_loaded is True

    def test_health_always_false(self):
        assert OpenAIEmbeddingProvider().health() is False

    def test_embed_raises_not_available(self):
        provider = OpenAIEmbeddingProvider(api_key="secret")
        provider.load()
        with pytest.raises(EmbeddingNotAvailableError):
            provider.embed("hello")

    def test_embed_batch_raises_not_available(self):
        provider = OpenAIEmbeddingProvider(api_key="secret")
        provider.load()
        with pytest.raises(EmbeddingNotAvailableError):
            provider.embed_batch(["a", "b"])

    def test_metadata_marks_unimplemented(self):
        meta = OpenAIEmbeddingProvider().metadata()
        assert meta["implemented"] is False
        assert meta["requires_token"] is True
        assert meta["required_env"] == "OPENAI_API_KEY"
