"""Unit tests for raw-row normalization onto canonical records."""

from __future__ import annotations

import json

from q_guardian.benchmark.registry import DatasetSpec
from q_guardian.training.normalize import DatasetRecordPreprocessor, count_raw_rows
from q_guardian.training.schema import GENERIC_MALICIOUS_CATEGORY


def _write_rows(path, rows: list[object]) -> None:
    lines = []
    for row in rows:
        if isinstance(row, str):
            lines.append(row)
        else:
            lines.append(json.dumps(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _spec() -> DatasetSpec:
    return DatasetSpec(
        dataset_id="local",
        name="Local",
        source="irrelevant",
        format="jsonl",
        splits=("default",),
        text_fields=("text", "prompt"),
        label_field="label",
        label_map={"malicious": 1, "benign": 0},
        category_field="category",
        default_category="benign",
    )


class TestDatasetRecordPreprocessor:
    def test_normalizes_valid_rows(self, tmp_path) -> None:
        split = tmp_path / "default.jsonl"
        _write_rows(
            split,
            [
                {"text": "Clean prompt", "label": "benign", "category": "benign"},
                {"text": "Inject this", "label": "malicious", "category": "jailbreak"},
            ],
        )
        records, filtered = DatasetRecordPreprocessor().preprocess(_spec(), {"default": split})

        assert filtered == 0
        assert len(records) == 2
        assert records[0].label == 0
        assert records[0].source == "local"
        assert records[1].category == "jailbreak"

    def test_filters_invalid_lines(self, tmp_path) -> None:
        split = tmp_path / "default.jsonl"
        _write_rows(
            split,
            [
                "not json",
                {"label": 1},
                {"text": "unknown label", "label": "weird"},
                {"text": "ok", "label": 0},
            ],
        )
        records, filtered = DatasetRecordPreprocessor().preprocess(_spec(), {"default": split})

        assert filtered == 3
        assert len(records) == 1
        assert records[0].text == "ok"

    def test_malicious_without_category_gets_fallback(self, tmp_path) -> None:
        split = tmp_path / "default.jsonl"
        _write_rows(split, [{"text": "Inject", "label": 1}])
        records, _ = DatasetRecordPreprocessor().preprocess(_spec(), {"default": split})

        assert records[0].category == GENERIC_MALICIOUS_CATEGORY

    def test_uses_fallback_text_field(self, tmp_path) -> None:
        spec = _spec()
        split = tmp_path / "default.jsonl"
        _write_rows(split, [{"prompt": "Prompt field", "label": 0}])
        records, _ = DatasetRecordPreprocessor().preprocess(spec, {"default": split})

        assert records[0].text == "Prompt field"

    def test_multiple_splits(self, tmp_path) -> None:
        train = tmp_path / "train.jsonl"
        test = tmp_path / "test.jsonl"
        _write_rows(train, [{"text": "t", "label": 0}])
        _write_rows(test, [{"text": "e", "label": 1}])
        records, _ = DatasetRecordPreprocessor().preprocess(_spec(), {"train": train, "test": test})

        assert [r.split for r in records] == ["train", "test"]


class TestCountRawRows:
    def test_counts_non_empty_lines(self, tmp_path) -> None:
        split = tmp_path / "default.jsonl"
        split.write_text("{}\n\n{}\n", encoding="utf-8")

        assert count_raw_rows({"default": split}) == 2
