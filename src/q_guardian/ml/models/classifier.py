"""Random Forest and XGBoost threat classifiers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import structlog
from sklearn.ensemble import RandomForestClassifier

from q_guardian.ml.base import (
    BaseThreatModel,
    extract_core_features,
    validate_feature_dimension,
)
from q_guardian.ml.config import MLConfig
from q_guardian.ml.data import ModelMetadata
from q_guardian.ml.enums import ModelBackend, ModelStatus, ModelType
from q_guardian.security.enums import PromptCategory
from q_guardian.security.extensibility import PromptClassifier

if TYPE_CHECKING:
    from q_guardian.security.models import PromptFeatures

logger = structlog.get_logger("ml.classifier")

# Threat categories for classification
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

_CATEGORY_MAP = {
    "benign": PromptCategory.UNKNOWN,
    "prompt_injection": PromptCategory.PROMPT_INJECTION,
    "jailbreak": PromptCategory.JAILBREAK,
    "role_manipulation": PromptCategory.ROLE_MANIPULATION,
    "system_prompt_leak": PromptCategory.SYSTEM_PROMPT_LEAK,
    "data_exfiltration": PromptCategory.DATA_EXFILTRATION,
    "excessive_encoding": PromptCategory.EXCESSIVE_ENCODING,
    "suspicious_formatting": PromptCategory.SUSPICIOUS_FORMATTING,
}


class RandomForestThreatClassifier(PromptClassifier, BaseThreatModel):
    """Multi-class threat classification using sklearn Random Forest.

    Classifies prompts into threat categories with probability scores.

    Implements both PromptClassifier (for plugin integration) and
    BaseThreatModel (for generic model management).
    """

    def __init__(
        self,
        config: MLConfig | None = None,
        n_estimators: int = 100,
        max_depth: int | None = None,
        class_weight: str | dict[str, float] | None = None,
    ) -> None:
        self._config = config or MLConfig()
        self._n_estimators = n_estimators
        self._max_depth = max_depth
        self._class_weight = class_weight
        self._model: RandomForestClassifier | None = None
        self._classes: list[str] = list(THREAT_CATEGORIES)
        self._metadata = ModelMetadata(
            name="random-forest-classifier",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.SKLEARN,
            description="Random Forest multi-class threat classifier",
        )

    @property
    def name(self) -> str:
        return "random-forest-classifier"

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    @property
    def model(self) -> RandomForestClassifier | None:
        return self._model

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    @property
    def classes(self) -> list[str]:
        return list(self._classes)

    def train(self, x: list[list[float]], y: list[int] | None = None) -> None:
        """Train the Random Forest classifier.

        Args:
            x: 2D array of feature vectors.
            y: Integer class labels.
        """
        if y is None:
            raise ValueError("y labels are required for supervised classification")
        x_arr = np.array(x, dtype=np.float64)
        arr_y = np.array(y, dtype=np.int32)

        self._model = RandomForestClassifier(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            random_state=self._config.random_state,
            class_weight=self._class_weight,
        )
        self._model.fit(x_arr, arr_y)

        if hasattr(self._model, "classes_"):
            self._classes = [THREAT_CATEGORIES[int(c)] for c in self._model.classes_]

        self._metadata.status = ModelStatus.READY
        self._metadata.training_samples = len(x)
        self._metadata.feature_count = x_arr.shape[1] if x_arr.ndim == 2 else 0
        logger.info("random_forest_trained", samples=len(x), classes=len(self._classes))

    async def classify(self, prompt: str, features: PromptFeatures) -> dict[str, float]:
        """Classify a prompt into threat categories.

        Args:
            prompt: The normalized prompt text.
            features: Pre-extracted prompt features.

        Returns:
            Dictionary mapping category names to probability scores.
        """
        if self._model is None:
            return dict.fromkeys(THREAT_CATEGORIES, 0.0)

        vector = self._extract_vector(features)
        expected = int(getattr(self._model, "n_features_in_", len(vector)))
        if expected != len(vector):
            validate_feature_dimension(self.name, expected, len(vector))
        arr = np.array([vector], dtype=np.float64)
        probas = self._model.predict_proba(arr)[0]

        return {self._classes[i]: float(probas[i]) for i in range(len(self._classes))}

    async def predict(self, features: list[float]) -> dict[str, Any]:
        """Run prediction on a numeric feature vector.

        Args:
            features: Numeric feature vector.

        Returns:
            Dictionary with prediction results.
        """
        if self._model is None:
            return {"predicted_class": "unknown", "probabilities": {}, "confidence": 0.0}

        arr = np.array([features], dtype=np.float64)
        probas = self._model.predict_proba(arr)[0]
        predicted_idx = int(np.argmax(probas))

        return {
            "predicted_class": self._classes[predicted_idx],
            "probabilities": {
                self._classes[i]: float(probas[i]) for i in range(len(self._classes))
            },
            "confidence": float(probas[predicted_idx]),
        }

    def _extract_vector(self, features: PromptFeatures) -> list[float]:
        """Extract the canonical 12-dim vector (see ml.base.CORE_FEATURE_NAMES)."""
        return extract_core_features(features)

    def health(self) -> dict[str, Any]:
        base = super().health()
        base["is_trained"] = self.is_trained
        base["class_count"] = len(self._classes)
        return base


class XGBoostThreatClassifier(PromptClassifier, BaseThreatModel):
    """Multi-class threat classification using XGBoost.

    Optional classifier — only available if xgboost is installed.
    Falls back gracefully if XGBoost is not installed.
    """

    def __init__(
        self,
        config: MLConfig | None = None,
        n_estimators: int = 100,
        max_depth: int = 6,
    ) -> None:
        self._config = config or MLConfig()
        self._n_estimators = n_estimators
        self._max_depth = max_depth
        self._model: Any = None
        self._classes: list[str] = list(THREAT_CATEGORIES)
        self._available = False
        self._metadata = ModelMetadata(
            name="xgboost-classifier",
            model_type=ModelType.CLASSIFICATION,
            backend=ModelBackend.XGBOOST,
            description="XGBoost multi-class threat classifier (optional)",
        )

        try:
            import xgboost  # noqa: F401

            self._available = True
        except ImportError:
            self._metadata.status = ModelStatus.UNLOADED
            logger.warning("xgboost_not_available")

    @property
    def name(self) -> str:
        return "xgboost-classifier"

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    @property
    def model(self) -> Any:
        return self._model

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def classes(self) -> list[str]:
        return list(self._classes)

    def train(self, x: list[list[float]], y: list[int] | None = None) -> None:
        """Train the XGBoost classifier."""
        if not self._available:
            msg = "XGBoost is not installed"
            raise RuntimeError(msg)
        if y is None:
            raise ValueError("y labels are required for supervised classification")

        import xgboost as xgb

        x_arr = np.array(x, dtype=np.float32)
        arr_y = np.array(y, dtype=np.int32)

        self._model = xgb.XGBClassifier(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            random_state=self._config.random_state,
            use_label_encoder=False,
            eval_metric="mlogloss",
            verbosity=0,
        )
        self._model.fit(x_arr, arr_y)

        if hasattr(self._model, "classes_"):
            self._classes = [THREAT_CATEGORIES[int(c)] for c in self._model.classes_]

        self._metadata.status = ModelStatus.READY
        self._metadata.training_samples = len(x)
        self._metadata.feature_count = x_arr.shape[1] if x_arr.ndim == 2 else 0
        logger.info("xgboost_trained", samples=len(x), classes=len(self._classes))

    async def classify(self, prompt: str, features: PromptFeatures) -> dict[str, float]:
        """Classify a prompt into threat categories."""
        if self._model is None:
            return dict.fromkeys(THREAT_CATEGORIES, 0.0)

        vector = self._extract_vector(features)
        expected = int(getattr(self._model, "n_features_in_", len(vector)))
        if expected != len(vector):
            validate_feature_dimension(self.name, expected, len(vector))
        arr = np.array([vector], dtype=np.float32)
        probas = self._model.predict_proba(arr)[0]

        return {self._classes[i]: float(probas[i]) for i in range(len(self._classes))}

    async def predict(self, features: list[float]) -> dict[str, Any]:
        """Run prediction on a numeric feature vector."""
        if self._model is None:
            return {"predicted_class": "unknown", "probabilities": {}, "confidence": 0.0}

        arr = np.array([features], dtype=np.float32)
        probas = self._model.predict_proba(arr)[0]
        predicted_idx = int(np.argmax(probas))

        return {
            "predicted_class": self._classes[predicted_idx],
            "probabilities": {
                self._classes[i]: float(probas[i]) for i in range(len(self._classes))
            },
            "confidence": float(probas[predicted_idx]),
        }

    def _extract_vector(self, features: PromptFeatures) -> list[float]:
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
        base = super().health()
        base["available"] = self._available
        base["is_trained"] = self.is_trained
        return base
