"""Embedding provider implementations.

Re-exports every concrete provider so consumers import from one place:
``from q_guardian.embeddings.providers import MiniLMProvider``.
"""

from __future__ import annotations

from q_guardian.embeddings.providers.cloud import (
    AzureOpenAIEmbeddingProvider,
    CloudEmbeddingProvider,
    CohereEmbeddingProvider,
    OpenAIEmbeddingProvider,
    VoyageAIEmbeddingProvider,
)
from q_guardian.embeddings.providers.hasher import (
    HashEmbeddingProvider,
    hash_vector,
)
from q_guardian.embeddings.providers.sentence_transformers import (
    BGEProvider,
    E5Provider,
    MiniLMProvider,
    SentenceTransformersProvider,
)

__all__ = [
    "AzureOpenAIEmbeddingProvider",
    "BGEProvider",
    "CloudEmbeddingProvider",
    "CohereEmbeddingProvider",
    "E5Provider",
    "HashEmbeddingProvider",
    "MiniLMProvider",
    "OpenAIEmbeddingProvider",
    "SentenceTransformersProvider",
    "VoyageAIEmbeddingProvider",
    "hash_vector",
]
