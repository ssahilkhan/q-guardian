"""Hugging Face dataset loader (optional)."""

from __future__ import annotations

import os
from typing import Any

from q_guardian.ml.data import DatasetEntry
from q_guardian.ml.datasets.base import DatasetLoader
from q_guardian.security.enums import PromptCategory, PromptSeverity


class HuggingFaceLoader(DatasetLoader):
    """Load datasets from Hugging Face Hub with optional authentication.

    Requires the `datasets` library (optional dependency).
    Install with: pip install q-guardian[datasets]

    Supports authentication via:
    - Explicit token parameter
    - HF_TOKEN environment variable
    - Hugging Face CLI cached credentials (huggingface_hub library)

    Example usage::

        loader = HuggingFaceLoader()
        entries = await loader.load(
            "security-ai/prompt-injection",
            split="train",
            prompt_column="text",
            label_column="label",
        )

        # With explicit token for gated datasets:
        loader = HuggingFaceLoader(token="hf_...")
        entries = await loader.load("org/gated-dataset", split="train")
    """

    def __init__(self, token: str | None = None) -> None:
        """Initialize the loader.

        Args:
            token: Optional Hugging Face token. If not provided, checks
                HF_TOKEN environment variable, then falls back to
                huggingface_hub cached credentials.
        """
        self._available = False
        self._token = token or os.environ.get("HF_TOKEN")
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

    @property
    def token(self) -> str | None:
        """Return the current token (never logged)."""
        return self._token

    @property
    def has_token(self) -> bool:
        """Check if a token is configured."""
        return self._token is not None

    async def load(self, source: str, **kwargs: Any) -> list[DatasetEntry]:
        """Load a Hugging Face dataset with optional authentication.

        Args:
            source: Dataset identifier on HF Hub.
            **kwargs: Options:
                - split (str): Dataset split (default: 'train')
                - prompt_column (str): Column name for prompts (default: 'text')
                - label_column (str): Column name for labels (default: 'label')
                - max_samples (int): Max samples to load (default: all)
                - streaming (bool): Stream instead of download (default: False)
                - token (str): Override token for this specific load
                - config (str): Dataset configuration name

        Returns:
            List of DatasetEntry objects.

        Raises:
            ImportError: If datasets library is not installed.
            ValueError: If dataset is gated and no valid token is available.
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
        config = kwargs.get("config")
        token = kwargs.get("token", self._token)

        try:
            dataset = load_dataset(
                source,
                split=split,
                streaming=streaming,
                token=token,
                config=config,
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "gated" in msg or "401" in msg or "403" in msg or "authentication" in msg:
                raise ValueError(
                    f"Dataset '{source}' is gated or requires authentication. "
                    f"Provide a valid HF_TOKEN after accepting the dataset terms "
                    f"on Hugging Face Hub."
                ) from exc
            raise

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

    async def check_access(self, source: str, **kwargs: Any) -> dict[str, Any]:
        """Check if a dataset is accessible without loading all data.

        Args:
            source: Dataset identifier on HF Hub.
            **kwargs: Options passed to load_dataset (config, split, etc.)

        Returns:
            Dictionary with access information:
            - accessible: bool
            - requires_auth: bool
            - error: str | None
        """
        if not self._available:
            return {
                "accessible": False,
                "requires_auth": False,
                "error": "datasets library not installed",
            }

        from datasets import load_dataset

        token = kwargs.get("token", self._token)

        try:
            # Try to load just the first row to verify access
            load_dataset(
                source,
                split=kwargs.get("split", "train"),
                streaming=True,
                token=token,
                config=kwargs.get("config"),
            )
            return {"accessible": True, "requires_auth": token is not None, "error": None}
        except Exception as exc:
            msg = str(exc).lower()
            if "gated" in msg or "401" in msg or "403" in msg:
                return {
                    "accessible": False,
                    "requires_auth": True,
                    "error": (
                        f"Dataset '{source}' is gated. "
                        f"Provide HF_TOKEN after accepting terms on Hugging Face Hub."
                    ),
                }
            return {
                "accessible": False,
                "requires_auth": False,
                "error": f"Failed to access dataset: {exc}",
            }
