"""Unified preprocessing: raw benchmark rows -> canonical dataset schema.

Heterogeneous benchmark schemas (explicit label columns, split-derived
labels, string label maps, category tags) are mapped onto the canonical
``q_guardian.evaluation.dataset`` schema (``BenchmarkSample`` /
``PromptBenchmarkDataset``) that ``HybridEvaluator`` / ``DetectionBenchmark``
consume. Text is kept verbatim so raw attack strings stay inspectable; the
pipeline's ``PromptNormalizer`` + ``PromptFeatureExtractor`` apply at
feature-extraction time inside ``q_guardian.evaluation``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from q_guardian.benchmark.registry import DatasetSpec

from q_guardian.evaluation.dataset import BenchmarkSample, PromptBenchmarkDataset


def extract_text(spec: DatasetSpec, row: dict[str, Any]) -> str:
    """Return the first non-empty value of ``spec.text_fields``."""
    for field in spec.text_fields:
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def resolve_label(spec: DatasetSpec, row: dict[str, Any], split: str) -> int | None:
    """Resolve a row's binary label (0/1) or ``None`` when it is ambiguous."""
    if spec.label_field is not None and spec.label_field in row:
        value: Any = row[spec.label_field]
        if spec.label_map is not None and value in spec.label_map:
            return spec.label_map[value]
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        if parsed in (0, 1):
            return parsed
        return None
    if spec.label_from_split is not None and split in spec.label_from_split:
        return spec.label_from_split[split]
    if spec.default_label is not None:
        return spec.default_label
    return None


def extract_category(spec: DatasetSpec, row: dict[str, Any]) -> str:
    """Return the category tag (defaulting to ``default_category``)."""
    if spec.category_field is not None:
        value: Any = row.get(spec.category_field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return spec.default_category


class DatasetPreprocessor:
    """Converts downloaded dataset splits into a ``PromptBenchmarkDataset``."""

    def preprocess(
        self,
        spec: DatasetSpec,
        split_paths: Mapping[str, Path],
    ) -> PromptBenchmarkDataset:
        """Map every row across all splits into the canonical schema.

        Rows that are not JSON objects, lack a text field, or have an
        unresolvable label are skipped (the validator reports them).

        Raises:
            ValueError: If no valid sample could be extracted.
        """
        samples: list[BenchmarkSample] = []
        for split, path in split_paths.items():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw: Any = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(raw, dict):
                        continue
                    text = extract_text(spec, raw)
                    label = resolve_label(spec, raw, split)
                    if not text or label is None:
                        continue
                    samples.append(
                        BenchmarkSample(
                            text=text,
                            label=label,
                            category=extract_category(spec, raw),
                        )
                    )
        if not samples:
            msg = f"no valid samples could be extracted from dataset {spec.dataset_id}"
            raise ValueError(msg)
        return PromptBenchmarkDataset(samples)
