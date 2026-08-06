"""Unit tests for QuantumKernelTrainer — Phase 2."""

from __future__ import annotations

import numpy as np
import pytest

from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
from q_guardian.quantum.enums import OptimizerType
from q_guardian.quantum.exceptions import ConfigurationError, TrainingError
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
from q_guardian.quantum.training.kernel_trainer import (
    KernelCandidate,
    KernelHyperparams,
    KernelSearchResult,
    QuantumKernelTrainer,
)


@pytest.fixture
def backend() -> LocalSimulatorBackend:
    return LocalSimulatorBackend()


@pytest.fixture
def feature_map() -> AngleEncodingMap:
    return AngleEncodingMap(num_qubits=4)


@pytest.fixture
def kernel(feature_map: AngleEncodingMap, backend: LocalSimulatorBackend) -> QuantumKernelEstimator:
    return QuantumKernelEstimator(feature_map=feature_map, backend=backend)


@pytest.fixture
def trainer(kernel: QuantumKernelEstimator, feature_map: AngleEncodingMap) -> QuantumKernelTrainer:
    return QuantumKernelTrainer(kernel=kernel, feature_map=feature_map)


@pytest.fixture
def sample_data() -> tuple[list[list[float]], list[int]]:
    rng = np.random.default_rng(42)
    x = rng.uniform(-np.pi, np.pi, size=(20, 4)).tolist()
    y = [0 if i < 10 else 1 for i in range(20)]
    return x, y


class TestKernelHyperparams:
    def test_default_values(self):
        hp = KernelHyperparams()
        assert hp.num_qubits == 4
        assert hp.feature_map_reps == 1
        assert hp.entanglement == "linear"
        assert hp.depth == 3
        assert hp.regularization == 1e-3
        assert hp.shots == 1024
        assert hp.optimizer == OptimizerType.ADAM
        assert hp.learning_rate == 0.1

    def test_custom_values(self):
        hp = KernelHyperparams(num_qubits=8, depth=5, shots=2048)
        assert hp.num_qubits == 8
        assert hp.depth == 5
        assert hp.shots == 2048

    def test_to_dict(self):
        hp = KernelHyperparams(num_qubits=6)
        d = hp.to_dict()
        assert d["num_qubits"] == 6
        assert "entanglement" in d
        assert "optimizer" in d

    def test_from_dict(self):
        d = {"num_qubits": 10, "depth": 7, "shots": 4096}
        hp = KernelHyperparams.from_dict(d)
        assert hp.num_qubits == 10
        assert hp.depth == 7
        assert hp.shots == 4096

    def test_from_dict_defaults(self):
        hp = KernelHyperparams.from_dict({})
        assert hp.num_qubits == 4
        assert hp.regularization == 1e-3

    def test_to_dict_roundtrip(self):
        hp = KernelHyperparams(num_qubits=8, depth=4, regularization=0.01)
        d = hp.to_dict()
        hp2 = KernelHyperparams.from_dict(d)
        assert hp2.num_qubits == 8
        assert hp2.depth == 4
        assert hp2.regularization == 0.01

    def test_metadata(self):
        hp = KernelHyperparams(metadata={"custom_key": "value"})
        assert hp.metadata["custom_key"] == "value"

    def test_to_dict_includes_metadata(self):
        hp = KernelHyperparams(metadata={"a": 1})
        d = hp.to_dict()
        assert d["metadata"] == {"a": 1}


class TestKernelCandidate:
    def test_composite_score(self):
        c = KernelCandidate(
            hyperparams=KernelHyperparams(),
            accuracy=0.9,
            training_time_s=1.0,
            cv_score_mean=0.85,
            cv_score_std=0.05,
        )
        expected = 0.85 - 0.1 * 0.05
        assert abs(c.composite_score - expected) < 1e-6

    def test_composite_score_zero_std(self):
        c = KernelCandidate(
            hyperparams=KernelHyperparams(),
            accuracy=0.9,
            training_time_s=1.0,
            cv_score_mean=0.9,
            cv_score_std=0.0,
        )
        assert c.composite_score == 0.9


class TestKernelSearchResult:
    def test_to_dict(self):
        best = KernelCandidate(
            hyperparams=KernelHyperparams(num_qubits=4),
            accuracy=0.85,
            training_time_s=2.0,
            cv_score_mean=0.82,
            cv_score_std=0.03,
        )
        result = KernelSearchResult(
            best_candidate=best,
            all_candidates=[best],
            search_time_s=5.0,
            total_evaluations=1,
        )
        d = result.to_dict()
        assert d["best_accuracy"] == 0.85
        assert d["total_evaluations"] == 1
        assert d["search_time_s"] == 5.0


class TestQuantumKernelTrainerConstruction:
    def test_kernel_property(self, trainer: QuantumKernelTrainer, kernel: QuantumKernelEstimator):
        assert trainer.kernel is kernel

    def test_feature_map_property(
        self, trainer: QuantumKernelTrainer, feature_map: AngleEncodingMap
    ):
        assert trainer.feature_map is feature_map

    def test_history_empty_initially(self, trainer: QuantumKernelTrainer):
        assert trainer.history == []

    def test_clear_cache(self, trainer: QuantumKernelTrainer):
        count = trainer.clear_cache()
        assert count == 0


class TestKernelTrainerGridSearch:
    def test_grid_search_basic(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        param_grid = {"num_qubits": [2, 4]}
        result = trainer.search_grid(x, y, param_grid, cv_folds=2)
        assert isinstance(result, KernelSearchResult)
        assert result.total_evaluations == 2

    def test_grid_search_empty_grid_raises(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        with pytest.raises(ConfigurationError):
            trainer.search_grid(x, y, {}, cv_folds=2)

    def test_grid_search_too_few_samples_raises(self, trainer: QuantumKernelTrainer):
        with pytest.raises(TrainingError):
            trainer.search_grid([[1.0, 2.0, 3.0, 4.0]], [0], {"num_qubits": [2]}, cv_folds=2)

    def test_grid_search_records_history(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        trainer.search_grid(x, y, {"num_qubits": [2]}, cv_folds=2)
        assert len(trainer.history) == 1

    def test_grid_search_returns_candidates(
        self, trainer: QuantumKernelTrainer, sample_data: tuple
    ):
        x, y = sample_data
        result = trainer.search_grid(x, y, {"num_qubits": [2, 4]}, cv_folds=2)
        assert len(result.all_candidates) == 2


class TestKernelTrainerRandomSearch:
    def test_random_search_basic(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        param_distributions = {"num_qubits": [2, 4, 6]}
        result = trainer.search_random(x, y, param_distributions, n_iter=3, cv_folds=2)
        assert isinstance(result, KernelSearchResult)
        assert result.total_evaluations == 3

    def test_random_search_empty_raises(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        with pytest.raises(ConfigurationError):
            trainer.search_random(x, y, {}, n_iter=3, cv_folds=2)

    def test_random_search_records_history(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        trainer.search_random(x, y, {"num_qubits": [2]}, n_iter=1, cv_folds=2)
        assert len(trainer.history) == 1


class TestKernelTrainerTrainKernel:
    def test_train_kernel_basic(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        result = trainer.train_kernel(x, y)
        assert result.model_name.startswith("kernel-")
        assert result.training_samples == len(x)

    def test_train_kernel_empty_raises(self, trainer: QuantumKernelTrainer):
        with pytest.raises(TrainingError):
            trainer.train_kernel([])

    def test_train_kernel_with_hyperparams(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        hp = KernelHyperparams(num_qubits=8)
        result = trainer.train_kernel(x, y, hp)
        assert "hyperparams" in result.metadata


class TestKernelTrainerCrossValidate:
    def test_cross_validate_basic(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        result = trainer.cross_validate(x, y, cv_folds=2)
        assert "cv_scores" in result
        assert "cv_score_mean" in result
        assert "cv_score_std" in result
        assert len(result["cv_scores"]) == 2

    def test_cross_validate_too_few_samples_raises(self, trainer: QuantumKernelTrainer):
        with pytest.raises(TrainingError):
            trainer.cross_validate([[1.0]], [0], cv_folds=5)

    def test_cross_validate_score_range(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        result = trainer.cross_validate(x, y, cv_folds=2)
        for score in result["cv_scores"]:
            assert 0.0 <= score <= 1.0


class TestKernelTrainerInfo:
    def test_get_kernel_info(self, trainer: QuantumKernelTrainer):
        info = trainer.get_kernel_info()
        assert "kernel_name" in info
        assert "feature_map_name" in info
        assert "num_qubits" in info
        assert "encoding_type" in info
        assert "circuit_depth" in info

    def test_get_kernel_info_after_search(self, trainer: QuantumKernelTrainer, sample_data: tuple):
        x, y = sample_data
        trainer.search_grid(x, y, {"num_qubits": [2]}, cv_folds=2)
        info = trainer.get_kernel_info()
        assert info["history_length"] == 1
