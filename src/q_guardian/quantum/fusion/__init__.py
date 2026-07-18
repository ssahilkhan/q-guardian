"""Hybrid Intelligence Layer — Phase 3.

Provides the fusion engine, prediction abstractions, calibration,
and interchangeable fusion strategies for hybrid quantum-classical
threat detection.
"""

from q_guardian.quantum.fusion.prediction import ThreatPrediction, ReasoningTrace
from q_guardian.quantum.fusion.providers import PredictionProvider
from q_guardian.quantum.fusion.calibrator import ConfidenceCalibrator
from q_guardian.quantum.fusion.engine import HybridFusionEngine
from q_guardian.quantum.fusion.adapters import (
    RuleEngineProvider,
    ClassicalModelProvider,
    QuantumModelProvider,
    GenericProvider,
)
from q_guardian.quantum.fusion.strategies import (
    FusionStrategy,
    FusedPrediction,
    WeightedVotingStrategy,
    ConfidenceFusionStrategy,
    AdaptiveFusionStrategy,
    StackingFusionStrategy,
    BayesianFusionStrategy,
)

__all__ = [
    "ThreatPrediction",
    "ReasoningTrace",
    "PredictionProvider",
    "ConfidenceCalibrator",
    "HybridFusionEngine",
    "RuleEngineProvider",
    "ClassicalModelProvider",
    "QuantumModelProvider",
    "GenericProvider",
    "FusionStrategy",
    "FusedPrediction",
    "WeightedVotingStrategy",
    "ConfidenceFusionStrategy",
    "AdaptiveFusionStrategy",
    "StackingFusionStrategy",
    "BayesianFusionStrategy",
]
