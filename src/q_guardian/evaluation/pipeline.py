"""End-to-end evaluator for the hybrid detection pipeline.

Builds the real Q-Guardian pipeline (normalizer -> feature extractor ->
rule engine -> classical ML -> quantum QSVM -> hybrid fusion) using the
framework's own provider adapters, fits it on a training set, and scores
it on a test set. Every provider (rule engine, isolation forest, random
forest, XGBoost, QSVM) and the fused result is measured with the same
continuous threat score, enabling per-component comparison and ablation.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog
from sklearn.preprocessing import StandardScaler

from q_guardian.evaluation.metrics import detection_metrics
from q_guardian.ml.feature_pipeline import MLFeatureProvider
from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import (
    RandomForestThreatClassifier,
    XGBoostThreatClassifier,
)
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.fusion.adapters import (
    ClassicalModelProvider,
    QuantumModelProvider,
    RuleEngineProvider,
)
from q_guardian.quantum.fusion.engine import HybridFusionEngine
from q_guardian.quantum.fusion.strategies.weighted_voting import (
    WeightedVotingStrategy,
)
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.models.qsvm import QSVMModel
from q_guardian.security.pipeline import (
    PromptFeatureExtractor,
    PromptNormalizer,
    RuleEngine,
)

if TYPE_CHECKING:
    from q_guardian.evaluation.dataset import PromptBenchmarkDataset
    from q_guardian.quantum.fusion.providers import PredictionProvider

logger = structlog.get_logger("evaluation.pipeline")

# Provider identifiers as registered on the fusion engine.
RULE_PROVIDER = "rule-engine"
ANOMALY_PROVIDER = "isolation-forest"
CLASSIFIER_PROVIDER = "random-forest"
XGBOOST_PROVIDER = "xgboost"
QUANTUM_PROVIDER = "qsvm"

# Default fusion weights mirror the production harness configuration. The
# classical classifiers (random forest + xgboost) carry the bulk of the vote;
# rule engine, isolation forest and the optional QSVM are supporting sources.
DEFAULT_PROVIDER_WEIGHTS: dict[str, float] = {
    RULE_PROVIDER: 0.15,
    ANOMALY_PROVIDER: 0.10,
    CLASSIFIER_PROVIDER: 0.35,
    XGBOOST_PROVIDER: 0.25,
    QUANTUM_PROVIDER: 0.15,
}

ALL_PROVIDERS = [
    RULE_PROVIDER,
    ANOMALY_PROVIDER,
    CLASSIFIER_PROVIDER,
    XGBOOST_PROVIDER,
    QUANTUM_PROVIDER,
]

# Supported probability calibration methods (fitted on validation only).
CALIBRATION_METHODS = ("platt", "isotonic")


def apply_probability_calibration(
    calibrator: tuple[str, Any] | None,
    scores: list[float],
) -> list[float]:
    """Map raw model scores through a fitted calibrator.

    Args:
        calibrator: ``(method, fitted_model)`` as stored in
            ``HybridEvaluator.calibrators`` — method is ``"platt"``
            (LogisticRegression on the raw score) or ``"isotonic"``.
        scores: Raw malicious-class probabilities.

    Returns:
        Calibrated probabilities (same order/length).
    """
    import numpy as np

    if calibrator is None:
        return list(scores)
    method, model = calibrator
    arr = np.asarray(scores, dtype=np.float64)
    if method == "platt":
        return [float(v) for v in model.predict_proba(arr.reshape(-1, 1))[:, 1]]
    if method == "isotonic":
        return [float(v) for v in model.predict(arr.ravel())]
    msg = f"unsupported calibration method: {method!r}"
    raise ValueError(msg)


class HybridEvaluator:
    """Fits and evaluates the hybrid detection pipeline.

    Args:
        quantum: Whether to train and use the quantum QSVM provider.
        quantum_shots: Simulator shots per kernel evaluation.
        quantum_feature_count: Number of leading features used for angle
            encoding (qubit limit).
        quantum_cap: Optional cap on training samples given to the QSVM
            (the kernel matrix is O(n^2)).
        n_estimators: Estimator count for the classical models.
        contamination: Isolation Forest contamination.
        provider_weights: Fusion weights keyed by provider id.
        random_state: Seed for reproducible model training.
    """

    def __init__(
        self,
        *,
        quantum: bool = True,
        quantum_shots: int = 128,
        quantum_feature_count: int = 5,
        quantum_cap: int | None = None,
        n_estimators: int = 50,
        contamination: float = 0.2,
        provider_weights: dict[str, float] | None = None,
        random_state: int = 42,
    ) -> None:
        self.quantum = quantum
        self.quantum_shots = quantum_shots
        self.quantum_feature_count = quantum_feature_count
        self.quantum_cap = quantum_cap
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.provider_weights = dict(
            DEFAULT_PROVIDER_WEIGHTS if provider_weights is None else provider_weights
        )
        self.random_state = random_state

        self.normalizer = PromptNormalizer()
        self.feature_extractor = PromptFeatureExtractor()
        self.ml_features = MLFeatureProvider()
        self.rule_engine = RuleEngine()

        self.scaler: StandardScaler | None = None
        self.anomaly: IsolationForestDetector | None = None
        self.rf: RandomForestThreatClassifier | None = None
        self.xgb: XGBoostThreatClassifier | None = None
        self.qsvm: QSVMModel | None = None
        # Optional per-provider probability calibrators (fitted on the
        # validation split, never on JBB). Maps a classical provider id
        # ("random-forest"/"xgboost") to ("platt"|"isotonic", fitted model).
        # When set, ``probability_matrix`` returns calibrated probabilities.
        self.calibrators: dict[str, tuple[str, Any]] | None = None
        self._providers: dict[str, tuple[PredictionProvider, float]] = {}

    # ── Feature extraction ─────────────────────────────────────────────

    def vector(self, text: str) -> list[float]:
        """Extract the ML feature vector for a prompt."""
        normalized = self.normalizer.normalize(text)
        base = self.feature_extractor.extract(normalized)
        return self.ml_features.extract_vector(normalized, base).features

    # ── Training ───────────────────────────────────────────────────────

    def fit(self, texts: list[str], labels: list[int]) -> None:
        """Fit scaler, classical models, optional QSVM, and fusion engine."""
        if len(texts) != len(labels):
            msg = f"texts ({len(texts)}) and labels ({len(labels)}) length mismatch"
            raise ValueError(msg)

        x = np.array([self.vector(t) for t in texts], dtype=np.float64)
        y = list(labels)

        self.scaler = StandardScaler()
        self.scaler.fit(x)
        x_scaled = self.scaler.transform(x).tolist()

        self.anomaly = IsolationForestDetector(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
        )
        self.rf = RandomForestThreatClassifier(n_estimators=self.n_estimators)
        self.anomaly.train(x_scaled)
        self.rf.train(x_scaled, y)

        # XGBoost is part of the classical classifier stack. It trains on the
        # same scaled features as Random Forest; if the optional dependency is
        # not installed the classifier reports itself unavailable and the
        # provider is skipped (graceful degradation, matching the ml module).
        self.xgb = XGBoostThreatClassifier(n_estimators=self.n_estimators)
        if self.xgb.is_available:
            self.xgb.train(x_scaled, y)
        else:
            self.xgb = None
            logger.warning("xgboost_provider_skipped_unavailable")

        if self.quantum:
            q_x = np.array(x_scaled, dtype=np.float64)
            q_x = q_x[:, : self.quantum_feature_count].tolist()
            q_y = y
            if self.quantum_cap is not None and len(q_x) > self.quantum_cap:
                q_x = q_x[: self.quantum_cap]
                q_y = y[: self.quantum_cap]
            backend = LocalSimulatorBackend(
                num_qubits=self.quantum_feature_count,
                shots=self.quantum_shots,
            )
            feature_map = AngleEncodingMap(num_qubits=self.quantum_feature_count)
            kernel = QuantumKernelEstimator(
                feature_map=feature_map,
                backend=backend,
                shots=self.quantum_shots,
            )
            self.qsvm = QSVMModel(kernel=kernel, feature_map=feature_map)
            self.qsvm.train(q_x, q_y)

        self._setup_providers()

    def _setup_providers(self) -> None:
        """Build the provider registry from the trained components."""
        if self.scaler is None or self.anomaly is None or self.rf is None:
            msg = "scaler, anomaly and random-forest must be fitted first"
            raise RuntimeError(msg)
        self._providers = {
            RULE_PROVIDER: (
                RuleEngineProvider(
                    rule_engine=self.rule_engine,
                    normalizer=self.normalizer,
                ),
                self.provider_weights.get(RULE_PROVIDER, 0.15),
            ),
            ANOMALY_PROVIDER: (
                ClassicalModelProvider(self.anomaly, provider_id=ANOMALY_PROVIDER),
                self.provider_weights.get(ANOMALY_PROVIDER, 0.15),
            ),
            CLASSIFIER_PROVIDER: (
                ClassicalModelProvider(self.rf, provider_id=CLASSIFIER_PROVIDER),
                self.provider_weights.get(CLASSIFIER_PROVIDER, 0.55),
            ),
        }
        if self.xgb is not None:
            self._providers[XGBOOST_PROVIDER] = (
                ClassicalModelProvider(self.xgb, provider_id=XGBOOST_PROVIDER),
                self.provider_weights.get(XGBOOST_PROVIDER, 0.25),
            )
        if self.qsvm is not None:
            self._providers[QUANTUM_PROVIDER] = (
                QuantumModelProvider(self.qsvm),
                self.provider_weights.get(QUANTUM_PROVIDER, 0.15),
            )

    # ── Persistence ───────────────────────────────────────────────────

    def save_state(self, directory: str | Path) -> Path:
        """Persist the fitted pipeline components (joblib checkpoint).

        Args:
            directory: Target directory; the checkpoint is written as
                ``hybrid_evaluator.joblib`` plus a human-readable
                ``params.json``.

        Returns:
            The directory the checkpoint was written to.
        """
        import joblib

        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        state: dict[str, Any] = {
            "params": {
                "quantum": self.quantum,
                "quantum_shots": self.quantum_shots,
                "quantum_feature_count": self.quantum_feature_count,
                "quantum_cap": self.quantum_cap,
                "n_estimators": self.n_estimators,
                "contamination": self.contamination,
                "provider_weights": dict(self.provider_weights),
                "random_state": self.random_state,
            },
            "scaler": self.scaler,
            "anomaly": self.anomaly,
            "rf": self.rf,
            "xgb": self.xgb,
            "qsvm": self.qsvm,
        }
        joblib.dump(state, path / "hybrid_evaluator.joblib")
        with open(path / "params.json", "w", encoding="utf-8") as f:
            json.dump(state["params"], f, indent=2)
        return path

    @classmethod
    def load_state(cls, directory: str | Path) -> HybridEvaluator:
        """Load a pipeline checkpoint written by ``save_state``."""
        import joblib

        path = Path(directory)
        state: Any = joblib.load(path / "hybrid_evaluator.joblib")
        evaluator = cls(**state["params"])
        evaluator.scaler = state.get("scaler")
        evaluator.anomaly = state.get("anomaly")
        evaluator.rf = state.get("rf")
        evaluator.xgb = state.get("xgb")
        evaluator.qsvm = state.get("qsvm")
        evaluator._setup_providers()
        return evaluator

    def score_texts(self, texts: list[str]) -> list[float]:
        """Return the fused threat score for each prompt (no labels needed).

        Args:
            texts: Prompt texts to score.

        Returns:
            A ``fusion`` risk score per input (higher = more threat).
        """
        fusion = self._build_fusion(include_providers=None)

        async def _run() -> list[dict[str, float]]:
            results = await asyncio.gather(*[self._score_one(text, fusion) for text in texts])
            return list(results)

        return [row["fusion"] for row in asyncio.run(_run())]

    # ── Probability calibration ────────────────────────────────────────

    def set_calibrator(self, provider_id: str, method: str, model: Any) -> None:
        """Attach a fitted probability calibrator to a classical provider.

        Args:
            provider_id: ``"random-forest"`` or ``"xgboost"``.
            method: ``"platt"`` (sigmoid/LogisticRegression) or
                ``"isotonic"`` (IsotonicRegression).
            model: The fitted sklearn calibrator object.
        """
        if self.calibrators is None:
            self.calibrators = {}
        self.calibrators[provider_id] = (method, model)

    def _positive_probability(self, provider_id: str, x_scaled: Any) -> list[float]:
        """Raw P(malicious) from a fitted classical provider."""
        if provider_id == CLASSIFIER_PROVIDER:
            if self.rf is None or self.rf.model is None:
                msg = "random-forest is not fitted"
                raise RuntimeError(msg)
            model = self.rf.model
        elif provider_id == XGBOOST_PROVIDER:
            if self.xgb is None or self.xgb.model is None:
                msg = "xgboost is not fitted"
                raise RuntimeError(msg)
            model = self.xgb.model
        else:
            msg = f"no probability provider named {provider_id!r}"
            raise ValueError(msg)

        import numpy as np

        arr = np.asarray(
            x_scaled, dtype=np.float32 if provider_id == XGBOOST_PROVIDER else np.float64
        )
        probas = model.predict_proba(arr)
        classes = getattr(model, "classes_", None)
        col = int(np.where(classes == 1)[0][0]) if classes is not None else probas.shape[1] - 1
        return [float(v) for v in probas[:, col]]

    def raw_probability_matrix(self, texts: list[str]) -> dict[str, list[float]]:
        """Batched raw P(malicious) per classical provider (RF/XGBoost).

        Uses exactly the same features as single-prompt inference
        (``vector()``); the batched path only avoids per-text encoder calls.
        """
        if self.scaler is None:
            msg = "HybridEvaluator.fit() must be called before scoring"
            raise RuntimeError(msg)
        x = self.feature_matrix(texts)
        x_scaled = self.scaler.transform(x)
        providers = [CLASSIFIER_PROVIDER]
        if self.xgb is not None and self.xgb.is_trained:
            providers.append(XGBOOST_PROVIDER)
        return {pid: self._positive_probability(pid, x_scaled) for pid in providers}

    def probability_matrix(
        self,
        texts: list[str],
        *,
        calibrated: bool = True,
    ) -> dict[str, list[float]]:
        """Per-provider malicious-class probabilities for production inference.

        When calibrators are attached (and ``calibrated=True``) the returned
        scores are **calibrated probabilities**; otherwise raw model scores.
        Decision rule for downstream consumers:
        ``probability >= classification_threshold``.
        """
        scores = self.raw_probability_matrix(texts)
        if not calibrated or not self.calibrators:
            return scores
        out: dict[str, list[float]] = {}
        for pid, values in scores.items():
            cal = self.calibrators.get(pid)
            out[pid] = apply_probability_calibration(cal, values) if cal else values
        return out

    def malicious_decisions(
        self,
        texts: list[str],
        provider_id: str = XGBOOST_PROVIDER,
        threshold: float | None = None,
    ) -> list[bool]:
        """Production decision rule: calibrated probability >= threshold.

        The threshold defaults to the single configured source of truth
        (``MLConfig.classification_threshold``, default 0.2 after the Week 3
        threshold sweep); callers may override it per call.

        Args:
            texts: Prompt texts to classify.
            provider_id: Classical provider to use (default ``"xgboost"``).
            threshold: Optional override of the configured threshold.

        Returns:
            One ``True`` (malicious) / ``False`` (benign) decision per text.
        """
        from q_guardian.ml.config import MLConfig

        if threshold is None:
            threshold = MLConfig().classification_threshold
        probabilities = self.probability_matrix(texts)[provider_id]
        return [p >= threshold for p in probabilities]

    # ── Scoring ────────────────────────────────────────────────────────

    def _build_fusion(
        self,
        include_providers: set[str] | None = None,
    ) -> HybridFusionEngine:
        """Build a fusion engine over the requested provider subset."""
        fusion = HybridFusionEngine(strategy=WeightedVotingStrategy())
        for pid, (provider, weight) in self._providers.items():
            if include_providers is None or pid in include_providers:
                fusion.register_provider(provider, weight=weight)
        return fusion

    async def _score_one(
        self,
        text: str,
        fusion: HybridFusionEngine,
    ) -> dict[str, float]:
        """Score a single prompt with the given fusion engine."""
        if self.scaler is None:
            msg = "HybridEvaluator.fit() must be called before scoring"
            raise RuntimeError(msg)
        raw = np.array([self.vector(text)], dtype=np.float64)
        scaled = self.scaler.transform(raw)[0]
        features = {"feature_vector": scaled.tolist()}

        fused = await fusion.fuse(text, features=features, calibrate=False)
        result: dict[str, float] = {
            p.provider_id: float(p.risk_score)
            for p in fused.source_predictions
            if p.is_valid is not False
        }
        result["fusion"] = float(fused.risk_score)
        return result

    def provider_ids(self) -> list[str]:
        return list(self._providers.keys())

    def evaluate(
        self,
        dataset: PromptBenchmarkDataset,
        threshold: float = 0.5,
        include_providers: set[str] | None = None,
    ) -> dict[str, Any]:
        """Evaluate the fitted pipeline on a dataset.

        Returns metrics for each active provider and for the fused result.

        Args:
            dataset: Labeled samples to score.
            threshold: Decision threshold for binary metrics.
            include_providers: Restrict fusion to this subset of providers
                (used by ablation). Passing None uses every fitted provider.

        Returns:
            Dictionary mapping ``"fusion"`` and each provider id to their
            detection metrics, plus a ``"scores"`` record with the raw
            continuous threat scores.
        """
        if self.scaler is None or not self._providers:
            msg = "Evaluator must be fitted before evaluation"
            raise RuntimeError(msg)

        texts = dataset.texts()
        labels = dataset.labels()
        fusion = self._build_fusion(include_providers=include_providers)

        async def _run() -> list[dict[str, float]]:
            return await asyncio.gather(*[self._score_one(t, fusion) for t in texts])

        per_sample = asyncio.run(_run())

        active = [
            pid
            for pid in self.provider_ids()
            if include_providers is None or pid in include_providers
        ]
        result: dict[str, Any] = {}
        for provider in ["fusion", *active]:
            scores = [row.get(provider, 0.0) for row in per_sample]
            result[provider] = detection_metrics(labels, scores, threshold=threshold)

        result["scores"] = [
            {**row, "label": label, "text": text}
            for row, label, text in zip(per_sample, labels, texts, strict=True)
        ]
        return result
