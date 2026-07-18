"""Quantum module exceptions."""

from __future__ import annotations


class QuantumError(Exception):
    """Base exception for quantum module errors."""


class BackendError(QuantumError):
    """Error related to quantum backend operations."""


class BackendNotAvailableError(BackendError):
    """Raised when a requested quantum backend is not available."""


class CircuitExecutionError(BackendError):
    """Raised when circuit execution fails."""


class TranspilationError(BackendError):
    """Raised when circuit transpilation fails."""


class FeatureMapError(QuantumError):
    """Error related to quantum feature mapping."""


class EncodingDimensionError(FeatureMapError):
    """Raised when feature dimensions don't match qubit count."""


class KernelError(QuantumError):
    """Error related to quantum kernel computation."""


class ModelNotTrainedError(QuantumError):
    """Raised when prediction is attempted on untrained model."""


class TrainingError(QuantumError):
    """Error during quantum model training."""


class ConfigurationError(QuantumError):
    """Invalid quantum configuration."""


class FusionError(QuantumError):
    """Error during hybrid fusion computation."""


class QuantumInferenceError(QuantumError):
    """Error during quantum inference."""

    def __init__(self, detail: str = "", model_name: str = "", **kwargs: object) -> None:
        self.detail = detail
        self.model_name = model_name
        super().__init__(detail or "Quantum inference error")
