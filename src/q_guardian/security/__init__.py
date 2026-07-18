"""Prompt Security Engine for Q-Guardian.

This package implements the first functional security plugin:
a modular, rule-based prompt analysis pipeline with extensibility
points for future ML and Quantum modules.

Modules:
    enums: PromptSeverity, PromptCategory, PromptDecision
    models: PromptAnalysis, PromptFeatures, PromptFinding, PromptRule
    pipeline: PromptNormalizer, PromptValidator, PromptFeatureExtractor, RuleEngine
    decision: SecurityDecisionEngine
    plugin: PromptScannerPlugin
    events: Security pipeline events
    config: PromptSecurityConfig
    extensibility: ABC interfaces for future modules
"""

from __future__ import annotations

from q_guardian.security.config import PromptSecurityConfig
from q_guardian.security.decision import SecurityDecisionEngine
from q_guardian.security.enums import (
    PromptCategory,
    PromptDecision,
    PromptSeverity,
    ValidationStatus,
)
from q_guardian.security.extensibility import (
    DetectionResult,
    FeatureProvider,
    PromptClassifier,
    PromptDetector,
    ThreatClassifier,
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
    # Enums
    "PromptCategory",
    "PromptDecision",
    "PromptSeverity",
    "ValidationStatus",
    # Models
    "PromptAnalysis",
    "PromptFeatures",
    "PromptFinding",
    "PromptRule",
    # Pipeline
    "PromptNormalizer",
    "PromptValidator",
    "PromptFeatureExtractor",
    "RuleEngine",
    # Decision
    "SecurityDecisionEngine",
    # Plugin
    "PromptScannerPlugin",
    # Config
    "PromptSecurityConfig",
    # Extensibility
    "DetectionResult",
    "FeatureProvider",
    "PromptClassifier",
    "PromptDetector",
    "ThreatClassifier",
]
