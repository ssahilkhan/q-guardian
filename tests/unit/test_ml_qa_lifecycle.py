"""ML model QA lifecycle tests.

Verifies the full lifecycle of every classical ML model with seeded,
deterministic data: train -> predict -> serialize -> load -> identical
predictions. These tests validate model CODE correctness and
reproducibility — NOT production performance (no trained artifacts ship
with the framework; see docs/qa/ml_model_qa_report.md).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import numpy as np
import pytest

from q_guardian.ml.config import MLConfig
from q_guardian.ml.data import ModelMetadata
from q_guardian.ml.enums import ModelStatus, ModelType
from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import RandomForestThreatClassifier
from q_guardian.ml.models.ensemble import EnsembleDetector
from q_guardian.ml.storage import ModelStorage

if TYPE_CHECKING:
    from pathlib import Path

SEED = 42


def _synthetic_dataset(
    n_samples: int = 200, n_features: int = 43
) -> tuple[list[list[float]], list[int]]:
    """Deterministic synthetic dataset: class 0 vs class 1 separable blobs."""
    rng = np.random.default_rng(SEED)
    half = n_samples // 2

    benign = rng.normal(loc=0.0, scale=1.0, size=(half, n_features))
    threat = rng.normal(loc=3.0, scale=1.0, size=(n_samples - half, n_features))

    x = np.vstack([benign, threat])
    y = np.array([0] * half + [1] * (n_samples - half))
    return x.tolist(), y.tolist()


@pytest.fixture(scope="module")
def dataset() -> tuple[list[list[float]], list[int]]:
    return _synthetic_dataset()


@pytest.fixture
def storage(tmp_path: Path) -> ModelStorage:
    return ModelStorage(base_path=tmp_path / "models")


class TestRandomForestLifecycle:
    async def test_train_predict_deterministic(self, dataset: tuple) -> None:
        x, y = dataset
        config = MLConfig(random_state=SEED)

        clf_a = RandomForestThreatClassifier(config=config, n_estimators=20)
        clf_b = RandomForestThreatClassifier(config=config, n_estimators=20)

        clf_a.train(x, y)
        clf_b.train(x, y)

        assert clf_a.is_trained
        pred_a = await clf_a.predict(x[0])
        pred_b = await clf_b.predict(x[0])

        assert pred_a["predicted_class"] == pred_b["predicted_class"]
        assert pred_a["probabilities"] == pytest.approx(pred_b["probabilities"])

    async def test_predict_output_schema(self, dataset: tuple) -> None:
        x, y = dataset
        clf = RandomForestThreatClassifier(config=MLConfig(random_state=SEED), n_estimators=10)
        clf.train(x, y)

        result = await clf.predict(x[-1])

        assert {"predicted_class", "probabilities", "confidence"} <= set(result)
        assert 0.0 <= result["confidence"] <= 1.0
        prob_sum = sum(result["probabilities"].values())
        assert prob_sum == pytest.approx(1.0, abs=1e-6)

    async def test_untrained_predict_returns_unknown(self) -> None:
        clf = RandomForestThreatClassifier()

        result = await clf.predict([0.0] * 43)

        assert result["predicted_class"] == "unknown"
        assert result["confidence"] == 0.0

    async def test_train_requires_labels(self, dataset: tuple) -> None:
        x, _y = dataset
        clf = RandomForestThreatClassifier()

        with pytest.raises(ValueError, match="labels"):
            clf.train(x, None)

    async def test_serialization_roundtrip_identical_predictions(
        self, dataset: tuple, storage: ModelStorage
    ) -> None:
        x, y = dataset
        clf = RandomForestThreatClassifier(config=MLConfig(random_state=SEED), n_estimators=10)
        clf.train(x, y)

        metadata = clf.metadata
        artifact = storage.save(clf.model, metadata)
        assert metadata.status == ModelStatus.READY

        loaded_model = storage.load(metadata)
        assert loaded_model is not None

        original = await clf.predict(x[5])
        restored = clf
        restored._model = loaded_model
        reloaded = await restored.predict(x[5])

        assert artifact.endswith(".joblib")
        assert reloaded["predicted_class"] == original["predicted_class"]
        assert reloaded["probabilities"] == pytest.approx(original["probabilities"])


class TestIsolationForestLifecycle:
    async def test_train_and_detect_anomaly(self) -> None:
        """Train on the detector's own 12-dim feature space (see F-09)."""
        rng = np.random.default_rng(SEED)
        normal_data = rng.normal(loc=0.0, scale=0.5, size=(200, 12)).tolist()

        detector = IsolationForestDetector(config=MLConfig(random_state=SEED))

        detector.train(normal_data)
        assert detector.is_trained

        from q_guardian.security.models import PromptFeatures

        typical = PromptFeatures(length=20, word_count=4)
        extreme = PromptFeatures(
            length=999_999,
            special_char_count=99_999,
            uppercase_ratio=1.0,
            entropy=8.0,
        )

        result_typical = await detector.detect("typical", typical)

        assert result_typical.risk_score >= 0.0
        # Extreme outlier must either flag as anomaly or score above typical.
        result_extreme = await detector.detect("extreme", extreme)

        assert (
            result_extreme.metadata["is_anomaly"]
            or result_extreme.risk_score >= result_typical.risk_score
        )

    async def test_metadata_tracks_training(self) -> None:
        rng = np.random.default_rng(SEED)
        data = rng.normal(size=(50, 12)).tolist()

        detector = IsolationForestDetector()
        detector.train(data)

        assert detector.metadata.training_samples == 50
        assert detector.metadata.feature_count == 12
        assert detector.metadata.model_type == ModelType.ANOMALY_DETECTION

    async def test_serialization_roundtrip(self, storage: ModelStorage) -> None:
        rng = np.random.default_rng(SEED)
        data = rng.normal(size=(100, 12)).tolist()

        detector = IsolationForestDetector(config=MLConfig(random_state=SEED))
        detector.train(data)

        metadata = detector.metadata
        storage.save(detector.model, metadata)
        loaded = storage.load(metadata)

        assert loaded is not None
        sample = np.array(data[:3], dtype=np.float64)
        orig_scores = detector.model.decision_function(sample)
        loaded_scores = loaded.decision_function(sample)

        assert orig_scores == pytest.approx(loaded_scores)


class TestXGBoostLifecycle:
    async def test_lifecycle_when_available(self, dataset: tuple, storage: ModelStorage) -> None:
        pytest.importorskip("xgboost")

        from q_guardian.ml.models.classifier import XGBoostThreatClassifier

        x, y = dataset
        clf = XGBoostThreatClassifier(config=MLConfig(random_state=SEED), n_estimators=20)
        assert clf._available is True

        clf.train(x, y)
        result_a = await clf.predict(x[0])

        metadata = clf.metadata
        storage.save(clf.model, metadata)
        clf._model = storage.load(metadata)
        result_b = await clf.predict(x[0])

        assert result_b["predicted_class"] == result_a["predicted_class"]

    async def test_unavailable_falls_back_gracefully(self) -> None:
        """If xgboost is missing, the classifier must degrade, not crash."""
        from q_guardian.ml.models.classifier import XGBoostThreatClassifier

        clf = XGBoostThreatClassifier()
        result = await clf.predict([0.0] * 43)

        if not clf._available:
            assert result["predicted_class"] == "unknown"
        else:
            assert "predicted_class" in result


class TestEnsembleDetector:
    async def test_ensemble_combines_detectors(self, dataset: tuple) -> None:
        x, y = dataset
        rf = RandomForestThreatClassifier(config=MLConfig(random_state=SEED), n_estimators=10)
        rf.train(x, y)

        rng = np.random.default_rng(SEED)
        iso_data = rng.normal(size=(100, 12)).tolist()
        iso = IsolationForestDetector(config=MLConfig(random_state=SEED))
        iso.train(iso_data)

        ensemble = EnsembleDetector(detectors=[rf, iso])

        assert ensemble.detector_count == 2

        from q_guardian.security.models import PromptFeatures

        result = await ensemble.detect("test prompt", PromptFeatures())

        assert result is not None


class TestModelStorageEdgeCases:
    def test_load_missing_artifact_raises(self, tmp_path: Path) -> None:
        storage = ModelStorage(base_path=tmp_path / "models")
        metadata = ModelMetadata(
            name="ghost-model",
            model_type=ModelType.CLASSIFICATION,
            backend="sklearn",
            artifact_path=str(tmp_path / "does_not_exist.joblib"),
        )

        with pytest.raises(FileNotFoundError):
            storage.load(metadata)

    def test_load_empty_path_raises(self, tmp_path: Path) -> None:
        storage = ModelStorage(base_path=tmp_path / "models")
        metadata = ModelMetadata(
            name="no-path",
            model_type=ModelType.CLASSIFICATION,
            backend="sklearn",
            artifact_path="",
        )

        with pytest.raises(ValueError, match="artifact_path"):
            storage.load(metadata)


def test_asyncio_loop_available() -> None:
    """Sanity: the module-level asyncio import is used by async tests."""
    assert asyncio.iscoroutinefunction(IsolationForestDetector.detect)
