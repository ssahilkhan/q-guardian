"""CSV dataset loader."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from q_guardian.ml.data import DatasetEntry
from q_guardian.ml.datasets.base import DatasetLoader
from q_guardian.security.enums import PromptCategory, PromptSeverity


class CSVLoader(DatasetLoader):
    """Load datasets from CSV files.

    Expected CSV columns:
    - prompt (required): The prompt text
    - label (required): The threat category label
    - severity (optional): Severity level
    - is_malicious (optional): Boolean flag
    """

    @property
    def name(self) -> str:
        return "csv-loader"

    async def load(self, source: str, **kwargs: Any) -> list[DatasetEntry]:
        """Load a CSV dataset.

        Args:
            source: Path to the CSV file.
            **kwargs: Options:
                - delimiter (str): CSV delimiter (default: ',')
                - encoding (str): File encoding (default: 'utf-8')

        Returns:
            List of DatasetEntry objects.
        """
        path = Path(source)
        if not path.exists():
            msg = f"CSV file not found: {source}"
            raise FileNotFoundError(msg)

        delimiter = kwargs.get("delimiter", ",")
        encoding = kwargs.get("encoding", "utf-8")

        entries: list[DatasetEntry] = []
        with open(path, encoding=encoding, newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
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

                is_malicious_str = row.get("is_malicious", "false")
                is_malicious = is_malicious_str.lower() in ("true", "1", "yes")

                entries.append(
                    DatasetEntry(
                        prompt=row.get("prompt", ""),
                        label=label,
                        severity=severity,
                        is_malicious=is_malicious,
                        metadata={"source": source},
                    )
                )

        return entries
