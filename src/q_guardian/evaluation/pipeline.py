"""End-to-end evaluator for the hybrid detection pipeline.

Builds the real Q-Guardian pipeline (normalizer -> feature extractor ->
rule engine -> classical ML -> quantum QSVM -> hybrid fusion) using the
framework's own provider adapters, fits it on a training set, and scores
it on a test set. Every provider (rule engine, isolation forest, random
forest, QSVM) and the fused result is measured with the same continuous
threat score, enabling per-component comparison and ablation.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import numpy as np
from sklearn.preprocessing import StandardScaler

from q_guardian.evaluation.metrics import detection_metrics
from q_guardian.ml.feature_pipeline import MLFeatureProvider
from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import RandomForestThreatClassifier
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

# Provider identifiers as registered on the fusion engine.
RULE_PROVIDER = "rule-engine"
ANOMALY_PROVIDER = "isolation-forest"
CLASSIFIER_PROVIDER = "random-forest"
QUANTUM_PROVIDER = "qsvm"

# Default fusion weights mirror the production harness configuration.
DEFAULT_PROVIDER_WEIGHTS: dict[str, float] = {
    RULE_PROVIDER: 0.15,
    ANOMALY_PROVIDER: 0.15,
    CLASSIFIER_PROVIDER: 0.55,
    QUANTUM_PROVIDER: 0.15,
}

ALL_PROVIDERS = [
    RULE_PROVIDER,
    ANOMALY_PROVIDER,
    CLASSIFIER_PROVIDER,
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
        self.qsvm: QSVMModel | None = None
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
            self._providers[QUANTUM_PROVIDER] = (
                QuantumModelProvider(self.qsvm),
                self.provider_weights.get(QUANTUM_PROVIDER, 0.15),
            )

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
