"""Normalization of raw dataset rows into the canonical ``DatasetRecord``.

This is the schema-normalization layer. It reuses the column-mapping rules
already defined in ``q_guardian.benchmark`` (``DatasetSpec`` +
``extract_text``/``resolve_label``/``extract_category``) so that every dataset
in the registry is mapped by one code path, and emits the richer canonical
record that also carries ``source``, ``split`` and the raw row as metadata.

Label mapping decisions:

* Canonical label space is ``0 = benign``, ``1 = malicious``.
* ``resolve_label`` (benchmark.preprocessing) applies, in order:
  explicit ``label_field`` (through ``label_map``), then
  ``label_from_split``, then ``default_label``.
* When a malicious row has no explicit category column, it is tagged with
  the generic fallback ``malicious`` (never mislabeled as ``benign``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from q_guardian.benchmark.preprocessing import (
    extract_category,
    extract_text,
    resolve_label,
)
from q_guardian.training.schema import (
    DEFAULT_CATEGORY,
    GENERIC_MALICIOUS_CATEGORY,
    DatasetRecord,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from q_guardian.benchmark.registry import DatasetSpec


class DatasetRecordPreprocessor:
    """Maps downloaded raw splits onto canonical ``DatasetRecord`` instances.

    Rows that are not JSON objects, have no text, or have an unresolvable
    label are skipped (and counted, so ``filtered`` is visible in the
    manifest rather than silent).
    """

    def preprocess(
        self,
        spec: DatasetSpec,
        split_paths: Mapping[str, Path],
    ) -> tuple[list[DatasetRecord], int]:
        """Normalize every row across all splits.

        Returns:
            A tuple of ``(records, filtered)`` where ``filtered`` is the
            number of raw rows that were dropped (invalid JSON, non-object,
            missing text, or unresolvable label).
        """
        records: list[DatasetRecord] = []
        filtered = 0
        for split, path in split_paths.items():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw: Any = json.loads(line)
                    except json.JSONDecodeError:
                        filtered += 1
                        continue
                    if not isinstance(raw, dict):
                        filtered += 1
                        continue
                    text = extract_text(spec, raw)
                    label = resolve_label(spec, raw, split)
                    if not text or label is None:
                        filtered += 1
                        continue
                    category = extract_category(spec, raw)
                    if label == 1 and category == DEFAULT_CATEGORY:
                        category = GENERIC_MALICIOUS_CATEGORY
                    records.append(
                        DatasetRecord(
                            text=text,
                            label=label,
                            source=spec.dataset_id,
                            split=split,
                            category=category,
                            metadata={"raw": raw},
                        )
                    )
        return records, filtered


def count_raw_rows(split_paths: Mapping[str, Path]) -> int:
    """Count non-empty JSON lines across downloaded split files."""
    total = 0
    for path in split_paths.values():
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    total += 1
    return total
