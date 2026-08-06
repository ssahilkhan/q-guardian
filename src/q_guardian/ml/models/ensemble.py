"""Ensemble detector combining multiple models."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.ml.base import BaseThreatModel
from q_guardian.ml.config import MLConfig
from q_guardian.ml.data import ModelMetadata
from q_guardian.ml.enums import ModelBackend, ModelType
from q_guardian.security.enums import PromptSeverity
from q_guardian.security.extensibility import DetectionResult, PromptDetector

if TYPE_CHECKING:
    from q_guardian.security.models import PromptFeatures, PromptFinding

logger = structlog.get_logger("ml.ensemble")


class EnsembleDetector(PromptDetector, BaseThreatModel):
    """Ensemble detector that combines multiple PromptDetector instances.

    Uses weighted voting to combine anomaly scores and findings
    from multiple detectors. Supports dynamic weight configuration.

    Module 6 (Quantum) can register a ThreatClassifier that
    implements PromptDetector and be seamlessly added to the ensemble.
    """

    def __init__(
        self,
        detectors: list[PromptDetector] | None = None,
        weights: dict[str, float] | None = None,
        config: MLConfig | None = None,
    ) -> None:
        self._config = config or MLConfig()
        self._detectors: dict[str, PromptDetector] = {}
        self._weights: dict[str, float] = weights or {}
        self._default_weight = 1.0
        self._metadata = ModelMetadata(
            name="ensemble-detector",
            model_type=ModelType.ENSEMBLE,
            backend=ModelBackend.CUSTOM,
            description="Ensemble combining multiple threat detectors",
        )

        if detectors:
            for det in detectors:
                self.add_detector(det, self._weights.get(det.name, self._default_weight))

    @property
    def name(self) -> str:
        return "ensemble-detector"

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    @property
    def detectors(self) -> dict[str, PromptDetector]:
        return dict(self._detectors)

    @property
    def detector_count(self) -> int:
        return len(self._detectors)

    def add_detector(self, detector: PromptDetector, weight: float = 1.0) -> None:
        """Add a detector to the ensemble.

        Args:
            detector: The detector instance.
            weight: Weight for this detector's votes.
        """
        self._detectors[detector.name] = detector
        self._weights[detector.name] = weight
        logger.info("ensemble_detector_added", detector=detector.name, weight=weight)

    def remove_detector(self, name: str) -> bool:
        """Remove a detector from the ensemble.

        Args:
            name: Detector name.

        Returns:
            True if the detector was found and removed.
        """
        if name in self._detectors:
            del self._detectors[name]
            self._weights.pop(name, None)
            return True
        return False

    def set_weight(self, name: str, weight: float) -> None:
        """Set the weight for a detector.

        Args:
            name: Detector name.
            weight: New weight value.
        """
        self._weights[name] = weight

    async def detect(self, prompt: str, features: PromptFeatures) -> DetectionResult:
        """Run all detectors and combine results with weighted voting.

        Args:
            prompt: The normalized prompt text.
            features: Pre-extracted prompt features.

        Returns:
            DetectionResult with combined findings.
        """
        start = time.monotonic()
        all_findings: list[PromptFinding] = []
        weighted_scores: list[float] = []
        total_weight = 0.0

        for det_name, detector in self._detectors.items():
            try:
                weight = self._weights.get(det_name, self._default_weight)
                result = await detector.detect(prompt, features)

                for finding in result.findings:
                    finding.metadata["source_detector"] = det_name
                    all_findings.append(finding)

                weighted_scores.append(result.risk_score * weight)
                total_weight += weight
            except Exception:
                logger.error("ensemble_detector_error", detector=det_name, exc_info=True)

        elapsed_ms = (time.monotonic() - start) * 1000

        # Weighted average risk score
        combined_risk = sum(weighted_scores) / max(total_weight, 1e-10) if total_weight > 0 else 0.0

        # Deduplicate findings by rule_id
        deduplicated = self._deduplicate_findings(all_findings)

        # Combined confidence
        confidences = []
        for det_name, detector in self._detectors.items():
            try:
                result = await detector.detect(prompt, features)
                if result.confidence > 0:
                    confidences.append(
                        result.confidence * self._weights.get(det_name, self._default_weight)
                    )
            except Exception:
                pass

        avg_confidence = (
            sum(confidences) / max(total_weight, 1e-10) if confidences and total_weight > 0 else 0.0
        )

        return DetectionResult(
            detector_name=self.name,
            findings=deduplicated,
            risk_score=min(1.0, combined_risk),
            confidence=min(1.0, avg_confidence),
            metadata={
                "detector_count": len(self._detectors),
                "total_weight": total_weight,
                "processing_time_ms": elapsed_ms,
            },
        )

    async def predict(self, features: list[float]) -> dict[str, Any]:
        """Run prediction across all detectors.

        Args:
            features: Numeric feature vector.

        Returns:
            Combined prediction from all detectors.
        """
        results: dict[str, Any] = {}
        for det_name, detector in self._detectors.items():
            try:
                predict_fn = getattr(detector, "predict", None)
                if predict_fn is None:
                    results[det_name] = {"error": "detector does not support vector prediction"}
                    continue
                result = await predict_fn(features)
                results[det_name] = result
            except Exception:
                results[det_name] = {"error": "prediction failed"}

        return results

    def _deduplicate_findings(self, findings: list[PromptFinding]) -> list[PromptFinding]:
        """Deduplicate findings by rule_id, keeping highest severity."""
        severity_order = {
            PromptSeverity.INFO: 0,
            PromptSeverity.LOW: 1,
            PromptSeverity.MEDIUM: 2,
            PromptSeverity.HIGH: 3,
            PromptSeverity.CRITICAL: 4,
        }
        best: dict[str, PromptFinding] = {}
        for f in findings:
            key = f.rule_id
            if key not in best or severity_order.get(f.severity, 0) > severity_order.get(
                best[key].severity, 0
            ):
                best[key] = f
        return list(best.values())

    def health(self) -> dict[str, Any]:
        base = super().health()
        base["detector_count"] = self.detector_count
        base["detectors"] = list(self._detectors.keys())
        return base
