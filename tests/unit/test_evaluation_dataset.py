"""Unit tests for the benchmark dataset."""

from __future__ import annotations

import pytest

from q_guardian.evaluation.dataset import BenchmarkSample, PromptBenchmarkDataset


class TestDatasetConstruction:
    def test_builtin_balance(self):
        d = PromptBenchmarkDataset.builtin()
        assert len(d) >= 40
        assert d.positives() > 0
        assert d.negatives() > 0
        stats = d.describe()
        assert stats["total"] == len(d)
        assert stats["threats"] == d.positives()
        assert stats["benign"] == d.negatives()
        # Every attack category in the taxonomy is represented.
        for cat in [
            "prompt_injection",
            "jailbreak",
            "role_manipulation",
            "system_prompt_leak",
            "data_exfiltration",
            "excessive_encoding",
            "suspicious_formatting",
        ]:
            assert stats["categories"].get(cat, 0) > 0

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            PromptBenchmarkDataset([])

    def test_invalid_label_rejected(self):
        with pytest.raises(ValueError):
            PromptBenchmarkDataset([BenchmarkSample(text="x", label=2)])

    def test_empty_text_rejected(self):
        with pytest.raises(ValueError):
            PromptBenchmarkDataset([BenchmarkSample(text="", label=0)])


class TestSerialization:
    def test_jsonl_roundtrip(self, tmp_path):
        d = PromptBenchmarkDataset.builtin()
        path = tmp_path / "dataset.jsonl"
        d.to_jsonl(path)
        loaded = PromptBenchmarkDataset.from_jsonl(path)
        assert len(loaded) == len(d)
        assert loaded.texts() == d.texts()
        assert loaded.labels() == d.labels()
        assert loaded.categories() == d.categories()

    def test_from_jsonl_skips_blank_lines(self, tmp_path):
        path = tmp_path / "dataset.jsonl"
        path.write_text(
            '{"text": "a", "label": 0, "category": "benign"}\n\n'
            '{"text": "b", "label": 1, "category": "jailbreak"}\n',
            encoding="utf-8",
        )
        d = PromptBenchmarkDataset.from_jsonl(path)
        assert len(d) == 2
        assert d.labels() == [0, 1]


class TestSplits:
    def test_train_test_split_stratified(self):
        d = PromptBenchmarkDataset.builtin()
        train, test = d.train_test_split(test_ratio=0.3, seed=1)
        assert len(train) + len(test) == len(d)
        assert train.positives() > 0 and train.negatives() > 0
        assert test.positives() > 0 and test.negatives() > 0

    def test_train_test_split_deterministic(self):
        d = PromptBenchmarkDataset.builtin()
        a, b = d.train_test_split(test_ratio=0.3, seed=7)
        c, e = d.train_test_split(test_ratio=0.3, seed=7)
        assert a.texts() == c.texts()
        assert b.texts() == e.texts()

    def test_kfold_stratified(self):
        d = PromptBenchmarkDataset.builtin()
        folds = d.kfold(k=3, seed=1)
        assert len(folds) == 3
        seen: set[str] = set()
        for train, test in folds:
            assert len(train) + len(test) == len(d)
            assert train.positives() > 0 and train.negatives() > 0
            assert test.positives() > 0 and test.negatives() > 0
            for s in test:
                assert s.text not in seen
                seen.add(s.text)
        # Every sample appears in exactly one test fold.
        assert len(seen) == len(d)

    def test_kfold_invalid(self):
        d = PromptBenchmarkDataset.builtin()
        with pytest.raises(ValueError):
            d.kfold(k=1)
