"""JSON dataset loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from q_guardian.ml.datasets.base import DatasetLoader
from q_guardian.ml.data import DatasetEntry
from q_guardian.security.enums import PromptCategory, PromptSeverity


class JSONLoader(DatasetLoader):
    """Load datasets from JSON or JSONL files.

    Supports two formats:
    - JSON array: [{"prompt": "...", "label": "..."}, ...]
    - JSONL: one JSON object per line
    """

    @property
    def name(self) -> str:
        return "json-loader"

    async def load(self, source: str, **kwargs: Any) -> list[DatasetEntry]:
        """Load a JSON dataset.

        Args:
            source: Path to the JSON or JSONL file.
            **kwargs: Options:
                - format (str): 'json' or 'jsonl' (auto-detected if not specified)
                - encoding (str): File encoding (default: 'utf-8')

        Returns:
            List of DatasetEntry objects.
        """
        path = Path(source)
        if not path.exists():
            msg = f"JSON file not found: {source}"
            raise FileNotFoundError(msg)

        encoding = kwargs.get("encoding", "utf-8")
        fmt = kwargs.get("format", "")

        if not fmt:
            fmt = "jsonl" if path.suffix == ".jsonl" else "json"

        with open(path, "r", encoding=encoding) as f:
            if fmt == "jsonl":
                data = [json.loads(line) for line in f if line.strip()]
            else:
                data = json.load(f)
                if isinstance(data, dict):
                    data = data.get("data", data.get("entries", [data]))

        entries: list[DatasetEntry] = []
        for row in data:
            if not isinstance(row, dict):
                continue

            label_str = row.get("label", "unknown")
            try:
                label = PromptCategory(label_str)
            except ValueError:
                label = PromptCategory.UNKNOWN

            severity_str = row.get("severity", "low")
            try:
                severity = PromptSeverity(severity_str)
            except ValueError:
                severity = PromptSeverity.LOW

            is_malicious = bool(row.get("is_malicious", False))

            entries.append(DatasetEntry(
                prompt=row.get("prompt", ""),
                label=label,
                severity=severity,
                is_malicious=is_malicious,
                metadata={"source": source},
            ))

        return entries
