"""Ablation evaluator (root-cause research, Phases 3 & 4).

A ``HybridEvaluator`` subclass that keeps the production scoring/fusion path
intact but lets experiments control:

- ``rf_class_weight``: passed to ``RandomForestThreatClassifier`` (default
  ``None`` reproduces the baseline exactly).
- ``feature_indices``: columns of the 43-feature vector kept for scaler /
  anomaly / random-forest. The fusion + provider scoring code is unchanged.

No production pipeline code is modified by these experiments.
"""

from __future__ import annotations

import numpy as np
from sklearn.preprocessing import StandardScaler

from q_guardian.evaluation.pipeline import HybridEvaluator
from q_guardian.ml.models.anomaly import IsolationForestDetector
from q_guardian.ml.models.classifier import RandomForestThreatClassifier
from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.models.qsvm import QSVMModel


class AblationEvaluator(HybridEvaluator):
    """HybridEvaluator with experimental hooks (class weight / feature subset)."""

    def __init__(
        self,
        *,
        rf_class_weight: str | dict[str, float] | None = None,
        feature_indices: list[int] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.rf_class_weight = rf_class_weight
        self.feature_indices = feature_indices

    def vector(self, text: str) -> list[float]:
        full = super().vector(text)
        if self.feature_indices is None:
            return full
        return [full[i] for i in self.feature_indices]

    def fit(self, texts: list[str], labels: list[int]) -> None:
        if self.rf_class_weight is None:
            super().fit(texts, labels)
            return

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
        self.rf = RandomForestThreatClassifier(
            n_estimators=self.n_estimators,
            class_weight=self.rf_class_weight,
        )
        self.anomaly.train(x_scaled)
        self.rf.train(x_scaled, y)

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
