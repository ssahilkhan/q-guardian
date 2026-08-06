"""Exception hierarchy for the embedding subsystem."""

from __future__ import annotations


class EmbeddingError(Exception):
    """Base error for the embedding subsystem."""


class EmbeddingNotLoadedError(EmbeddingError):
    """Raised when an operation requires a loaded provider/model."""


class EmbeddingNotAvailableError(EmbeddingError):
    """Raised when a backend cannot be used (missing library, credentials,
    or a not-yet-implemented cloud provider)."""


class EmbeddingProviderError(EmbeddingError):
    """Raised when a provider fails while producing an embedding."""
