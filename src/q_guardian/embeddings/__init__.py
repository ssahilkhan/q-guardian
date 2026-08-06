"""Semantic embedding subsystem (V2.0 M3).

Extends the handcrafted feature pipeline with semantic embeddings through a
fully modular provider interface. The handcrafted 43-feature pipeline
remains the default and is never modified; embeddings are layered on top
through three feature modes: ``handcrafted``, ``embedding`` and ``hybrid``.

Public surface: providers, :class:`EmbeddingManager`, feature fusion
(:class:`FeatureMode`, :class:`ModeFeatureExtractor`,
:class:`EmbeddingFeatureProvider`), explainability
(:class:`EmbeddingMeta`, :class:`EmbeddingTrace`), trainer adapters
(:class:`ModeTrainingAdapter`, :class:`ModeQuantumAdapter`) and the mode
comparison benchmark (:class:`ModeComparisonRunner`).
"""

from __future__ import annotations

from q_guardian.embeddings.base import EmbeddingProvider
from q_guardian.embeddings.benchmark import (
    ModeComparisonReport,
    ModeComparisonRunner,
    ModeDetectionBenchmark,
)
from q_guardian.embeddings.errors import (
    EmbeddingError,
    EmbeddingNotAvailableError,
    EmbeddingNotLoadedError,
    EmbeddingProviderError,
)
from q_guardian.embeddings.explain import EmbeddingMeta, EmbeddingTrace
from q_guardian.embeddings.fusion import (
    EmbeddingFeatureProvider,
    FeatureMode,
    ModeFeatureExtractor,
    ModeHybridEvaluator,
)
from q_guardian.embeddings.integration import (
    ModeQuantumAdapter,
    ModeTrainingAdapter,
)
from q_guardian.embeddings.manager import (
    EmbeddingCache,
    EmbeddingManager,
    build_manager,
)
from q_guardian.embeddings.providers import (
    AzureOpenAIEmbeddingProvider,
    BGEProvider,
    CloudEmbeddingProvider,
    CohereEmbeddingProvider,
    E5Provider,
    HashEmbeddingProvider,
    MiniLMProvider,
    OpenAIEmbeddingProvider,
    SentenceTransformersProvider,
    VoyageAIEmbeddingProvider,
)

__all__ = [
    "AzureOpenAIEmbeddingProvider",
    "BGEProvider",
    "CloudEmbeddingProvider",
    "CohereEmbeddingProvider",
    "E5Provider",
    "EmbeddingCache",
    "EmbeddingError",
    "EmbeddingFeatureProvider",
    "EmbeddingManager",
    "EmbeddingMeta",
    "EmbeddingNotAvailableError",
    "EmbeddingNotLoadedError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingTrace",
    "FeatureMode",
    "HashEmbeddingProvider",
    "MiniLMProvider",
    "ModeComparisonReport",
    "ModeComparisonRunner",
    "ModeDetectionBenchmark",
    "ModeFeatureExtractor",
    "ModeHybridEvaluator",
    "ModeQuantumAdapter",
    "ModeTrainingAdapter",
    "OpenAIEmbeddingProvider",
    "SentenceTransformersProvider",
    "VoyageAIEmbeddingProvider",
    "build_manager",
]
