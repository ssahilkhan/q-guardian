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
        use_semantic_embedding: bool = False,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        rf_n_estimators: int | None = None,
        xgb_n_estimators: int | None = None,
    ) -> None:
        self.quantum = quantum
        self.quantum_shots = quantum_shots
        self.quantum_feature_count = quantum_feature_count
        self.quantum_cap = quantum_cap
        self.n_estimators = n_estimators
        # Per-model estimator overrides (None = use ``n_estimators``).
        self.rf_n_estimators = rf_n_estimators
        self.xgb_n_estimators = xgb_n_estimators
        self.contamination = contamination
        self.provider_weights = dict(
            DEFAULT_PROVIDER_WEIGHTS if provider_weights is None else provider_weights
        )
        self.random_state = random_state
        # Optional semantic-embedding extension of the feature vector (used by
        # the training-diversity arm_d models). When enabled, ``vector()``
        # appends a normalized sentence embedding to the handcrafted features
        # so training and inference share one identical representation.
        self.use_semantic_embedding = use_semantic_embedding
        self.embedding_model_name = embedding_model_name

        self.normalizer = PromptNormalizer()
        self.feature_extractor = PromptFeatureExtractor()
        self.ml_features = MLFeatureProvider()
        self.rule_engine = RuleEngine()

        self.scaler: StandardScaler | None = None
        self.anomaly: IsolationForestDetector | None = None
        self.rf: RandomForestThreatClassifier | None = None
        self.xgb: XGBoostThreatClassifier | None = None
        self.qsvm: QSVMModel | None = None
        self._providers: dict[str, tuple[PredictionProvider, float]] = {}
        self._embedding_model: Any = None

    # ── Feature extraction ─────────────────────────────────────────────

    def _ensure_embedder(self) -> Any:
        """Lazy-load the sentence-embedding model (optional dependency)."""
        if self._embedding_model is not None:
            return self._embedding_model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment dependent
            msg = (
                "use_semantic_embedding=True requires the optional "
                "'sentence-transformers' dependency"
            )
            raise RuntimeError(msg) from exc
        self._embedding_model = SentenceTransformer(self.embedding_model_name)
        return self._embedding_model

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        """Encode texts into normalized embeddings (batched)."""
        model = self._ensure_embedder()
        emb = model.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
        return np.asarray(emb, dtype=np.float64)

    def vector(self, text: str) -> list[float]:
        """Extract the ML feature vector for a prompt."""
        normalized = self.normalizer.normalize(text)
        base = self.feature_extractor.extract(normalized)
        features = list(self.ml_features.extract_vector(normalized, base).features)
        if self.use_semantic_embedding:
            features.extend(self._embed_texts([text])[0].tolist())
        return features

    def feature_matrix(self, texts: list[str]) -> np.ndarray:
        """Feature matrix for many prompts (batched embeddings when enabled).

        Produces exactly the same rows as ``vector()`` per prompt; the batch
        path only avoids per-text encoder calls during training.
        """
        if not self.use_semantic_embedding:
            return np.array([self.vector(t) for t in texts], dtype=np.float64)
        base_rows: list[list[float]] = []
        for t in texts:
            normalized = self.normalizer.normalize(t)
            feats = self.feature_extractor.extract(normalized)
            base_rows.append(list(self.ml_features.extract_vector(normalized, feats).features))
        emb = self._embed_texts(texts)
        return np.hstack([np.array(base_rows, dtype=np.float64), emb])

    # ── Training ───────────────────────────────────────────────────────

    def fit(self, texts: list[str], labels: list[int]) -> None:
        """Fit scaler, classical models, optional QSVM, and fusion engine."""
        if len(texts) != len(labels):
            msg = f"texts ({len(texts)}) and labels ({len(labels)}) length mismatch"
            raise ValueError(msg)

        x = self.feature_matrix(texts)
        y = list(labels)

        self.scaler = StandardScaler()
        self.scaler.fit(x)
        x_scaled = self.scaler.transform(x).tolist()

        self.anomaly = IsolationForestDetector(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
        )
        self.rf = RandomForestThreatClassifier(
            n_estimators=self.rf_n_estimators or self.n_estimators
        )
        self.anomaly.train(x_scaled)
        self.rf.train(x_scaled, y)

        # XGBoost is part of the classical classifier stack. It trains on the
        # same scaled features as Random Forest; if the optional dependency is
        # not installed the classifier reports itself unavailable and the
        # provider is skipped (graceful degradation, matching the ml module).
        self.xgb = XGBoostThreatClassifier(n_estimators=self.xgb_n_estimators or self.n_estimators)
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
                "rf_n_estimators": self.rf_n_estimators,
                "xgb_n_estimators": self.xgb_n_estimators,
                "contamination": self.contamination,
                "provider_weights": dict(self.provider_weights),
                "random_state": self.random_state,
                "use_semantic_embedding": self.use_semantic_embedding,
                "embedding_model_name": self.embedding_model_name,
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
        # Checkpoints saved before semantic-embedding support default to the
        # handcrafted-only representation via __init__ defaults.
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
