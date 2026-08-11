"""Unit tests for deterministic, source-aware data splitting."""

from __future__ import annotations

from q_guardian.training.config import DatasetGroupConfig
from q_guardian.training.schema import DatasetRecord
from q_guardian.training.splitting import (
    assign_groups,
    cap_records,
    split_by_label,
    split_train_pool,
)


def _record(
    text: str, *, source: str = "src", split: str = "default", label: int = 1
) -> DatasetRecord:
    return DatasetRecord(text=text, label=label, source=source, split=split)


class TestSplitByLabel:
    def test_deterministic_across_calls(self) -> None:
        records = [_record(f"t{i}", label=i % 2) for i in range(20)]
        t1, v1 = split_by_label(records, 0.2, seed=7)
        t2, v2 = split_by_label(records, 0.2, seed=7)

        assert [r.text for r in t1] == [r.text for r in t2]
        assert [r.text for r in v1] == [r.text for r in v2]

    def test_preserves_label_balance(self) -> None:
        records = [_record(f"t{i}", label=i % 2) for i in range(40)]
        train, validation = split_by_label(records, 0.25, seed=3)

        train_positive = sum(1 for r in train if r.label == 1)
        valid_positive = sum(1 for r in validation if r.label == 1)
        assert train_positive > 0 and valid_positive > 0
        assert len(validation) == 10
        assert len(train) == 30

    def test_zero_ratio_keeps_all_in_train(self) -> None:
        records = [_record("a", label=0), _record("b", label=1)]
        train, validation = split_by_label(records, 0.0, seed=1)

        assert len(train) == 2
        assert validation == []


class TestAssignGroups:
    def _groups(self) -> DatasetGroupConfig:
        return DatasetGroupConfig(
            train=["deepset"],
            validation=["deepset"],
            test=["deepset"],
            external_eval=["external"],
        )

    def test_official_test_split_routed_to_test(self) -> None:
        groups = self._groups()
        records = [
            _record("train row", source="deepset", split="train"),
            _record("official test row", source="deepset", split="test"),
        ]
        pools = assign_groups(records, groups)

        assert pools["test"][0].text == "official test row"
        assert pools["train"][0].text == "train row"

    def test_unlisted_source_goes_to_external_eval(self) -> None:
        pools = assign_groups([_record("x", source="unlisted")], self._groups())

        assert pools["external_eval"][0].text == "x"
        assert pools["train"] == []

    def test_external_source_routed_to_external(self) -> None:
        pools = assign_groups([_record("x", source="external")], self._groups())

        assert pools["external_eval"][0].text == "x"

    def test_all_pools_present(self) -> None:
        pools = assign_groups([], self._groups())

        assert set(pools) == {"train", "validation", "test", "external_eval"}


class TestSplitTrainPool:
    def test_validation_source_stratified(self) -> None:
        records = [_record(f"t{i}", source="deepset", label=i % 2) for i in range(30)]
        train, validation = split_train_pool(records, ["deepset"], 0.2, seed=5)

        assert len(validation) == 6
        assert len(train) == 24

    def test_non_validation_source_keeps_all(self) -> None:
        records = [_record(f"t{i}", source="other") for i in range(10)]
        train, validation = split_train_pool(records, ["deepset"], 0.5, seed=5)

        assert len(train) == 10
        assert validation == []


class TestCapRecords:
    def test_no_cap_keeps_everything(self) -> None:
        records = [_record(f"t{i}") for i in range(10)]
        kept, removed = cap_records(records, None, seed=1)

        assert len(kept) == 10
        assert removed == 0

    def test_cap_preserves_both_labels(self) -> None:
        records = [_record(f"b{i}", label=0) for i in range(20)] + [
            _record(f"m{i}", label=1) for i in range(20)
        ]
        kept, removed = cap_records(records, 10, seed=4)

        assert len(kept) == 10
        assert removed == 30
        assert sum(1 for r in kept if r.label == 0) > 0
        assert sum(1 for r in kept if r.label == 1) > 0

    def test_cap_at_or_above_length_is_noop(self) -> None:
        records = [_record(f"t{i}") for i in range(5)]
        kept, removed = cap_records(records, 5, seed=1)

        assert len(kept) == 5
        assert removed == 0
