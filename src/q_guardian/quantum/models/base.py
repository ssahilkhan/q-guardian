"""Abstract base class for quantum threat models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

from q_guardian.ml.base import BaseThreatModel
from q_guardian.quantum.data import QuantumModelMetadata, QuantumInferenceResult
from q_guardian.quantum.enums import QuantumModelType
from q_guardian.security.extensibility import DetectionResult, ThreatClassifier
from q_guardian.security.models import PromptFeatures

logger = structlog.get_logger("quantum.base_model")


class BaseQuantumModel(BaseThreatModel, ThreatClassifier, ABC):
    """Common interface for all quantum threat models.

    Inherits from both:
      - BaseThreatModel (Module 5 generic model interface)
      - ThreatClassifier (Module 4 quantum classification interface)

    Every quantum ML algorithm (QSVM, VQC, QNN, etc.) must implement
    this interface. This ensures that quantum models integrate seamlessly
    with the existing inference pipeline.
    """

    @property
    @abstractmethod
    def quantum_metadata(self) -> QuantumModelMetadata:
        """Return quantum-specific model metadata."""

    @property
    @abstractmethod
    def is_trained(self) -> bool:
        """Return whether the model has been trained."""

    @abstractmethod
    async def predict_quantum(self, features: list[float]) -> QuantumInferenceResult:
        """Run prediction using quantum model.

        Args:
            features: Numeric feature vector.

        Returns:
            QuantumInferenceResult with predictions and metadata.
        """

    def health(self) -> dict[str, Any]:
        """Return model health status with quantum metadata."""
        base = super().health()
        qmeta = self.quantum_metadata
        base["quantum_model_type"] = qmeta.model_type.value
        base["num_qubits"] = qmeta.num_qubits
        base["is_trained"] = self.is_trained
        return base
