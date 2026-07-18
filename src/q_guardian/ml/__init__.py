"""ML Security module for Q-Guardian.

Provides machine learning-based threat detection, classification,
and analysis for prompt security. Designed to work alongside the
rule-based Prompt Security Engine and future Quantum Analysis module.
"""

from q_guardian.ml.base import BaseThreatModel, ModelRegistry
from q_guardian.ml.config import MLConfig
from q_guardian.ml.enums import (
    DatasetFormat,
    FeatureType,
    ModelBackend,
    ModelStatus,
    ModelType,
    TrainingStatus,
)
from q_guardian.ml.evaluation.metrics import BenchmarkMetrics, ResearchMetrics
from q_guardian.ml.feature_pipeline import MLFeatureProvider
from q_guardian.ml.inference.engine import InferenceEngine
from q_guardian.ml.data import (
    DatasetEntry,
    EvaluationMetrics,
    FeatureVector,
    InferenceResult,
    ModelMetadata,
    TrainingResult,
)
from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import (
    RandomForestThreatClassifier,
    XGBoostThreatClassifier,
)
from q_guardian.ml.models.ensemble import EnsembleDetector
from q_guardian.ml.models.model_manager import ModelManager
from q_guardian.ml.plugin import ThreatAnalysisPlugin
from q_guardian.ml.storage import ModelStorage
from q_guardian.ml.training.trainer import CrossValidator, ModelTrainer

__all__ = [
    # Enums
    "DatasetFormat",
    "FeatureType",
    "ModelBackend",
    "ModelStatus",
    "ModelType",
    "TrainingStatus",
    # Config
    "MLConfig",
    # Base
    "BaseThreatModel",
    "ModelRegistry",
    # Models
    "DatasetEntry",
    "EvaluationMetrics",
    "FeatureVector",
    "InferenceResult",
    "ModelMetadata",
    "TrainingResult",
    # Feature pipeline
    "MLFeatureProvider",
    # Detectors
    "EnsembleDetector",
    "IsolationForestDetector",
    "RandomForestThreatClassifier",
    "XGBoostThreatClassifier",
    # Managers
    "InferenceEngine",
    "ModelManager",
    "ModelStorage",
    # Training
    "CrossValidator",
    "ModelTrainer",
    # Evaluation
    "BenchmarkMetrics",
    "ResearchMetrics",
    # Plugin
    "ThreatAnalysisPlugin",
]
