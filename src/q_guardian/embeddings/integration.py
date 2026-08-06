"""Dependency-injection adapters for the training pipelines.

``ModelTrainer`` (classical ML) and ``QuantumTrainer`` (quantum models) are
existing, completed modules that consume feature matrices directly. These
thin adapters produce mode-specific matrices (handcrafted / embedding /
hybrid) from raw prompt text and forward them to an *injected* trainer —
no trainer code is modified.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from q_guardian.embeddings.fusion import (
    FeatureMode,
    ModeFeatureExtractor,
)
from q_guardian.ml.training.trainer import ModelTrainer
from q_guardian.quantum.training.trainer import QuantumTrainer

if TYPE_CHECKING:
    from q_guardian.ml.base import BaseThreatModel
    from q_guardian.ml.data import TrainingResult
    from q_guardian.quantum.data import QuantumTrainingResult
    from q_guardian.quantum.models.base import BaseQuantumModel


class ModeTrainingAdapter:
    """Trains a classical model on mode-specific features via ``ModelTrainer``.

    Args:
        trainer: The ``ModelTrainer`` to delegate to (injectable for tests).
        extractor: The mode-aware feature extractor (injectable).
    """

    def __init__(
        self,
        *,
        trainer: ModelTrainer | None = None,
        extractor: ModeFeatureExtractor | None = None,
    ) -> None:
        self._trainer = trainer if trainer is not None else ModelTrainer()
        self._extractor = extractor if extractor is not None else ModeFeatureExtractor()

    @property
    def trainer(self) -> ModelTrainer:
        return self._trainer

    @property
    def extractor(self) -> ModeFeatureExtractor:
        return self._extractor

    async def train_texts(
        self,
        model: BaseThreatModel,
        texts: list[str],
        labels: list[int],
        mode: FeatureMode | str | None = None,
        **trainer_kwargs: Any,
    ) -> TrainingResult:
        """Build the mode feature matrix and train ``model`` through the
        injected ``ModelTrainer``."""
        x = self._extractor.vectors(texts, mode)
        names = self._extractor.feature_names(mode)
        return await self._trainer.train(
            model,
            x,
            labels,
            feature_names=names,
            **trainer_kwargs,
        )

    async def train_anomaly_texts(
        self,
        model: BaseThreatModel,
        texts: list[str],
        mode: FeatureMode | str | None = None,
    ) -> TrainingResult:
        """Train an unsupervised anomaly detector on mode features."""
        x = self._extractor.vectors(texts, mode)
        return await self._trainer.train_anomaly_detector(model, x)


class ModeQuantumAdapter:
    """Trains a quantum model on mode-specific features via ``QuantumTrainer``.

    Args:
        trainer: The ``QuantumTrainer`` to delegate to (injectable for tests).
        extractor: The mode-aware feature extractor (injectable).
    """

    def __init__(
        self,
        *,
        trainer: QuantumTrainer | None = None,
        extractor: ModeFeatureExtractor | None = None,
    ) -> None:
        self._trainer = trainer if trainer is not None else QuantumTrainer()
        self._extractor = extractor if extractor is not None else ModeFeatureExtractor()

    @property
    def trainer(self) -> QuantumTrainer:
        return self._trainer

    @property
    def extractor(self) -> ModeFeatureExtractor:
        return self._extractor

    def train_texts(
        self,
        model: BaseQuantumModel,
        texts: list[str],
        labels: list[int] | None = None,
        mode: FeatureMode | str | None = None,
    ) -> QuantumTrainingResult:
        """Build the mode feature matrix and train ``model`` through the
        injected ``QuantumTrainer``."""
        x = self._extractor.vectors(texts, mode)
        return self._trainer.train(model, x, labels)
