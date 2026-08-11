"""Unit tests for the training pipeline configuration."""

from __future__ import annotations

import json

import pytest

from q_guardian.training.config import (
    DEFAULT_TRAIN_SOURCES,
    EvalConfig,
    ModelConfig,
    TrainingPipelineConfig,
)


class TestDatasetGroupConfig:
    def test_all_ids_deduplicates_and_preserves_order(self) -> None:
        config = TrainingPipelineConfig()
        ids = config.datasets.all_ids()

        assert ids[0] == "deepset-prompt-injections"
        assert len(ids) == len(set(ids))

    def test_default_groups_include_expected_sources(self) -> None:
        config = TrainingPipelineConfig()

        assert config.datasets.train == DEFAULT_TRAIN_SOURCES
        assert "jbb-behaviors" in config.datasets.external_eval
        assert "deepset-prompt-injections" in config.datasets.test


class TestTrainingPipelineConfig:
    def test_defaults(self) -> None:
        config = TrainingPipelineConfig()

        assert config.seed == 42
        assert config.validation_ratio == 0.2
        assert config.model.quantum is False
        assert config.eval.threshold == 0.5

    def test_negative_seed_rejected(self) -> None:
        with pytest.raises(ValueError):
            TrainingPipelineConfig(seed=-1)

    def test_validation_ratio_bounds(self) -> None:
        with pytest.raises(ValueError):
            TrainingPipelineConfig(validation_ratio=1.0)
        with pytest.raises(ValueError):
            TrainingPipelineConfig(validation_ratio=-0.1)

    def test_evaluator_kwargs_forward_model_and_seed(self) -> None:
        config = TrainingPipelineConfig(
            seed=7,
            model=ModelConfig(quantum=True, n_estimators=30, contamination=0.3),
        )
        kwargs = config.evaluator_kwargs()

        assert kwargs["quantum"] is True
        assert kwargs["n_estimators"] == 30
        assert kwargs["contamination"] == 0.3
        assert kwargs["random_state"] == 7
        assert "provider_weights" in kwargs

    def test_from_file_round_trip(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"seed": 99, "model": {"n_estimators": 10}}), encoding="utf-8")

        config = TrainingPipelineConfig.from_file(path)

        assert config.seed == 99
        assert config.model.n_estimators == 10

    def test_from_file_missing_raises(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            TrainingPipelineConfig.from_file(tmp_path / "missing.json")

    def test_as_dict_redacts_token(self) -> None:
        config = TrainingPipelineConfig(hf_token="super-secret")
        data = config.as_dict()

        assert data["hf_token"] == "***"
        assert "super-secret" not in json.dumps(data)


class TestEvalConfig:
    def test_threshold_bounds(self) -> None:
        with pytest.raises(ValueError):
            EvalConfig(threshold=1.5)
        with pytest.raises(ValueError):
            EvalConfig(threshold=-0.1)

    def test_default_sweep(self) -> None:
        sweep = EvalConfig().threshold_sweep
        assert sweep[0] == 0.1
        assert sweep[-1] == 0.9
