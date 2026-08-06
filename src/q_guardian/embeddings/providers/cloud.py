"""Placeholder providers for cloud embedding APIs.

OpenAI, Azure OpenAI, Voyage AI and Cohere are registered now so the
catalog documents the full provider set. They have **no hard dependency on
any cloud SDK**: nothing is imported, and using them before implementation
raises a clear :class:`EmbeddingNotAvailableError`. Wiring (HTTP clients,
retries, auth) is a later phase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from q_guardian.embeddings.base import EmbeddingProvider
from q_guardian.embeddings.errors import EmbeddingNotAvailableError


class CloudEmbeddingProvider(EmbeddingProvider, ABC):
    """Abstract placeholder for a remote embedding API.

    Subclasses declare a default model, dimension hint and the environment
    variable that will carry the credential. ``embed``/``embed_batch`` are
    not implemented yet and always raise.
    """

    default_model: str = ""
    default_dimension: int = 0

    def __init__(
        self,
        *,
        model_name: str | None = None,
        dimension: int | None = None,
        api_key: str | None = None,
        latency_window: int = 64,
    ) -> None:
        super().__init__(latency_window=latency_window)
        self._model_name = model_name or self.default_model
        self._dimension = dimension or self.default_dimension
        self._api_key = api_key

    @property
    @abstractmethod
    def required_env(self) -> str | None:
        """Environment variable that will carry the credential."""

    @property
    def model_id(self) -> str:
        return self._model_name

    @property
    def backend(self) -> str:
        return "cloud-placeholder"

    @property
    def requires_token(self) -> bool:
        return True

    def load(self) -> None:
        if self._api_key is None and self.required_env is not None:
            msg = (
                f"provider {self.name!r} is a cloud placeholder and is not "
                "implemented yet; a future phase will wire "
                f"{self.required_env}"
            )
            raise EmbeddingNotAvailableError(msg)
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def dimension(self) -> int:
        return self._dimension

    def health(self) -> bool:
        return False

    def metadata(self) -> dict[str, object]:
        record = super().metadata()
        record["required_env"] = self.required_env
        record["implemented"] = False
        return record

    def _embed_impl(self, text: str) -> list[float]:
        raise self._not_implemented()

    def _embed_batch_impl(self, texts: list[str]) -> list[list[float]]:
        raise self._not_implemented()

    def _not_implemented(self) -> EmbeddingNotAvailableError:
        msg = (
            f"provider {self.name!r} is a registered cloud placeholder and "
            "cannot embed yet (scheduled for a later phase)"
        )
        return EmbeddingNotAvailableError(msg)


class OpenAIEmbeddingProvider(CloudEmbeddingProvider):
    """OpenAI ``text-embedding-3-small`` placeholder (1536-dim)."""

    default_model = "text-embedding-3-small"
    default_dimension = 1536

    @property
    def name(self) -> str:
        return "openai-embeddings"

    @property
    def required_env(self) -> str | None:
        return "OPENAI_API_KEY"


class AzureOpenAIEmbeddingProvider(CloudEmbeddingProvider):
    """Azure OpenAI ``text-embedding-3-small`` placeholder (1536-dim)."""

    default_model = "text-embedding-3-small"
    default_dimension = 1536

    @property
    def name(self) -> str:
        return "azure-openai-embeddings"

    @property
    def required_env(self) -> str | None:
        return "AZURE_OPENAI_API_KEY"


class VoyageAIEmbeddingProvider(CloudEmbeddingProvider):
    """Voyage AI ``voyage-3-small`` placeholder (1024-dim)."""

    default_model = "voyage-3-small"
    default_dimension = 1024

    @property
    def name(self) -> str:
        return "voyage-ai"

    @property
    def required_env(self) -> str | None:
        return "VOYAGE_API_KEY"


class CohereEmbeddingProvider(CloudEmbeddingProvider):
    """Cohere ``embed-english-v3.0`` placeholder (1024-dim)."""

    default_model = "embed-english-v3.0"
    default_dimension = 1024

    @property
    def name(self) -> str:
        return "cohere-embeddings"

    @property
    def required_env(self) -> str | None:
        return "COHERE_API_KEY"
