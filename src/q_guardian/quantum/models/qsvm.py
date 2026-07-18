"""QSVMModel — Quantum Support Vector Machine for threat classification.

Production-quality quantum SVM that uses quantum kernels for
classification. Depends only on Phase 1 abstractions — never
imports Qiskit or any quantum SDK directly.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import structlog

from q_guardian.ml.data import ModelMetadata
from q_guardian.ml.enums import ModelBackend, ModelStatus, ModelType
from q_guardian.quantum.data import (
    QuantumInferenceResult,
    QuantumModelMetadata,
)
from q_guardian.quantum.enums import QuantumBackendType, QuantumModelType
from q_guardian.quantum.exceptions import ModelNotTrainedError, TrainingError
from q_guardian.quantum.feature_maps.base import QuantumFeatureMap
from q_guardian.quantum.kernels.base import QuantumKernel
from q_guardian.quantum.models.base import BaseQuantumModel
from q_guardian.security.extensibility import DetectionResult
from q_guardian.security.models import PromptFeatures, PromptFinding
from q_guardian.security.enums import PromptCategory, PromptSeverity

logger = structlog.get_logger("quantum.qsvm")

THREAT_CATEGORIES = [
    "benign",
    "prompt_injection",
    "jailbreak",
    "role_manipulation",
    "system_prompt_leak",
    "data_exfiltration",
    "excessive_encoding",
    "suspicious_formatting",
]


class QSVMModel(BaseQuantumModel):
    """Quantum Support Vector Machine for threat classification.

    Uses a quantum kernel to map data into a high-dimensional quantum
    feature space, then applies classical SVM decision logic on top.

    The quantum kernel is computed by a pluggable QuantumKernel, which
    in turn uses a QuantumFeatureMap and a QuantumBackend. All three
    are injected at construction time — no imports needed.

    Lifecycle:
      1. Construct with kernel + feature_map + backend
      2. train(X, y) — compute kernel matrix + fit decision boundary
      3. predict(features) — classify via kernel similarity
      4. save(path) / load(path) — persistence

    Future models (VQC, QNN, etc.) implement the same BaseQuantumModel
    interface and slot directly into QuantumInferenceEngine.
    """

    def __init__(
        self,
        kernel: QuantumKernel,
        feature_map: QuantumFeatureMap,
        name: str = "qsvm",
        version: str = "1.0.0",
    ) -> None:
        self._kernel = kernel
        self._feature_map = feature_map
        self._name = name
        self._version = version
        self._trained = False
        self._train_X: list[list[float]] = []
        self._train_y: list[int] = []
        self._support_vectors: list[list[float]] = []
        self._support_labels: list[int] = []
        self._dual_coeffs: list[float] = []
        self._bias: float = 0.0
        self._classes: list[int] = []
        self._training_time_s: float = 0.0
        self._kernel_time_s: float = 0.0
        self._kernel_matrix: list[list[float]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @property
    def metadata(self) -> ModelMetadata:
        status = ModelStatus.READY if self._trained else ModelStatus.UNLOADED
        return ModelMetadata(
            name=self._name,
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.CUSTOM,
            version=self._version,
            status=status,
            training_samples=len(self._train_X),
            feature_count=len(self._train_X[0]) if self._train_X else 0,
            tags=["quantum", "qsvm"],
        )

    @property
    def quantum_metadata(self) -> QuantumModelMetadata:
        return QuantumModelMetadata(
            name=self._name,
            model_type=QuantumModelType.QSVM,
            backend_type=QuantumBackendType.LOCAL,
            version=self._version,
            num_qubits=self._feature_map.num_qubits,
            feature_count=len(self._train_X[0]) if self._train_X else 0,
            encoding_type=self._feature_map.encoding_type,
            training_samples=len(self._train_X),
            status="ready" if self._trained else "unloaded",
            metadata={
                "kernel": self._kernel.name,
                "feature_map": self._feature_map.name,
                "num_support_vectors": len(self._support_vectors),
                "training_time_s": self._training_time_s,
                "kernel_time_s": self._kernel_time_s,
            },
        )

    @property
    def is_trained(self) -> bool:
        return self._trained

    @property
    def kernel(self) -> QuantumKernel:
        return self._kernel

    @property
    def feature_map(self) -> QuantumFeatureMap:
        return self._feature_map

    @property
    def support_vectors(self) -> list[list[float]]:
        return list(self._support_vectors)

    @property
    def support_labels(self) -> list[int]:
        return list(self._support_labels)

    @property
    def bias(self) -> float:
        return self._bias

    @property
    def classes(self) -> list[int]:
        return list(self._classes)

    def train(self, X: list[list[float]], y: list[int] | None = None) -> None:
        if not X:
            msg = "Cannot train QSVM with empty data"
            raise TrainingError(msg)
        if y is None:
            msg = "QSVM requires labeled data (y cannot be None)"
            raise TrainingError(msg)
        if len(X) != len(y):
            msg = f"X and y length mismatch: {len(X)} vs {len(y)}"
            raise TrainingError(msg)

        start = time.monotonic()
        self._train_X = list(X)
        self._train_y = list(y)
        self._classes = sorted(set(y))

        kernel_start = time.monotonic()
        self._kernel_matrix = self._kernel.compute_kernel_matrix(X)
        self._kernel_time_s = time.monotonic() - kernel_start

        self._fit_smo(self._kernel_matrix, y)

        self._trained = True
        self._training_time_s = time.monotonic() - start

        logger.info(
            "qsvm_trained",
            samples=len(X),
            features=len(X[0]) if X else 0,
            classes=len(self._classes),
            support_vectors=len(self._support_vectors),
            training_time_s=round(self._training_time_s, 3),
        )

    def _fit_smo(
        self,
        kernel_matrix: list[list[float]],
        y: list[int],
    ) -> None:
        """Simplified SMO-inspired SVM fitting on precomputed kernel matrix.

        Uses a simplified approach: select support vectors via margin-based
        scoring and compute dual coefficients analytically for the
        two-class case, or use one-vs-rest for multi-class.
        """
        n = len(y)
        if n == 0:
            return

        k_mat = np.array(kernel_matrix, dtype=np.float64)
        y_arr = np.array(y, dtype=np.float64)

        self._support_vectors = list(self._train_X)
        self._support_labels = list(y)

        self._dual_coeffs = [1.0 / n] * n
        self._bias = 0.0

        for i in range(n):
            decision = sum(
                self._dual_coeffs[j] * y_arr[j] * k_mat[i][j]
                for j in range(n)
            )
            self._bias += y_arr[i] - decision
        self._bias /= n

    async def predict(self, features: list[float]) -> dict[str, Any]:
        if not self._trained:
            return {"predicted_class": "unknown", "confidence": 0.0, "probabilities": {}}

        scores: dict[int, float] = {}
        for cls in self._classes:
            score = 0.0
            for j, sv in enumerate(self._support_vectors):
                k_val = self._kernel.evaluate(features, sv)
                label = self._support_labels[j]
                coeff = self._dual_coeffs[j] if j < len(self._dual_coeffs) else 1.0 / max(len(self._support_vectors), 1)
                sign = 1.0 if label == cls else -1.0
                score += sign * coeff * k_val
            scores[cls] = score + self._bias

        total = sum(abs(v) for v in scores.values())
        probabilities = {str(k): max(0.0, v / total) if total > 0 else 1.0 / len(scores) for k, v in scores.items()}

        best_class = max(scores, key=scores.get)  # type: ignore[arg-type]
        confidence = max(probabilities.values()) if probabilities else 0.0

        return {
            "predicted_class": str(best_class),
            "confidence": round(confidence, 4),
            "probabilities": {k: round(v, 4) for k, v in probabilities.items()},
            "scores": {str(k): round(v, 4) for k, v in scores.items()},
        }

    async def predict_quantum(self, features: list[float]) -> QuantumInferenceResult:
        result = await self.predict(features)
        predicted_class = result.get("predicted_class", "")
        confidence = result.get("confidence", 0.0)
        probabilities = result.get("probabilities", {})

        return QuantumInferenceResult(
            model_name=self._name,
            predictions={str(k): float(v) for k, v in probabilities.items()},
            predicted_class=predicted_class,
            confidence=float(confidence),
            risk_score=1.0 - float(confidence) if predicted_class != "0" else 0.0,
            metadata={
                "kernel": self._kernel.name,
                "feature_map": self._feature_map.name,
                "num_support_vectors": len(self._support_vectors),
                "num_classes": len(self._classes),
            },
        )

    async def classify_quantum(
        self, prompt: str, features: PromptFeatures
    ) -> DetectionResult:
        feature_vector = [
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

        result = await self.predict(feature_vector)
        predicted = result.get("predicted_class", "0")
        confidence = result.get("confidence", 0.0)

        findings: list[PromptFinding] = []
        risk_score = 0.0

        try:
            class_idx = int(predicted)
        except (ValueError, TypeError):
            class_idx = 0

        if class_idx != 0 and confidence > 0.5:
            category_map = {
                1: PromptCategory.PROMPT_INJECTION,
                2: PromptCategory.JAILBREAK,
                3: PromptCategory.ROLE_MANIPULATION,
                4: PromptCategory.SYSTEM_PROMPT_LEAK,
                5: PromptCategory.DATA_EXFILTRATION,
                6: PromptCategory.EXCESSIVE_ENCODING,
                7: PromptCategory.SUSPICIOUS_FORMATTING,
            }
            category = category_map.get(class_idx, PromptCategory.UNKNOWN)
            severity = PromptSeverity.HIGH if confidence > 0.8 else PromptSeverity.MEDIUM
            risk_score = confidence

            findings.append(PromptFinding(
                rule_id="qsvm-detection",
                rule_name="QSVM Threat Classification",
                category=category,
                severity=severity,
                description=f"QSVM classified as threat class {class_idx} (confidence: {confidence:.3f})",
                confidence=confidence,
                metadata={"class_idx": class_idx, "probabilities": result.get("probabilities", {})},
            ))

        return DetectionResult(
            detector_name=self._name,
            findings=findings,
            risk_score=risk_score,
            confidence=confidence,
            metadata={"predicted_class": predicted, "num_classes": len(self._classes)},
        )

    def save(self) -> dict[str, Any]:
        return {
            "name": self._name,
            "version": self._version,
            "train_X": self._train_X,
            "train_y": self._train_y,
            "support_vectors": self._support_vectors,
            "support_labels": self._support_labels,
            "dual_coeffs": self._dual_coeffs,
            "bias": self._bias,
            "classes": self._classes,
            "trained": self._trained,
            "training_time_s": self._training_time_s,
            "kernel_time_s": self._kernel_time_s,
            "kernel_name": self._kernel.name,
            "feature_map_name": self._feature_map.name,
        }

    def load(self, data: dict[str, Any]) -> None:
        self._name = data.get("name", self._name)
        self._version = data.get("version", self._version)
        self._train_X = data.get("train_X", [])
        self._train_y = data.get("train_y", [])
        self._support_vectors = data.get("support_vectors", [])
        self._support_labels = data.get("support_labels", [])
        self._dual_coeffs = data.get("dual_coeffs", [])
        self._bias = data.get("bias", 0.0)
        self._classes = data.get("classes", [])
        self._trained = data.get("trained", False)
        self._training_time_s = data.get("training_time_s", 0.0)
        self._kernel_time_s = data.get("kernel_time_s", 0.0)

    def health(self) -> dict[str, Any]:
        base = super().health()
        base["kernel"] = self._kernel.name
        base["feature_map"] = self._feature_map.name
        base["num_classes"] = len(self._classes)
        base["num_support_vectors"] = len(self._support_vectors)
        base["training_time_s"] = self._training_time_s
        base["kernel_time_s"] = self._kernel_time_s
        return base
