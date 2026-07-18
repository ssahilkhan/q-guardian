"""Extensibility interfaces for future ML and Quantum modules.

Defines abstract base classes that future modules will implement
to plug into the prompt security pipeline.

Module 5 (Machine Learning) will implement:
  - PromptDetector: ML-based prompt classification
  - PromptClassifier: Multi-class threat classification
  - FeatureProvider: Custom feature extraction for ML models

Module 6 (Quantum Analysis) will implement:
  - ThreatClassifier: Quantum-enhanced threat classification
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.security.enums import PromptDecision, PromptSeverity
from q_guardian.security.models import PromptFeatures, PromptFinding


class DetectionResult(BaseModel):
    """Result from an external detector (ML, Quantum, etc.)."""

    model_config = ConfigDict(populate_by_name=True)

    detector_name: str = Field(description="Name of the detector")
    findings: list[PromptFinding] = Field(default_factory=list, description="Detected findings")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Detector risk score")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Detection confidence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class PromptDetector(ABC):
    """Abstract base class for ML-based prompt detectors.

    Future Module 5 (Machine Learning) will implement this interface
    using models like XGBoost, Isolation Forest, or transformer-based
    classifiers.

    Integration point:
      The PromptScannerPlugin will call detect() and merge
      DetectionResult.findings into the analysis before
      SecurityDecisionEngine runs.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the detector name."""

    @abstractmethod
    async def detect(self, prompt: str, features: PromptFeatures) -> DetectionResult:
        """Analyze a prompt for security threats.

        Args:
            prompt: The normalized prompt text.
            features: Pre-extracted prompt features.

        Returns:
            DetectionResult with findings and risk score.
        """

    def health(self) -> dict[str, Any]:
        """Return detector health status.

        Returns:
            Dictionary with health information.
        """
        return {"status": "healthy", "detector": self.name}


class PromptClassifier(ABC):
    """Abstract base class for multi-class threat classification.

    Future Module 5 will implement this using trained classifiers
    to categorize prompts into threat types with probabilities.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the classifier name."""

    @abstractmethod
    async def classify(
        self, prompt: str, features: PromptFeatures
    ) -> dict[str, float]:
        """Classify a prompt into threat categories with probabilities.

        Args:
            prompt: The normalized prompt text.
            features: Pre-extracted prompt features.

        Returns:
            Dictionary mapping category names to probability scores.
        """


class FeatureProvider(ABC):
    """Abstract base class for custom feature extraction.

    Future Module 5 will implement this to provide ML-specific
    features (embeddings, tokenization, attention patterns, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the feature provider name."""

    @abstractmethod
    async def extract_features(
        self, prompt: str, base_features: PromptFeatures
    ) -> dict[str, Any]:
        """Extract additional features for ML models.

        Args:
            prompt: The normalized prompt text.
            base_features: Features from PromptFeatureExtractor.

        Returns:
            Dictionary of additional features.
        """


class ThreatClassifier(ABC):
    """Abstract base class for quantum-enhanced threat classification.

    Future Module 6 (Quantum Analysis) will implement this using
    quantum machine learning algorithms like QSVM or quantum
    neural networks.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the classifier name."""

    @abstractmethod
    async def classify_quantum(
        self, prompt: str, features: PromptFeatures
    ) -> DetectionResult:
        """Classify threats using quantum analysis.

        Args:
            prompt: The normalized prompt text.
            features: Pre-extracted prompt features.

        Returns:
            DetectionResult with quantum-enhanced findings.
        """
