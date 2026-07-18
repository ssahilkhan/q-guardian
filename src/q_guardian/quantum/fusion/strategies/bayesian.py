"""BayesianFusionStrategy — interface-only Bayesian fusion.

Implements the FusionStrategy ABC with a placeholder that raises
NotImplementedError. Full Bayesian fusion (e.g. Bayesian model
averaging, posterior updates) is deferred to a future phase.
"""

from __future__ import annotations

from typing import Any

from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.quantum.fusion.strategies.base import FusionStrategy, FusedPrediction
from q_guardian.quantum.exceptions import FusionError


class BayesianFusionStrategy(FusionStrategy):
    """Bayesian fusion — interface only.

    This strategy implements the FusionStrategy interface but defers
    the actual Bayesian inference implementation. Calling fuse() raises
    FusionError with a descriptive message.

    Planned implementation:
      - Bayesian Model Averaging (BMA) with prior/posterior weights
      - Online posterior updates as new predictions arrive
      - Uncertainty quantification via credible intervals
    """

    @property
    def name(self) -> str:
        return "bayesian"

    @property
    def display_name(self) -> str:
        return "Bayesian Fusion"

    @property
    def description(self) -> str:
        return "Bayesian model averaging (interface only — not yet implemented)"

    def fuse(
        self,
        predictions: list[ThreatPrediction],
        weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> FusedPrediction:
        """Fuse predictions using Bayesian model averaging.

        Raises:
            FusionError: Always — this strategy is not yet implemented.
        """
        raise FusionError(
            "Bayesian fusion is not yet implemented. "
            "Use weighted_voting, confidence_fusion, stacking, or adaptive instead."
        )

    def predict_with_uncertainty(
        self,
        predictions: list[ThreatPrediction],
        prior_weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Planned: Bayesian fusion with uncertainty quantification.

        Returns:
            Dict with 'fused_prediction', 'credible_interval', 'posterior_weights'.
        """
        raise FusionError("Bayesian fusion is not yet implemented.")

    def update_posterior(
        self,
        provider_id: str,
        outcome: bool,
        learning_rate: float = 0.1,
    ) -> None:
        """Planned: Update posterior weight for a provider based on observed outcome.

        Args:
            provider_id: Provider identifier.
            outcome: Whether the provider was correct (True) or not (False).
            learning_rate: How fast to update.
        """
        raise FusionError("Bayesian fusion is not yet implemented.")
