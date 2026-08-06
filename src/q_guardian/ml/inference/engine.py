"""Inference engine for ML threat detection."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.ml.base import ModelRegistry
from q_guardian.ml.config import MLConfig
from q_guardian.ml.data import InferenceResult

if TYPE_CHECKING:
    from q_guardian.security.extensibility import PromptDetector
    from q_guardian.security.models import PromptFeatures, PromptFinding

logger = structlog.get_logger("ml.inference")


class InferenceEngine:
    """Orchestrates inference across all registered detectors and classifiers.

    Runs all PromptDetector and PromptClassifier instances, merges their
    results, and produces a combined InferenceResult. Designed so that
    Module 6 (Quantum) can register new models without modifying this
    engine.
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        config: MLConfig | None = None,
    ) -> None:
        self._registry = registry or ModelRegistry()
        self._config = config or MLConfig()
        self._detectors: list[PromptDetector] = []
        self._classifiers: list[Any] = []

    def register_detector(self, detector: PromptDetector) -> None:
        """Register a detector for inference.

        Args:
            detector: The detector to register.
        """
        self._detectors.append(detector)
        logger.info("inference_detector_registered", detector=detector.name)

    def register_classifier(self, classifier: Any) -> None:
        """Register a classifier for inference.

        Args:
            classifier: The classifier to register.
        """
        self._classifiers.append(classifier)
        logger.info(
            "inference_classifier_registered", classifier=getattr(classifier, "name", "unknown")
        )

    def unregister_detector(self, name: str) -> bool:
        """Unregister a detector by name."""
        for i, det in enumerate(self._detectors):
            if det.name == name:
                self._detectors.pop(i)
                return True
        return False

    def unregister_classifier(self, name: str) -> bool:
        """Unregister a classifier by name."""
        for i, clf in enumerate(self._classifiers):
            if getattr(clf, "name", "") == name:
                self._classifiers.pop(i)
                return True
        return False

    @property
    def detector_count(self) -> int:
        return len(self._detectors)

    @property
    def classifier_count(self) -> int:
        return len(self._classifiers)

    async def run(
        self,
        prompt: str,
        features: PromptFeatures,
    ) -> InferenceResult:
        """Run inference across all registered detectors and classifiers.

        Args:
            prompt: The normalized prompt text.
            features: Pre-extracted prompt features.

        Returns:
            InferenceResult with merged findings and scores.
        """
        start = time.monotonic()
        all_findings: list[PromptFinding] = []
        risk_scores: list[float] = []
        confidences: list[float] = []

        # Run detectors
        for detector in self._detectors:
            try:
                result = await detector.detect(prompt, features)
                all_findings.extend(result.findings)
                if result.risk_score > 0:
                    risk_scores.append(result.risk_score)
                if result.confidence > 0:
                    confidences.append(result.confidence)
            except Exception:
                logger.error("inference_detector_error", detector=detector.name, exc_info=True)

        # Run classifiers
        category_scores: dict[str, float] = {}
        for classifier in self._classifiers:
            try:
                scores = await classifier.classify(prompt, features)
                for cat, score in scores.items():
                    if cat not in category_scores or score > category_scores[cat]:
                        category_scores[cat] = score
            except Exception:
                logger.error(
                    "inference_classifier_error",
                    classifier=getattr(classifier, "name", "unknown"),
                    exc_info=True,
                )

        elapsed_ms = (time.monotonic() - start) * 1000

        # Aggregate
        avg_risk = sum(risk_scores) / max(len(risk_scores), 1) if risk_scores else 0.0
        avg_confidence = sum(confidences) / max(len(confidences), 1) if confidences else 0.0
        max_category = (
            max(category_scores, key=lambda k: category_scores.get(k, 0.0))
            if category_scores
            else ""
        )
        max_category_score = category_scores.get(max_category, 0.0)

        # Determine if threat

        return InferenceResult(
            model_name="inference-engine",
            is_anomaly=avg_risk > self._config.anomaly_threshold,
            anomaly_score=avg_risk,
            predictions=category_scores,
            predicted_class=max_category,
            confidence=max(avg_confidence, max_category_score),
            risk_score=min(1.0, avg_risk),
            findings=all_findings,
            processing_time_ms=round(elapsed_ms, 2),
            metadata={
                "detector_count": len(self._detectors),
                "classifier_count": len(self._classifiers),
            },
        )
