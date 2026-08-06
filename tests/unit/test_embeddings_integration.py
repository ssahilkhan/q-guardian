"""Unit tests for the mode-aware trainer adapters."""

from __future__ import annotations

from q_guardian.embeddings.fusion import FeatureMode, ModeFeatureExtractor
from q_guardian.embeddings.integration import ModeQuantumAdapter, ModeTrainingAdapter


class _FakeTrainingResult:
    def __init__(self, marker: str = "fake") -> None:
        self.marker = marker


class _FakeModelTrainer:
    def __init__(self) -> None:
        self.train_calls: list[dict] = []
        self.anomaly_calls: list[dict] = []

    async def train(self, model, x, y, feature_names=None, test_size=None, cv_folds=None):
        self.train_calls.append({"model": model, "x": x, "y": y, "feature_names": feature_names})
        return _FakeTrainingResult()

    async def train_anomaly_detector(self, model, x):
        self.anomaly_calls.append({"model": model, "x": x})
        return _FakeTrainingResult(marker="anomaly")


class _FakeQuantumTrainer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def train(self, model, x, y=None, x_val=None, y_val=None):
        self.calls.append({"model": model, "x": x, "y": y})
        return _FakeTrainingResult(marker="quantum")


class _SpyExtractor(ModeFeatureExtractor):
    def __init__(self) -> None:
        super().__init__()
        self.requested_modes: list[FeatureMode | None] = []
        self.requested_texts: list[list[str]] = []

    def vectors(self, texts, mode=None):
        self.requested_texts.append(list(texts))
        self.requested_modes.append(mode)
        return super().vectors(texts, mode)

    def feature_names(self, mode=None):
        return super().feature_names(mode)


class TestModeTrainingAdapter:
    def test_defaults(self):
        adapter = ModeTrainingAdapter()
        assert adapter.trainer is not None
        assert adapter.extractor is not None

    async def test_train_texts_builds_matrix_and_names(self):
        trainer = _FakeModelTrainer()
        extractor = _SpyExtractor()
        adapter = ModeTrainingAdapter(trainer=trainer, extractor=extractor)

        result = await adapter.train_texts("model", ["a", "b"], [0, 1], mode="hybrid")

        assert result.marker == "fake"
        assert len(trainer.train_calls) == 1
        call = trainer.train_calls[0]
        assert len(call["x"]) == 2
        assert len(call["x"][0]) == 43 + 16
        assert len(call["feature_names"]) == 43 + 16
        assert call["y"] == [0, 1]

    async def test_train_texts_forwards_trainer_kwargs(self):
        trainer = _FakeModelTrainer()
        adapter = ModeTrainingAdapter(trainer=trainer)
        await adapter.train_texts(
            "model", ["a"], [1], mode=FeatureMode.HANDCRAFTED_ONLY, cv_folds=3, test_size=0.2
        )
        call = trainer.train_calls[0]
        assert call["feature_names"] is not None

    async def test_train_texts_passes_mode_to_extractor(self):
        trainer = _FakeModelTrainer()
        extractor = _SpyExtractor()
        adapter = ModeTrainingAdapter(trainer=trainer, extractor=extractor)
        await adapter.train_texts("model", ["a", "b"], [0, 1], mode="embedding")
        assert extractor.requested_modes == ["embedding"]
        assert extractor.requested_texts == [["a", "b"]]

    async def test_train_anomaly_texts(self):
        trainer = _FakeModelTrainer()
        adapter = ModeTrainingAdapter(trainer=trainer)
        result = await adapter.train_anomaly_texts("model", ["a", "b", "c"], mode="hybrid")
        assert result.marker == "anomaly"
        assert len(trainer.anomaly_calls) == 1
        assert len(trainer.anomaly_calls[0]["x"]) == 3


class TestModeQuantumAdapter:
    def test_defaults(self):
        adapter = ModeQuantumAdapter()
        assert adapter.trainer is not None
        assert adapter.extractor is not None

    def test_train_texts(self):
        trainer = _FakeQuantumTrainer()
        adapter = ModeQuantumAdapter(trainer=trainer)
        result = adapter.train_texts("model", ["a", "b"], [0, 1], mode="embedding")
        assert result.marker == "quantum"
        assert len(trainer.calls) == 1
        assert trainer.calls[0]["y"] == [0, 1]
        assert len(trainer.calls[0]["x"][0]) == 16

    def test_train_texts_without_labels(self):
        trainer = _FakeQuantumTrainer()
        adapter = ModeQuantumAdapter(trainer=trainer)
        adapter.train_texts("model", ["a", "b"])
        assert trainer.calls[0]["y"] is None

    def test_train_texts_handcrafted_mode(self):
        trainer = _FakeQuantumTrainer()
        adapter = ModeQuantumAdapter(trainer=trainer)
        adapter.train_texts("model", ["a"], mode=FeatureMode.HANDCRAFTED_ONLY)
        assert len(trainer.calls[0]["x"][0]) == 43
