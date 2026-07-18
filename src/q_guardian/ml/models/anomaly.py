"""Isolation Forest anomaly detector."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import structlog
from sklearn.ensemble import IsolationForest

from q_guardian.ml.base import BaseThreatModel
from q_guardian.ml.config import MLConfig
from q_guardian.ml.enums import ModelBackend, ModelStatus, ModelType
from q_guardian.ml.data import InferenceResult, ModelMetadata
from q_guardian.security.enums import PromptCategory, PromptDecision, PromptSeverity
from q_guardian.security.extensibility import DetectionResult, PromptDetector
from q_guardian.security.models import PromptFeatures, PromptFinding
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("ml.anomaly")


class IsolationForestDetector(PromptDetector, BaseThreatModel):
    """Anomaly detection using sklearn Isolation Forest.

    Detects prompts that deviate significantly from normal patterns.
    The anomaly score is mapped to a risk score for the decision engine.

    Implements both PromptDetector (for plugin integration) and
    BaseThreatModel (for generic model management).
    """

    def __init__(
        self,
        config: MLConfig | None = None,
        contamination: float = 0.1,
        n_estimators: int = 100,
    ) -> None:
        self._config = config or MLConfig()
        self._contamination = contamination
        self._n_estimators = n_estimators
        self._model: IsolationForest | None = None
        self._threshold = self._config.anomaly_threshold
        self._metadata = ModelMetadata(
            name="isolation-forest",
            model_type=ModelType.ANOMALY_DETECTION,
            backend=ModelBackend.SKLEARN,
            description="Isolation Forest anomaly detector for prompts",
        )

    @property
    def name(self) -> str:
        return "isolation-forest"

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    @property
    def model(self) -> IsolationForest | None:
        return self._model

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def train(self, X: list[list[float]]) -> None:
        """Train the Isolation Forest on feature vectors.

        Args:
            X: 2D array of feature vectors.
        """
        arr = np.array(X, dtype=np.float64)
        self._model = IsolationForest(
            contamination=self._contamination,
            n_estimators=self._n_estimators,
            random_state=self._config.random_state,
        )
        self._model.fit(arr)
        self._metadata.status = ModelStatus.READY
        self._metadata.training_samples = len(X)
        self._metadata.feature_count = arr.shape[1] if arr.ndim == 2 else 0
        logger.info("isolation_forest_trained", samples=len(X), features=arr.shape[1])

    async def detect(self, prompt: str, features: PromptFeatures) -> DetectionResult:
        """Detect anomalies in a prompt.

        Args:
            prompt: The normalized prompt text.
            features: Pre-extracted prompt features.

        Returns:
            DetectionResult with anomaly findings.
        """
        start = time.monotonic()
        findings: list[PromptFinding] = []
        risk_score = 0.0
        confidence = 0.0
        is_anomaly = False

        if self._model is not None:
            feature_vector = self._extract_vector(features)
            arr = np.array([feature_vector], dtype=np.float64)
            raw_score = self._model.decision_function(arr)[0]
            prediction = self._model.predict(arr)[0]

            # decision_function: lower = more anomalous
            # Map to 0-1 range: score < 0 → anomaly
            anomaly_score = max(0.0, min(1.0, 0.5 - raw_score))
            is_anomaly = prediction == -1

            if is_anomaly:
                risk_score = anomaly_score
                confidence = min(1.0, anomaly_score * 1.5)
                findings.append(PromptFinding(
                    rule_id="isolation-forest",
                    rule_name="Isolation Forest Anomaly Detection",
                    category=PromptCategory.UNKNOWN,
                    severity=PromptSeverity.MEDIUM if anomaly_score < 0.7 else PromptSeverity.HIGH,
                    description=f"Anomalous prompt detected (score: {anomaly_score:.3f})",
                    confidence=confidence,
                    metadata={"anomaly_score": anomaly_score, "raw_score": float(raw_score)},
                ))

        elapsed_ms = (time.monotonic() - start) * 1000

        return DetectionResult(
            detector_name=self.name,
            findings=findings,
            risk_score=risk_score,
            confidence=confidence,
            metadata={"is_anomaly": is_anomaly, "processing_time_ms": elapsed_ms},
        )

    async def predict(self, features: list[float]) -> dict[str, Any]:
        """Run prediction on a numeric feature vector.

        Args:
            features: Numeric feature vector.

        Returns:
            Dictionary with prediction results.
        """
        if self._model is None:
            return {"is_anomaly": False, "anomaly_score": 0.0}

        arr = np.array([features], dtype=np.float64)
        raw_score = float(self._model.decision_function(arr)[0])
        prediction = int(self._model.predict(arr)[0])
        anomaly_score = max(0.0, min(1.0, 0.5 - raw_score))

        return {
            "is_anomaly": prediction == -1,
            "anomaly_score": anomaly_score,
            "raw_score": raw_score,
        }

    def _extract_vector(self, features: PromptFeatures) -> list[float]:
        """Extract a numeric vector from PromptFeatures."""
        return [
            float(features.length),
            float(features.word_count),
            float(features.line_count),
            float(features.token_estimate),
            features.entropy,
            features.uppercase_ratio,
            features.digit_ratio,
            float(features.special_char_count),
            float(features.code_block_count),
            float(features.url_count),
            float(len(features.suspicious_keywords)),
            float(len(features.repeated_patterns)),
        ]

    def health(self) -> dict[str, Any]:
        """Return detector health status."""
        base = super().health()
        base["is_trained"] = self.is_trained
        base["contamination"] = self._contamination
        return base
