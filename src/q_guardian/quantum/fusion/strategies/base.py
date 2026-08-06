"""FusionStrategy — abstract interface for fusion algorithms.

Each strategy takes a list of ThreatPrediction objects (one per
provider) and produces a single FusedPrediction. Strategies are
interchangeable and registered dynamically through the plugin system.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.utils.uuid_utils import generate_uuid


class FusedPrediction(BaseModel):
    """Output of a fusion strategy — the final combined prediction."""

    model_config = ConfigDict(populate_by_name=True)

    fused_id: str = Field(default_factory=generate_uuid, description="Unique fused result ID")
    predicted_label: str = Field(description="Final predicted class")
    confidence: float = Field(ge=0.0, le=1.0, description="Fused confidence")
    probabilities: dict[str, float] = Field(
        default_factory=dict, description="Fused probability distribution"
    )
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Fused risk score")

    strategy_name: str = Field(description="Name of the strategy used")
    provider_contributions: dict[str, float] = Field(
        default_factory=dict, description="provider_id -> contribution weight"
    )

    source_predictions: list[ThreatPrediction] = Field(
        default_factory=list, description="Original predictions from providers"
    )

    calibrated: bool = Field(default=False, description="Whether predictions were calibrated")
    num_providers: int = Field(default=0, description="Number of providers that contributed")
    num_failed: int = Field(default=0, description="Number of providers that failed")

    reasoning_summary: str = Field(default="", description="Human-readable fusion reasoning")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra fusion metadata")

    def to_fused_result(self) -> dict[str, Any]:
        """Convert to the legacy FusedResult-compatible dict format."""
        return {
            "predicted_class": self.predicted_label,
            "confidence": self.confidence,
            "risk_score": self.risk_score,
            "predictions": self.probabilities,
            "fusion_strategy": self.strategy_name,
            "source_results": [
                {
                    "provider": p.provider_id,
                    "label": p.predicted_label,
                    "confidence": p.confidence,
                }
                for p in self.source_predictions
            ],
            "quantum_contribution": sum(
                w
                for pid, w in self.provider_contributions.items()
                if "quantum" in pid.lower() or "qsvm" in pid.lower()
            ),
            "classical_contribution": sum(
                w
                for pid, w in self.provider_contributions.items()
                if "classical" in pid.lower() or "forest" in pid.lower() or "xgboost" in pid.lower()
            ),
            "rule_contribution": sum(
                w for pid, w in self.provider_contributions.items() if "rule" in pid.lower()
            ),
            "metadata": self.metadata,
        }


class FusionStrategy(ABC):
    """Abstract base for all fusion strategies.

    Each strategy implements a single method: fuse(). Given a list of
    ThreatPrediction objects (one per provider), it produces a single
    FusedPrediction.

    Strategies receive calibrated predictions and should not modify them.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier (e.g. 'weighted_voting', 'stacking')."""

    @property
    def display_name(self) -> str:
        """Human-readable name."""
        return self.name

    @property
    def description(self) -> str:
        """Short description of the strategy."""
        return ""

    @abstractmethod
    def fuse(
        self,
        predictions: list[ThreatPrediction],
        weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> FusedPrediction:
        """Fuse multiple predictions into a single result.

        Args:
            predictions: Valid predictions from registered providers.
            weights: Optional provider_id -> weight mapping.
            **kwargs: Strategy-specific parameters.

        Returns:
            A FusedPrediction combining all inputs.
        """

    def health(self) -> dict[str, Any]:
        """Health status."""
        return {"strategy": self.name, "status": "healthy"}

    def validate_predictions(self, predictions: list[ThreatPrediction]) -> list[ThreatPrediction]:
        """Filter out invalid predictions. Override for custom validation."""
        return [p for p in predictions if p.is_valid]
