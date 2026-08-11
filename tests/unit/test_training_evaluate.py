"""Unit tests for the evaluation pipeline (fake fitted evaluator)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from q_guardian.training.config import DatasetGroupConfig, TrainingPipelineConfig
from q_guardian.training.dedup import LeakageReport
from q_guardian.training.evaluate import EvaluationPipeline
from q_guardian.training.manifest import DatasetManifest
from q_guardian.training.prepare import PreparedDatasets
from q_guardian.training.schema import DatasetRecord

if TYPE_CHECKING:
    from pathlib import Path

if TYPE_CHECKING:
    from pathlib import Path


def _record(text: str, *, label: int = 1, source: str = "local-ds") -> DatasetRecord:
    category = "jailbreak" if label == 1 else "benign"
    return DatasetRecord(text=text, label=label, source=source, category=category)


class _FakeEvaluator:
    """Deterministic scorer: scores come from a text->score mapping."""

    def __init__(self, score_map: dict[str, float]) -> None:
        self._score_map = score_map
        self.calls: list[list[str]] = []

    def score_texts(self, texts: list[str]) -> list[float]:
        self.calls.append(list(texts))
        return [self._score_map[text] for text in texts]


def _config() -> TrainingPipelineConfig:
    return TrainingPipelineConfig(
        datasets=DatasetGroupConfig(
            train=["local-ds"],
            validation=["local-ds"],
            test=["local-ds"],
            external_eval=["ext-ds"],
        ),
        seed=1,
    )


def _records_with_scores() -> tuple[dict[str, list[DatasetRecord]], dict[str, float]]:
    benign = [
        _record("b1", label=0),
        _record("b2", label=0),
        _record("b3", label=0),
    ]
    malicious = [
        _record("m1", label=1),
        _record("m2", label=1),
        _record("m3", label=1),
    ]
    validation = [_record("vb", label=0), _record("vm", label=1)]
    external = [_record("e1", label=1, source="ext-ds"), _record("e2", label=1, source="ext-ds")]
    score_map = {
        r.text: (0.1 if r.label == 0 else 0.9)
        for r in [*benign, *malicious, *validation, *external]
    }
    return {
        "test": [*benign, *malicious],
        "validation": validation,
        "external_eval": external,
    }, score_map


def _prepared(config: TrainingPipelineConfig, output_dir: Path, pools) -> PreparedDatasets:
    manifest = DatasetManifest.build(
        config,
        {},
        {
            "train": [],
            "validation": pools["validation"],
            "test": pools["test"],
            "external_eval": pools["external_eval"],
        },
    )
    return PreparedDatasets(
        config=config,
        train=[],
        validation=pools["validation"],
        test=pools["test"],
        external_eval=pools["external_eval"],
        manifest=manifest,
        leakage_report=LeakageReport(train_count=0),
        output_dir=output_dir,
    )


class TestEvaluationPipeline:
    def test_evaluate_produces_matrix_and_summary(self, tmp_path) -> None:
        config = _config()
        pools, score_map = _records_with_scores()
        prepared = _prepared(config, tmp_path / "run", pools)
        evaluator = _FakeEvaluator(score_map)
        report = EvaluationPipeline(evaluator=evaluator).evaluate(config, prepared)

        datasets = [row["dataset"] for row in report.matrix]
        assert "test" in datasets
        assert "validation" in datasets
        assert "test:local-ds" in datasets
        assert "ext-ds" in datasets

        test_row = next(row for row in report.matrix if row["dataset"] == "test")
        assert test_row["samples"] == 6
        assert test_row["detection_rate"] == 1.0
        assert test_row["fpr"] == 0.0

        assert report.summary["internal_test_detection_rate"] == 1.0
        assert report.summary["external_datasets_evaluated"] == 1
        assert report.summary["mean_external_detection_rate"] == 1.0

    def test_threshold_analysis(self, tmp_path) -> None:
        config = _config()
        pools, score_map = _records_with_scores()
        prepared = _prepared(config, tmp_path / "run", pools)
        report = EvaluationPipeline(evaluator=_FakeEvaluator(score_map)).evaluate(config, prepared)

        assert len(report.threshold_analysis) == len(config.eval.threshold_sweep)
        assert report.summary["best_threshold_f1"] == 1.0

    def test_report_artifacts_written(self, tmp_path) -> None:
        config = _config()
        pools, score_map = _records_with_scores()
        prepared = _prepared(config, tmp_path / "run", pools)
        report = EvaluationPipeline(evaluator=_FakeEvaluator(score_map)).evaluate(config, prepared)

        assert (prepared.output_dir / "evaluation.json").exists()
        assert (prepared.output_dir / "evaluation.md").exists()
        markdown = (prepared.output_dir / "evaluation.md").read_text(encoding="utf-8")
        assert "Q-Guardian Evaluation Report" in markdown
        assert "| test |" in markdown

        data = report.as_dict()
        assert data["config"]["seed"] == config.seed
        assert data["summary"]["datasets_evaluated"] >= 4

    def test_unavailable_external_dataset_appears_in_matrix(self, tmp_path) -> None:
        config = _config()
        config.datasets.external_eval = ["ext-ds", "gated-missing"]
        pools, score_map = _records_with_scores()
        prepared = _prepared(config, tmp_path / "run", pools)
        report = EvaluationPipeline(evaluator=_FakeEvaluator(score_map)).evaluate(config, prepared)

        missing = next(row for row in report.matrix if row["dataset"] == "gated-missing")
        assert missing["available"] is False
        assert missing["samples"] == 0

    def test_empty_test_skips_threshold_analysis(self, tmp_path) -> None:
        config = _config()
        pools, score_map = _records_with_scores()
        pools["test"] = []
        prepared = _prepared(config, tmp_path / "run", pools)
        report = EvaluationPipeline(evaluator=_FakeEvaluator(score_map)).evaluate(config, prepared)

        test_row = next(row for row in report.matrix if row["dataset"] == "test")
        assert test_row["note"] == "no valid samples"
        assert report.threshold_analysis == []

    def test_no_evaluator_and_no_checkpoint_raises(self, tmp_path) -> None:
        config = _config()
        pools, _ = _records_with_scores()
        prepared = _prepared(config, tmp_path / "run", pools)

        with pytest.raises(RuntimeError, match="no fitted evaluator"):
            EvaluationPipeline().evaluate(config, prepared)

    def test_per_category_rows(self, tmp_path) -> None:
        config = _config()
        pools, score_map = _records_with_scores()
        prepared = _prepared(config, tmp_path / "run", pools)
        report = EvaluationPipeline(evaluator=_FakeEvaluator(score_map)).evaluate(config, prepared)

        categories = {row["category"] for row in report.per_category}
        assert "jailbreak" in categories
        assert "benign" in categories
