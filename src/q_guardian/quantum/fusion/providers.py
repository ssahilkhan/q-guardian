"""PredictionProvider — abstract interface for all prediction sources.

Every prediction source (rule engine, classical ML model, quantum model,
external API) implements this ABC. The Fusion Engine depends only on
PredictionProvider and ThreatPrediction — it never imports or references
any specific algorithm.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from q_guardian.quantum.fusion.prediction import ThreatPrediction


class PredictionProvider(ABC):
    """Abstract base for any source that produces ThreatPredictions.

    Lifecycle:
      1. Construct with provider_id and optional config
      2. Optionally train/fit (most providers skip this)
      3. predict(prompt, features) -> ThreatPrediction
      4. Optional: health(), explain()

    The FusionEngine registers PredictionProviders and calls predict()
    on each during fusion. Providers are decoupled from each other —
    the engine never knows whether a provider is rule-based, classical
    ML, or quantum.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g. 'rule-engine', 'random-forest')."""

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Category of provider: 'rule', 'classical', 'quantum', 'external'."""

    @property
    def display_name(self) -> str:
        """Human-readable name. Defaults to provider_id."""
        return self.provider_id

    @property
    def version(self) -> str:
        """Provider version."""
        return "1.0.0"

    @abstractmethod
    async def predict(
        self,
        prompt: str,
        features: dict[str, Any] | None = None,
    ) -> ThreatPrediction:
        """Produce a ThreatPrediction for the given prompt.

        Args:
            prompt: The raw prompt text.
            features: Optional pre-extracted feature dict.

        Returns:
            A ThreatPrediction with label, confidence, probabilities, etc.
        """

    async def train(
        self,
        training_data: list[dict[str, Any]],
    ) -> None:
        """Optional training step. Default is no-op for pre-trained or rule-based providers.

        Args:
            training_data: List of {'prompt': str, 'label': str, ...} dicts.
        """
        return None

    def health(self) -> dict[str, Any]:
        """Health status of this provider."""
        return {
            "provider_id": self.provider_id,
            "provider_type": self.provider_type,
            "status": "healthy",
        }

    def configuration(self) -> dict[str, Any]:
        """Current configuration of this provider."""
        return {
            "provider_id": self.provider_id,
            "provider_type": self.provider_type,
            "version": self.version,
        }
