"""Tests for ModelTrainer and CrossValidator."""

from __future__ import annotations

import pytest

from q_guardian.ml.config import MLConfig
from q_guardian.ml.enums import TrainingStatus
from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import RandomForestThreatClassifier
from q_guardian.ml.storage import ModelStorage
from q_guardian.ml.training.trainer import ModelTrainer, CrossValidator

import tempfile


def _make_training_data(n: int = 60) -> tuple[list[list[float]], list[int]]:
    import random
    random.seed(42)
    X = [[random.uniform(0, 100) for _ in range(12)] for _ in range(n)]
    y = [random.choice([0, 1, 2]) for _ in range(n)]
    return X, y


class TestModelTrainer:
    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.storage = ModelStorage(base_path=self.tmpdir)
        self.trainer = ModelTrainer(storage=self.storage)

    @pytest.mark.asyncio
    async def test_train_classifier(self) -> None:
        model = RandomForestThreatClassifier()
        X, y = _make_training_data(60)
        result = await self.trainer.train(model, X, y)
        assert result.status == TrainingStatus.COMPLETED
        assert result.metrics.get("accuracy", 0) > 0.0
        assert result.training_samples > 0

    @pytest.mark.asyncio
    async def test_train_anomaly_detector(self) -> None:
        model = IsolationForestDetector()
        X, _ = _make_training_data(60)
        result = await self.trainer.train_anomaly_detector(model, X)
        assert result.status == TrainingStatus.COMPLETED
        assert result.training_samples == 60

    @pytest.mark.asyncio
    async def test_train_with_feature_names(self) -> None:
        model = RandomForestThreatClassifier()
        X, y = _make_training_data(60)
        feature_names = [f"f{i}" for i in range(12)]
        result = await self.trainer.train(model, X, y, feature_names=feature_names)
        assert result.status == TrainingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cv_scores(self) -> None:
        model = RandomForestThreatClassifier()
        X, y = _make_training_data(60)
        result = await self.trainer.train(model, X, y, cv_folds=3)
        assert len(result.cv_scores) > 0
        assert result.cv_mean > 0.0


class TestCrossValidator:
    def setup_method(self) -> None:
        self.cv = CrossValidator()

    @pytest.mark.asyncio
    async def test_cross_validate(self) -> None:
        model = RandomForestThreatClassifier()
        X, y = _make_training_data(60)
        model.train(X, y)
        result = await self.cv.cross_validate(model, X, y, folds=3)
        assert "mean" in result
        assert "std" in result
        assert len(result["scores"]) > 0

    @pytest.mark.asyncio
    async def test_cv_untrained_model(self) -> None:
        model = RandomForestThreatClassifier()
        X, y = _make_training_data(60)
        result = await self.cv.cross_validate(model, X, y)
        assert "error" in result
