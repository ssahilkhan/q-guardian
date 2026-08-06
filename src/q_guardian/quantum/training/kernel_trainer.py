"""QuantumKernelTrainer — trains and tunes quantum kernels for QSVM models.

Manages kernel hyper-parameter search, cross-validated kernel
selection, and kernel persistence. Depends only on Phase 1 abstractions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

from q_guardian.quantum.data import QuantumTrainingResult
from q_guardian.quantum.enums import (
    OptimizerType,
)
from q_guardian.quantum.exceptions import (
    ConfigurationError,
    TrainingError,
)

if TYPE_CHECKING:
    from q_guardian.quantum.feature_maps.base import QuantumFeatureMap
    from q_guardian.quantum.kernels.base import QuantumKernel

logger = structlog.get_logger("quantum.kernel_trainer")


@dataclass
class KernelHyperparams:
    """Hyper-parameters for a quantum kernel."""

    num_qubits: int = 4
    feature_map_reps: int = 1
    entanglement: str = "linear"
    depth: int = 3
    regularization: float = 1e-3
    kernel_cache_size: int = 1024
    optimization_level: int = 2
    shots: int = 1024
    optimizer: OptimizerType = OptimizerType.ADAM
    learning_rate: float = 0.1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_qubits": self.num_qubits,
            "feature_map_reps": self.feature_map_reps,
            "entanglement": self.entanglement,
            "depth": self.depth,
            "regularization": self.regularization,
            "kernel_cache_size": self.kernel_cache_size,
            "optimization_level": self.optimization_level,
            "shots": self.shots,
            "optimizer": self.optimizer.value,
            "learning_rate": self.learning_rate,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KernelHyperparams:
        return cls(
            num_qubits=data.get("num_qubits", 4),
            feature_map_reps=data.get("feature_map_reps", 1),
            entanglement=data.get("entanglement", "linear"),
            depth=data.get("depth", 3),
            regularization=data.get("regularization", 1e-3),
            kernel_cache_size=data.get("kernel_cache_size", 1024),
            optimization_level=data.get("optimization_level", 2),
            shots=data.get("shots", 1024),
            optimizer=OptimizerType(data.get("optimizer", OptimizerType.ADAM.value)),
            learning_rate=data.get("learning_rate", 0.1),
            metadata=data.get("metadata", {}),
        )


@dataclass
class KernelCandidate:
    """A single kernel candidate from hyper-parameter search."""

    hyperparams: KernelHyperparams
    accuracy: float
    training_time_s: float
    cv_score_mean: float
    cv_score_std: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def composite_score(self) -> float:
        return self.cv_score_mean - 0.1 * self.cv_score_std


@dataclass
class KernelSearchResult:
    """Result of a kernel hyper-parameter search."""

    best_candidate: KernelCandidate
    all_candidates: list[KernelCandidate]
    search_time_s: float
    total_evaluations: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_accuracy": self.best_candidate.accuracy,
            "best_cv_score": self.best_candidate.cv_score_mean,
            "best_cv_std": self.best_candidate.cv_score_std,
            "best_hyperparams": self.best_candidate.hyperparams.to_dict(),
            "search_time_s": self.search_time_s,
            "total_evaluations": self.total_evaluations,
            "num_candidates": len(self.all_candidates),
        }


class QuantumKernelTrainer:
    """Trains and tunes quantum kernels for QSVM and other kernel models.

    Responsibilities:
      1. Hyper-parameter grid/random search over kernel configurations
      2. Cross-validated kernel scoring
      3. Kernel caching for repeated evaluations
      4. Best-kernel selection and persistence

    The trainer does NOT create backends — it receives a QuantumKernel
    instance whose QuantumBackend is already connected.
    """

    def __init__(
        self,
        kernel: QuantumKernel,
        feature_map: QuantumFeatureMap,
    ) -> None:
        self._kernel = kernel
        self._feature_map = feature_map
        self._cache: dict[str, dict[str, Any]] = {}
        self._history: list[KernelSearchResult] = []

    @property
    def kernel(self) -> QuantumKernel:
        return self._kernel

    @property
    def feature_map(self) -> QuantumFeatureMap:
        return self._feature_map

    @property
    def history(self) -> list[KernelSearchResult]:
        return list(self._history)

    def search_grid(
        self,
        x: list[list[float]],
        y: list[int],
        param_grid: dict[str, list[Any]],
        cv_folds: int = 5,
    ) -> KernelSearchResult:
        """Grid search over a hyper-parameter space."""
        if not param_grid:
            msg = "param_grid cannot be empty"
            raise ConfigurationError(msg)
        if len(x) < 2:
            msg = "Need at least 2 samples for grid search"
            raise TrainingError(msg)

        start = time.monotonic()
        keys = sorted(param_grid.keys())
        combinations = self._grid_combinations(param_grid)
        candidates: list[KernelCandidate] = []

        logger.info("kernel_grid_search_started", combinations=len(combinations), cv_folds=cv_folds)

        for combo in combinations:
            hp = KernelHyperparams(**dict(zip(keys, combo, strict=False)))
            candidate = self._evaluate_kernel(x, y, hp, cv_folds)
            candidates.append(candidate)

        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        best = (
            candidates[0]
            if candidates
            else KernelCandidate(
                hyperparams=KernelHyperparams(),
                accuracy=0.0,
                training_time_s=0.0,
                cv_score_mean=0.0,
                cv_score_std=1.0,
            )
        )

        result = KernelSearchResult(
            best_candidate=best,
            all_candidates=candidates,
            search_time_s=time.monotonic() - start,
            total_evaluations=len(candidates),
        )
        self._history.append(result)
        return result

    def search_random(
        self,
        x: list[list[float]],
        y: list[int],
        param_distributions: dict[str, list[Any] | tuple[Any, Any]],
        n_iter: int = 20,
        cv_folds: int = 5,
    ) -> KernelSearchResult:
        """Random search over a hyper-parameter space."""
        if not param_distributions:
            msg = "param_distributions cannot be empty"
            raise ConfigurationError(msg)

        start = time.monotonic()
        candidates: list[KernelCandidate] = []

        for _ in range(n_iter):
            sampled: dict[str, Any] = {}
            for key, values in param_distributions.items():
                if (
                    isinstance(values, (list, tuple))
                    and len(values) == 2
                    and not isinstance(values[0], list)
                ):
                    lo, hi = values
                    sampled[key] = np.random.uniform(float(lo), float(hi))
                else:
                    sampled[key] = np.random.choice(list(values))

            hp = KernelHyperparams(
                **{k: v for k, v in sampled.items() if hasattr(KernelHyperparams, k)}
            )
            candidate = self._evaluate_kernel(x, y, hp, cv_folds)
            candidates.append(candidate)

        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        best = (
            candidates[0]
            if candidates
            else KernelCandidate(
                hyperparams=KernelHyperparams(),
                accuracy=0.0,
                training_time_s=0.0,
                cv_score_mean=0.0,
                cv_score_std=1.0,
            )
        )

        result = KernelSearchResult(
            best_candidate=best,
            all_candidates=candidates,
            search_time_s=time.monotonic() - start,
            total_evaluations=len(candidates),
        )
        self._history.append(result)
        return result

    def train_kernel(
        self,
        x: list[list[float]],
        y: list[int] | None = None,
        hyperparams: KernelHyperparams | None = None,
    ) -> QuantumTrainingResult:
        """Train the kernel with given or default hyper-parameters."""
        if not x:
            msg = "Cannot train kernel with empty data"
            raise TrainingError(msg)

        start = time.monotonic()
        hp = hyperparams or KernelHyperparams()

        k_mat = self._kernel.compute_kernel_matrix(x)

        elapsed = time.monotonic() - start

        return QuantumTrainingResult(
            model_name=f"kernel-{self._kernel.name}",
            training_samples=len(x),
            loss=0.0,
            convergence_epoch=1,
            training_time_s=elapsed,
            status="completed",
            metadata={
                "kernel": self._kernel.name,
                "feature_map": self._feature_map.name,
                "hyperparams": hp.to_dict(),
                "matrix_shape": [len(k_mat), len(k_mat[0]) if k_mat else 0],
            },
        )

    def cross_validate(
        self,
        x: list[list[float]],
        y: list[int],
        cv_folds: int = 5,
        hyperparams: KernelHyperparams | None = None,
    ) -> dict[str, Any]:
        """Perform cross-validation on the kernel."""
        n = len(x)
        if n < cv_folds:
            msg = f"Cannot perform {cv_folds}-fold CV with {n} samples"
            raise TrainingError(msg)

        fold_size = n // cv_folds
        scores: list[float] = []

        indices = np.random.permutation(n)

        for fold in range(cv_folds):
            test_start = fold * fold_size
            test_end = test_start + fold_size if fold < cv_folds - 1 else n
            test_idx = list(indices[test_start:test_end])
            train_idx = list(indices[:test_start]) + list(indices[test_end:])

            x_train = [x[i] for i in train_idx]
            y_train = [y[i] for i in train_idx]
            x_test = [x[i] for i in test_idx]
            y_test = [y[i] for i in test_idx]

            self._kernel.compute_kernel_matrix(x_train)
            test_km = self._kernel.compute_kernel_matrix(x_test, x_train)

            predictions = []
            for i, _test_vec in enumerate(x_test):
                train_scores = {}
                for cls in set(y_train):
                    cls_indices = [j for j, label in enumerate(y_train) if label == cls]
                    if cls_indices:
                        kernel_sim = float(np.mean([test_km[i][j] for j in cls_indices]))
                    else:
                        kernel_sim = 0.0
                    train_scores[cls] = kernel_sim
                pred = max(train_scores, key=train_scores.get)  # type: ignore[arg-type]
                predictions.append(pred)

            correct = sum(1 for p, t in zip(predictions, y_test, strict=False) if p == t)
            accuracy = correct / len(y_test) if y_test else 0.0
            scores.append(accuracy)

        mean_score = float(np.mean(scores))
        std_score = float(np.std(scores))

        return {
            "cv_scores": scores,
            "cv_score_mean": mean_score,
            "cv_score_std": std_score,
            "cv_folds": cv_folds,
            "kernel_name": self._kernel.name,
            "feature_map_name": self._feature_map.name,
        }

    def get_kernel_info(self) -> dict[str, Any]:
        """Return metadata about the current kernel configuration."""
        fm_info = self._kernel.get_circuit_info()
        return {
            "kernel_name": self._kernel.name,
            "feature_map_name": self._feature_map.name,
            "num_qubits": self._feature_map.num_qubits,
            "encoding_type": self._feature_map.encoding_type.value,
            "circuit_depth": fm_info.depth,
            "num_gates": fm_info.gate_count,
            "parameter_count": fm_info.metadata.get("parameter_count", 0),
            "cache_size": len(self._cache),
            "history_length": len(self._history),
        }

    def clear_cache(self) -> int:
        """Clear the kernel evaluation cache."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def _evaluate_kernel(
        self,
        x: list[list[float]],
        y: list[int],
        hp: KernelHyperparams,
        cv_folds: int,
    ) -> KernelCandidate:
        """Evaluate a single kernel configuration via cross-validation."""
        start = time.monotonic()

        cv_result = self.cross_validate(x, y, cv_folds, hp)

        elapsed = time.monotonic() - start

        return KernelCandidate(
            hyperparams=hp,
            accuracy=cv_result["cv_score_mean"],
            training_time_s=elapsed,
            cv_score_mean=cv_result["cv_score_mean"],
            cv_score_std=cv_result["cv_score_std"],
            metadata={"kernel_name": self._kernel.name},
        )

    def _grid_combinations(self, param_grid: dict[str, list[Any]]) -> list[tuple[Any, ...]]:
        """Generate all combinations from a parameter grid."""
        keys = sorted(param_grid.keys())
        if not keys:
            return [()]

        values = [param_grid[k] for k in keys]
        result: list[tuple[Any, ...]] = []
        self._recursive_grid(values, 0, (), result)
        return result

    def _recursive_grid(
        self,
        values: list[list[Any]],
        depth: int,
        current: tuple[Any, ...],
        result: list[tuple[Any, ...]],
    ) -> None:
        if depth == len(values):
            result.append(current)
            return
        for v in values[depth]:
            self._recursive_grid(values, depth + 1, (*current, v), result)
