"""Dataset abstractions for training ML models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from q_guardian.ml.data import DatasetEntry


class DatasetLoader(ABC):
    """Abstract base class for dataset loading.

    Supports multiple formats: CSV, JSON, Hugging Face datasets.
    All loaders produce DatasetEntry objects for training pipelines.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the loader name."""

    @abstractmethod
    async def load(self, source: str, **kwargs: Any) -> list[DatasetEntry]:
        """Load a dataset from a source.

        Args:
            source: Path, URL, or dataset identifier.
            **kwargs: Format-specific options.

        Returns:
            List of DatasetEntry objects.
        """

    async def load_split(
        self, source: str, split: str = "train", **kwargs: Any
    ) -> list[DatasetEntry]:
        """Load a specific split from a dataset.

        Args:
            source: Path, URL, or dataset identifier.
            split: Dataset split name (train, test, validation).
            **kwargs: Format-specific options.

        Returns:
            List of DatasetEntry objects.
        """
        return await self.load(source, split=split, **kwargs)
