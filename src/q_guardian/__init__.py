"""Q-Guardian: A Hybrid Quantum-Classical Framework for Runtime Security of Autonomous AI Agents."""

__version__ = "1.1.0"
__title__ = "Q-Guardian"
__description__ = (
    "A Hybrid Quantum-Classical Framework for Runtime Security of Autonomous AI Agents"
)

# Public SDK API — re-exported so users never import from internal packages.
from q_guardian.adapters.base import Adapter
from q_guardian.core.framework_state import FrameworkState
from q_guardian.events.base import Event
from q_guardian.events.bus import EventBus
from q_guardian.framework.config import FrameworkConfig
from q_guardian.framework.context import FrameworkContext
from q_guardian.hooks.manager import HookManager

# Machine Learning Security
from q_guardian.ml.base import BaseThreatModel, ModelRegistry
from q_guardian.ml.config import MLConfig
from q_guardian.ml.data import (
    EvaluationMetrics,
    FeatureVector,
    InferenceResult,
    ModelMetadata,
    TrainingResult,
)
from q_guardian.ml.enums import ModelBackend, ModelStatus, ModelType, TrainingStatus
from q_guardian.ml.evaluation.metrics import BenchmarkMetrics, ResearchMetrics
from q_guardian.ml.feature_pipeline import MLFeatureProvider
from q_guardian.ml.inference.engine import InferenceEngine
from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import RandomForestThreatClassifier, XGBoostThreatClassifier
from q_guardian.ml.models.ensemble import EnsembleDetector
from q_guardian.ml.models.model_manager import ModelManager
from q_guardian.ml.plugin import ThreatAnalysisPlugin
from q_guardian.ml.storage import ModelStorage
from q_guardian.ml.training.trainer import CrossValidator, ModelTrainer
from q_guardian.plugins.base import Plugin, PluginMetadata, PluginStatus
from q_guardian.plugins.registry import PluginRegistry
from q_guardian.quantum.backends.base import QuantumBackend
from q_guardian.quantum.backends.manager import BackendManager
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend

# Quantum Computing Layer
from q_guardian.quantum.config import QuantumConfig
from q_guardian.quantum.data import (
    CircuitResult,
    QuantumInferenceResult,
    QuantumModelMetadata,
    QuantumTrainingResult,
)
from q_guardian.quantum.enums import (
    EncodingType,
    QuantumBackendType,
    QuantumModelType,
)
from q_guardian.quantum.evaluation.metrics import QuantumEvaluator
from q_guardian.quantum.execution.executor import CircuitExecutor
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.feature_maps.base import EncodedCircuit, QuantumFeatureMap
from q_guardian.quantum.feature_maps.pauli_feature_map import PauliFeatureMap
from q_guardian.quantum.feature_maps.zz_feature_map import ZZFeatureMap
from q_guardian.quantum.kernels.base import QuantumKernel
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.models.base import BaseQuantumModel
from q_guardian.quantum.plugin import QuantumAnalysisPlugin
from q_guardian.quantum.training.trainer import QuantumTrainer
from q_guardian.runtime.context import RuntimeContext

# Runtime abstraction layer
from q_guardian.runtime.enums import (
    AgentStatus,
    MemoryOperation,
    MemoryType,
    SessionStatus,
    ThreatSeverity,
    ThreatType,
    ToolType,
)
from q_guardian.runtime.managers import (
    MemoryTracker,
    RequestManager,
    SessionManager,
    ToolExecutionTracker,
)
from q_guardian.runtime.models import (
    Agent,
    AgentRequest,
    AgentResponse,
    AgentSession,
    MemoryAccess,
    RiskContext,
    SecurityContext,
    ThreatContext,
    ToolInvocation,
)
from q_guardian.sdk.guardian import Guardian
from q_guardian.security.config import PromptSecurityConfig
from q_guardian.security.decision import SecurityDecisionEngine

# Prompt Security Engine
from q_guardian.security.enums import (
    PromptCategory,
    PromptDecision,
    PromptSeverity,
)
from q_guardian.security.models import (
    PromptAnalysis,
    PromptFeatures,
    PromptFinding,
    PromptRule,
)
from q_guardian.security.pipeline import (
    PromptFeatureExtractor,
    PromptNormalizer,
    PromptValidator,
    RuleEngine,
)
from q_guardian.security.plugin import PromptScannerPlugin

__all__ = [
    # Framework core
    "Adapter",
    # Runtime models
    "Agent",
    "AgentRequest",
    "AgentResponse",
    "AgentSession",
    # Runtime enums
    "AgentStatus",
    # Quantum Computing Layer
    "AngleEncodingMap",
    "BackendManager",
    "BaseQuantumModel",
    # ML Security
    "BaseThreatModel",
    "BenchmarkMetrics",
    "CircuitExecutor",
    "CircuitResult",
    "CrossValidator",
    "EncodedCircuit",
    "EncodingType",
    "EnsembleDetector",
    "EvaluationMetrics",
    "Event",
    "EventBus",
    "FeatureVector",
    "FrameworkConfig",
    "FrameworkContext",
    "FrameworkState",
    "Guardian",
    "HookManager",
    "InferenceEngine",
    "InferenceResult",
    "IsolationForestDetector",
    "LocalSimulatorBackend",
    "MLConfig",
    "MLFeatureProvider",
    "MemoryAccess",
    "MemoryOperation",
    # Runtime managers
    "MemoryTracker",
    "MemoryType",
    "ModelBackend",
    "ModelManager",
    "ModelMetadata",
    "ModelRegistry",
    "ModelStatus",
    "ModelStorage",
    "ModelTrainer",
    "ModelType",
    "PauliFeatureMap",
    "Plugin",
    "PluginMetadata",
    "PluginRegistry",
    "PluginStatus",
    # Security engine
    "PromptAnalysis",
    "PromptCategory",
    "PromptDecision",
    "PromptFeatureExtractor",
    "PromptFeatures",
    "PromptFinding",
    "PromptNormalizer",
    "PromptRule",
    "PromptScannerPlugin",
    "PromptSecurityConfig",
    "PromptSeverity",
    "PromptValidator",
    "QuantumAnalysisPlugin",
    "QuantumBackend",
    "QuantumBackendType",
    "QuantumConfig",
    "QuantumEvaluator",
    "QuantumFeatureMap",
    "QuantumInferenceResult",
    "QuantumKernel",
    "QuantumKernelEstimator",
    "QuantumModelMetadata",
    "QuantumModelType",
    "QuantumTrainer",
    "QuantumTrainingResult",
    "RandomForestThreatClassifier",
    "RequestManager",
    "ResearchMetrics",
    "RiskContext",
    "RuleEngine",
    # Runtime context
    "RuntimeContext",
    "SecurityContext",
    "SecurityDecisionEngine",
    "SessionManager",
    "SessionStatus",
    "ThreatAnalysisPlugin",
    "ThreatContext",
    "ThreatSeverity",
    "ThreatType",
    "ToolExecutionTracker",
    "ToolInvocation",
    "ToolType",
    "TrainingResult",
    "TrainingStatus",
    "XGBoostThreatClassifier",
    "ZZFeatureMap",
]
