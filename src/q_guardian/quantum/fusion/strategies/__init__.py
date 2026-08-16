"""Fusion strategy implementations."""

from q_guardian.quantum.enums import FusionStrategyType
from q_guardian.quantum.fusion.strategies.adaptive import AdaptiveFusionStrategy
from q_guardian.quantum.fusion.strategies.base import FusedPrediction, FusionStrategy
from q_guardian.quantum.fusion.strategies.bayesian import BayesianFusionStrategy
from q_guardian.quantum.fusion.strategies.confidence import ConfidenceFusionStrategy
from q_guardian.quantum.fusion.strategies.stacking import StackingFusionStrategy
from q_guardian.quantum.fusion.strategies.weighted_voting import WeightedVotingStrategy

__all__ = [
    "AdaptiveFusionStrategy",
    "BayesianFusionStrategy",
    "ConfidenceFusionStrategy",
    "FusedPrediction",
    "FusionStrategy",
    "StackingFusionStrategy",
    "WeightedVotingStrategy",
]

# Single source of truth for fusion strategies the backend can actually
# execute at runtime. `max_confidence` is deliberately absent — no
# implementation exists (enum-only). `bayesian` is interface-only and is
# reported separately (its fuse() raises).
IMPLEMENTED_STRATEGIES: dict[str, type[FusionStrategy]] = {
    FusionStrategyType.WEIGHTED_VOTING.value: WeightedVotingStrategy,
    FusionStrategyType.CONFIDENCE_BASED.value: ConfidenceFusionStrategy,
    FusionStrategyType.STACKING.value: StackingFusionStrategy,
    FusionStrategyType.ADAPTIVE.value: AdaptiveFusionStrategy,
}

# Strategies whose interface exists but whose implementation is a stub.
INTERFACE_ONLY_STRATEGIES: tuple[str, ...] = (FusionStrategyType.BAYESIAN.value,)
