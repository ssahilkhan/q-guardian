"""Abstract base class for quantum feature maps."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.quantum.enums import EncodingType


class EncodedCircuit(BaseModel):
    """Result of encoding classical features into a quantum circuit."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    circuit: Any = Field(description="The encoded quantum circuit (backend-specific)")
    num_qubits: int = Field(description="Number of qubits used")
    encoding_type: EncodingType = Field(description="Encoding strategy used")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Encoding metadata")


class QuantumFeatureMap(ABC):
    """Abstract base class for quantum feature maps.

    Every feature map (Angle Encoding, ZZFeatureMap, Amplitude Encoding,
    etc.) must implement this interface. Feature maps convert classical
    feature vectors into quantum circuits for quantum ML models.

    Integration point:
      Models call encode() to convert features before execution.
      Training pipelines call encode_batch() for efficient batch encoding.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the feature map name."""

    @property
    @abstractmethod
    def encoding_type(self) -> EncodingType:
        """Return the encoding strategy type."""

    @property
    @abstractmethod
    def num_qubits(self) -> int:
        """Return the number of qubits required."""

    @abstractmethod
    def encode(self, features: list[float]) -> EncodedCircuit:
        """Encode a single feature vector into a quantum circuit.

        Args:
            features: Classical feature vector.

        Returns:
            EncodedCircuit with the encoded quantum circuit.
        """

    def encode_batch(self, batch: list[list[float]]) -> list[EncodedCircuit]:
        """Encode a batch of feature vectors.

        Default implementation calls encode() for each vector.
        Subclasses may override for batch optimization.

        Args:
            batch: List of classical feature vectors.

        Returns:
            List of EncodedCircuit instances.
        """
        return [self.encode(features) for features in batch]

    def validate_features(self, features: list[float]) -> bool:
        """Validate that feature vector dimensions are compatible.

        Args:
            features: Feature vector to validate.

        Returns:
            True if the feature vector is valid for this map.
        """
        return len(features) > 0

    def health(self) -> dict[str, Any]:
        """Return feature map health status."""
        return {
            "status": "healthy",
            "feature_map": self.name,
            "encoding_type": self.encoding_type.value,
            "num_qubits": self.num_qubits,
        }
