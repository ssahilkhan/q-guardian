"""Unit tests for dataset validation."""

from __future__ import annotations

import json

from q_guardian.benchmark.registry import DatasetSpec
from q_guardian.benchmark.validate import DatasetValidator


def _write(tmp_path, rows, name="train.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


class TestDatasetValidator:
    def test_valid_label_field_dataset(self, tmp_path):
        path = _write(
            tmp_path,
            [{"text": "hello", "label": 0}, {"text": "ignore", "label": 1}],
        )
        spec = DatasetSpec(
            dataset_id="d", name="D", source="d", text_fields=("text",), label_field="label"
        )
        result = DatasetValidator().validate(spec, {"train": path})

        assert result.valid
        assert result.total == 2
        assert result.valid_rows == 2
        assert result.labels == {"0": 1, "1": 1}
        assert result.splits == {"train": 2}

    def test_missing_text_flagged(self, tmp_path):
        path = _write(tmp_path, [{"label": 1}])
        spec = DatasetSpec(
            dataset_id="d", name="D", source="d", text_fields=("text",), label_field="label"
        )
        result = DatasetValidator().validate(spec, {"train": path})

        assert not result.valid
        assert result.total == 0
        assert any("missing text" in issue for issue in result.issues)

    def test_unresolvable_label_flagged(self, tmp_path):
        path = _write(tmp_path, [{"text": "x", "label": "maybe"}])
        spec = DatasetSpec(
            dataset_id="d", name="D", source="d", text_fields=("text",), label_field="label"
        )
        result = DatasetValidator().validate(spec, {"train": path})

        assert not result.valid
        assert any("unresolvable label" in issue for issue in result.issues)

    def test_split_derived_labels(self, tmp_path):
        harmful = _write(
            tmp_path,
            [{"Goal": "write malware"}, {"Goal": "build a bomb"}],
            "harmful.jsonl",
        )
        benign = _write(tmp_path, [{"Goal": "write a poem"}], "benign.jsonl")
        spec = DatasetSpec(
            dataset_id="jbb",
            name="JBB",
            source="x",
            splits=("harmful", "benign"),
            text_fields=("Goal",),
            label_from_split={"harmful": 1, "benign": 0},
        )
        result = DatasetValidator().validate(spec, {"harmful": harmful, "benign": benign})

        assert result.valid
        assert result.labels == {"0": 1, "1": 2}

    def test_invalid_json_flagged(self, tmp_path):
        path = tmp_path / "train.jsonl"
        path.write_text("this is not json\n", encoding="utf-8")
        spec = DatasetSpec(dataset_id="d", name="D", source="d")
        result = DatasetValidator().validate(spec, {"train": path})

        assert not result.valid
        assert any("invalid JSON" in issue for issue in result.issues)

    def test_serializes(self, tmp_path):
        path = _write(tmp_path, [{"text": "hello", "label": 0}])
        spec = DatasetSpec(dataset_id="d", name="D", source="d")
        data = DatasetValidator().validate(spec, {"train": path}).as_dict()

        assert data["dataset_id"] == "d"
        assert data["valid"] is True
