"""Hugging Face dataset loader (optional)."""

from __future__ import annotations

from typing import Any

from q_guardian.ml.data import DatasetEntry
from q_guardian.ml.datasets.base import DatasetLoader
from q_guardian.security.enums import PromptCategory, PromptSeverity


class HuggingFaceLoader(DatasetLoader):
    """Load datasets from Hugging Face Hub.

    Requires the `datasets` library (optional dependency).
    Install with: pip install q-guardian[datasets]

    Example usage::

        loader = HuggingFaceLoader()
        entries = await loader.load(
            "security-ai/prompt-injection",
            split="train",
            prompt_column="text",
            label_column="label",
        )
    """

    def __init__(self) -> None:
        self._available = False
        try:
            import datasets  # noqa: F401

            self._available = True
        except ImportError:
            pass

    @property
    def name(self) -> str:
        return "huggingface-loader"

    @property
    def is_available(self) -> bool:
        return self._available

    async def load(self, source: str, **kwargs: Any) -> list[DatasetEntry]:
        """Load a Hugging Face dataset.

        Args:
            source: Dataset identifier on HF Hub.
            **kwargs: Options:
                - split (str): Dataset split (default: 'train')
                - prompt_column (str): Column name for prompts (default: 'text')
                - label_column (str): Column name for labels (default: 'label')
                - max_samples (int): Max samples to load (default: all)
                - streaming (bool): Stream instead of download (default: False)

        Returns:
            List of DatasetEntry objects.
        """
        if not self._available:
            msg = (
                "Hugging Face 'datasets' library is not installed. Install with: "
                "pip install q-guardian[datasets]"
            )
            raise ImportError(msg)

        from datasets import load_dataset

        split = kwargs.get("split", "train")
        prompt_column = kwargs.get("prompt_column", "text")
        label_column = kwargs.get("label_column", "label")
        max_samples = kwargs.get("max_samples")
        streaming = kwargs.get("streaming", False)

        dataset = load_dataset(source, split=split, streaming=streaming)

        if max_samples:
            dataset = dataset.select(range(min(max_samples, len(dataset))))

        entries: list[DatasetEntry] = []
        for row in dataset:
            label_str = str(row.get(label_column, "unknown"))
            try:
                label = PromptCategory(label_str)
            except ValueError:
                label = PromptCategory.UNKNOWN

            entries.append(
                DatasetEntry(
                    prompt=str(row.get(prompt_column, "")),
                    label=label,
                    severity=PromptSeverity.LOW,
                    is_malicious=label != PromptCategory.UNKNOWN,
                    metadata={"source": source, "split": split},
                )
            )

        return entries
