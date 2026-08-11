"""Unit tests for run-artifact helpers (JSON, splits, label distributions)."""

from __future__ import annotations

import json

from q_guardian.training.artifacts import (
    label_distribution,
    read_splits,
    write_json,
    write_splits,
)
from q_guardian.training.schema import DatasetRecord


def _record(text: str, *, label: int = 1, category: str = "jailbreak") -> DatasetRecord:
    return DatasetRecord(text=text, label=label, source="local", category=category)


class TestWriteJson:
    def test_writes_pretty_json_with_parents(self, tmp_path) -> None:
        target = tmp_path / "nested" / "out.json"
        write_json(target, {"a": [1, 2]})

        assert json.loads(target.read_text(encoding="utf-8")) == {"a": [1, 2]}


class TestLabelDistribution:
    def test_counts_labels_and_categories(self) -> None:
        records = [
            _record("a", label=0, category="benign"),
            _record("b", label=1, category="jailbreak"),
            _record("c", label=1, category="jailbreak"),
        ]
        dist = label_distribution(records)

        assert dist["total"] == 3
        assert dist["labels"] == {"benign": 1, "malicious": 2}
        assert dist["categories"] == {"benign": 1, "jailbreak": 2}


class TestSplits:
    def test_write_and_read_round_trip(self, tmp_path) -> None:
        pools = {
            "train": [_record("a", label=0), _record("b", label=1)],
            "validation": [],
            "test": [_record("c", label=1, category="jailbreak")],
            "external_eval": [_record("d", label=1)],
        }
        write_splits(tmp_path, pools)
        loaded = read_splits(tmp_path)

        assert [r.text for r in loaded["train"]] == ["a", "b"]
        assert loaded["validation"] == []
        assert loaded["test"][0].category == "jailbreak"
        assert [r.text for r in loaded["external_eval"]] == ["d"]

    def test_read_splits_skips_missing(self, tmp_path) -> None:
        write_splits(tmp_path, {"train": [_record("a")]})
        loaded = read_splits(tmp_path)

        assert "train" in loaded
        assert "validation" not in loaded
