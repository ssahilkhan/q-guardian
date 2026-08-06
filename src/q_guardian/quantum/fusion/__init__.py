"""Hybrid Intelligence Layer — Phase 3.

Provides the fusion engine, prediction abstractions, calibration,
and interchangeable fusion strategies for hybrid quantum-classical
threat detection.
"""

from q_guardian.quantum.fusion.adapters import (
    ClassicalModelProvider,
    GenericProvider,
    QuantumModelProvider,
    RuleEngineProvider,
)
from q_guardian.quantum.fusion.calibrator import ConfidenceCalibrator
from q_guardian.quantum.fusion.engine import HybridFusionEngine
from q_guardian.quantum.fusion.prediction import ReasoningTrace, ThreatPrediction
from q_guardian.quantum.fusion.providers import PredictionProvider
from q_guardian.quantum.fusion.strategies import (
    AdaptiveFusionStrategy,
    BayesianFusionStrategy,
    ConfidenceFusionStrategy,
    FusedPrediction,
    FusionStrategy,
    StackingFusionStrategy,
    WeightedVotingStrategy,
)

__all__ = [
    "AdaptiveFusionStrategy",
    "BayesianFusionStrategy",
    "ClassicalModelProvider",
    "ConfidenceCalibrator",
    "ConfidenceFusionStrategy",
    "FusedPrediction",
    "FusionStrategy",
    "GenericProvider",
    "HybridFusionEngine",
    "PredictionProvider",
    "QuantumModelProvider",
    "ReasoningTrace",
    "RuleEngineProvider",
    "StackingFusionStrategy",
    "ThreatPrediction",
    "WeightedVotingStrategy",
]
