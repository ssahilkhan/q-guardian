"""Feature fusion: handcrafted features + semantic embeddings.

The handcrafted 43-feature pipeline (``MLFeatureProvider``) remains the
default and is never modified. This module *extends* it with embeddings and
selects between three modes:

- ``HANDCRAFTED_ONLY`` — identical output to the existing pipeline.
- ``EMBEDDING_ONLY`` — semantic embedding vectors only.
- ``HYBRID`` — handcrafted features concatenated with embedding vectors.

The public surface stays backward compatible: ``ModeFeatureExtractor``
wraps the existing ``MLFeatureProvider``/``PromptFeatureExtractor``, and
``EmbeddingFeatureProvider`` implements the same ``FeatureProvider``
interface, so it can be injected anywhere the handcrafted provider is used.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from q_guardian.embeddings.manager import EmbeddingManager
from q_guardian.evaluation.pipeline import HybridEvaluator
from q_guardian.ml.feature_pipeline import MLFeatureProvider
from q_guardian.security.extensibility import FeatureProvider
from q_guardian.security.pipeline import PromptFeatureExtractor, PromptNormalizer

if TYPE_CHECKING:
    from q_guardian.security.models import PromptFeatures


class FeatureMode(StrEnum):
    """Feature pipeline selection for the embedding-extended pipeline."""

    HANDCRAFTED_ONLY = "handcrafted"
    EMBEDDING_ONLY = "embedding"
    HYBRID = "hybrid"


class ModeFeatureExtractor:
    """Produces mode-specific feature vectors from raw prompt text.

    Wraps (does not modify) the existing handcrafted pipeline
    (``PromptNormalizer`` + ``PromptFeatureExtractor`` +
    ``MLFeatureProvider``) and an :class:`EmbeddingManager`. The manager is
    injectable, so tests and callers can supply any provider.

    Args:
        mode: Default :class:`FeatureMode` used when no per-call mode is
            given.
        manager: Embedding manager (defaults to one with the offline hash
            provider).
        normalizer: Prompt normalizer (defaults to the real one).
        feature_extractor: Handcrafted feature extractor (defaults to the
            real one).
        ml_features: Handcrafted feature provider (defaults to the real
            one).
    """

    def __init__(
        self,
        *,
        mode: FeatureMode | str = FeatureMode.HYBRID,
        manager: EmbeddingManager | None = None,
        normalizer: PromptNormalizer | None = None,
        feature_extractor: PromptFeatureExtractor | None = None,
        ml_features: MLFeatureProvider | None = None,
    ) -> None:
        self.mode = FeatureMode(mode)
        self.manager = manager if manager is not None else EmbeddingManager.default()
        self._normalizer = normalizer if normalizer is not None else PromptNormalizer()
        self._feature_extractor = (
            feature_extractor if feature_extractor is not None else PromptFeatureExtractor()
        )
        self._ml_features = ml_features if ml_features is not None else MLFeatureProvider()

    # ── Handcrafted path (byte-identical to the existing pipeline) ─────

    def handcrafted_vector(self, text: str) -> list[float]:
        """Extract the classic 43-feature vector for a prompt."""
        normalized = self._normalizer.normalize(text)
        base = self._feature_extractor.extract(normalized)
        return self._ml_features.extract_vector(normalized, base).features

    @property
    def handcrafted_names(self) -> list[str]:
        return self._ml_features.feature_names

    # ── Embedding path ─────────────────────────────────────────────────

    def embedding_vector(self, text: str) -> list[float]:
        """Embed a prompt through the manager's default provider."""
        return self.manager.embed(text)

    @property
    def embedding_dim(self) -> int:
        return self.manager.dimension()

    # ── Mode-aware vector / names ──────────────────────────────────────

    def vector(self, text: str, mode: FeatureMode | str | None = None) -> list[float]:
        """Return the feature vector for the effective mode."""
        effective = self._coerce(mode)
        if effective is FeatureMode.HANDCRAFTED_ONLY:
            return self.handcrafted_vector(text)
        if effective is FeatureMode.EMBEDDING_ONLY:
            return self.embedding_vector(text)
        return self.handcrafted_vector(text) + self.embedding_vector(text)

    def vectors(
        self,
        texts: list[str],
        mode: FeatureMode | str | None = None,
    ) -> list[list[float]]:
        return [self.vector(text, mode) for text in texts]

    def feature_names(self, mode: FeatureMode | str | None = None) -> list[str]:
        """Ordered feature names for the effective mode."""
        effective = self._coerce(mode)
        if effective is FeatureMode.EMBEDDING_ONLY:
            return [f"emb_{i}" for i in range(self.embedding_dim)]
        handcrafted = self.handcrafted_names
        if effective is FeatureMode.HANDCRAFTED_ONLY:
            return handcrafted
        return handcrafted + [f"emb_{i}" for i in range(self.embedding_dim)]

    def embedding_metadata(self) -> dict[str, Any]:
        """Provider metadata of the active embedding manager."""
        provider = self.manager.default_provider
        if provider is None:
            return {}
        return provider.metadata()

    def _coerce(self, mode: FeatureMode | str | None) -> FeatureMode:
        return self.mode if mode is None else FeatureMode(mode)


class EmbeddingFeatureProvider(FeatureProvider):
    """FeatureProvider-compatible wrapper for embedding-extended features.

    Implements the same interface as ``MLFeatureProvider`` so it can be
    injected wherever the handcrafted provider is used. In
    ``HANDCRAFTED_ONLY`` mode its output is identical to the wrapped
    handcrafted provider.

    Args:
        mode: Feature mode.
        manager: Embedding manager (defaults to the offline hash provider).
        ml_provider: Handcrafted provider to delegate to (defaults to a
            fresh ``MLFeatureProvider``).
    """

    def __init__(
        self,
        *,
        mode: FeatureMode | str = FeatureMode.HYBRID,
        manager: EmbeddingManager | None = None,
        ml_provider: MLFeatureProvider | None = None,
    ) -> None:
        self._mode = FeatureMode(mode)
        self._manager = manager if manager is not None else EmbeddingManager.default()
        self._ml_provider = ml_provider if ml_provider is not None else MLFeatureProvider()

    @property
    def name(self) -> str:
        return "embedding-feature-provider"

    @property
    def mode(self) -> FeatureMode:
        return self._mode

    @property
    def embedding_manager(self) -> EmbeddingManager:
        return self._manager

    async def extract_features(
        self,
        prompt: str,
        base_features: PromptFeatures,
    ) -> dict[str, Any]:
        """Extract mode-aware features (handcrafted + optional embedding).

        Returns the same keys as ``MLFeatureProvider`` plus ``embedding``
        and ``embedding_meta`` in embedding modes.
        """
        handcrafted = await self._ml_provider.extract_features(prompt, base_features)
        if self._mode is FeatureMode.HANDCRAFTED_ONLY:
            return handcrafted

        vector, meta = self._manager.embed_with_meta(prompt)
        features = dict(handcrafted)
        features["embedding"] = vector
        features["embedding_meta"] = dataclasses.replace(meta, mode=self._mode.value).to_dict()
        if self._mode is FeatureMode.EMBEDDING_ONLY:
            names = [f"emb_{i}" for i in range(len(vector))]
        else:
            names = handcrafted["feature_names"] + [f"emb_{i}" for i in range(len(vector))]
        features["feature_vector"] = (
            vector
            if self._mode is FeatureMode.EMBEDDING_ONLY
            else (handcrafted["feature_vector"] + vector)
        )
        features["feature_names"] = names
        return features


class ModeHybridEvaluator(HybridEvaluator):
    """HybridEvaluator that feeds mode-specific features into the pipeline.

    Subclasses the existing evaluator without modifying it. In
    ``HANDCRAFTED_ONLY`` mode :meth:`vector` delegates to the base
    implementation, so results are identical to the classic pipeline.
    """

    def __init__(
        self,
        *,
        mode: FeatureMode | str = FeatureMode.HYBRID,
        mode_extractor: ModeFeatureExtractor | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.mode = FeatureMode(mode)
        self.mode_extractor = (
            mode_extractor if mode_extractor is not None else ModeFeatureExtractor(mode=self.mode)
        )

    def vector(self, text: str) -> list[float]:
        effective = self.mode
        if effective is FeatureMode.HANDCRAFTED_ONLY:
            return super().vector(text)
        embedding = self.mode_extractor.embedding_vector(text)
        if effective is FeatureMode.EMBEDDING_ONLY:
            return embedding
        return super().vector(text) + embedding
