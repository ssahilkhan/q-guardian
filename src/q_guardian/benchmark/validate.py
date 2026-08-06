"""Dataset validation: schema and quality checks on downloaded rows.

Validation is intentionally non-destructive: every problem found is
collected into a ``DatasetValidation`` report instead of raising, so a
partially broken download is visible (and auditable) rather than silent.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from q_guardian.benchmark.registry import DatasetSpec

from q_guardian.benchmark.preprocessing import (
    extract_category,
    extract_text,
    resolve_label,
)


@dataclass
class DatasetValidation:
    """Quality report for a downloaded dataset."""

    dataset_id: str
    total: int
    valid_rows: int
    labels: dict[str, int]
    categories: dict[str, int]
    splits: dict[str, int]
    issues: list[str]

    @property
    def valid(self) -> bool:
        """True when every row resolved to text + label with no issues."""
        return self.total == self.valid_rows and not self.issues

    def as_dict(self) -> dict[str, Any]:
        """Serialize the validation report."""
        return {**asdict(self), "valid": self.valid}


class DatasetValidator:
    """Validates downloaded JSONL splits against a ``DatasetSpec``.

    Each row must be a JSON object with at least one non-empty text field
    and a resolvable binary label (explicit label column, split-derived
    label, or ``default_label``). Problems are collected as issues.
    """

    def validate(
        self,
        spec: DatasetSpec,
        split_paths: Mapping[str, Path],
    ) -> DatasetValidation:
        total = 0
        valid_rows = 0
        labels: dict[str, int] = {}
        categories: dict[str, int] = {}
        splits: dict[str, int] = {}
        issues: list[str] = []

        for split, path in split_paths.items():
            split_count = 0
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw: Any = json.loads(line)
                    except json.JSONDecodeError:
                        issues.append(f"{spec.dataset_id}/{split}: invalid JSON row")
                        continue
                    if not isinstance(raw, dict):
                        issues.append(f"{spec.dataset_id}/{split}: non-object row")
                        continue

                    split_count += 1
                    text = extract_text(spec, raw)
                    label = resolve_label(spec, raw, split)
                    if not text:
                        issues.append(f"{spec.dataset_id}/{split}: missing text")
                        continue
                    if label is None:
                        issues.append(f"{spec.dataset_id}/{split}: unresolvable label")
                        continue

                    total += 1
                    valid_rows += 1
                    labels[str(label)] = labels.get(str(label), 0) + 1
                    category = extract_category(spec, raw)
                    categories[category] = categories.get(category, 0) + 1
            splits[split] = split_count

        return DatasetValidation(
            dataset_id=spec.dataset_id,
            total=total,
            valid_rows=valid_rows,
            labels=labels,
            categories=categories,
            splits=splits,
            issues=issues,
        )
