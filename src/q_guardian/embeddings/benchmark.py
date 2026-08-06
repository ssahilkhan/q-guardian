"""Mode-aware benchmarking: handcrafted vs embedding vs hybrid.

Subclasses the existing ``DetectionBenchmark`` (from ``q_guardian.evaluation``,
untouched) so the same K-fold / ablation harness measures the classic
43-feature pipeline, an embedding-only pipeline, and the hybrid pipeline.
``ModeComparisonRunner`` reuses the *completed* benchmark package
(``q_guardian.benchmark``) registry/download/validate/preprocess components
through dependency injection and produces a comparison report automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from q_guardian.benchmark.download import DatasetDownloader
from q_guardian.benchmark.preprocessing import DatasetPreprocessor
from q_guardian.benchmark.registry import DatasetRegistry
from q_guardian.benchmark.validate import DatasetValidator
from q_guardian.embeddings.fusion import (
    FeatureMode,
    ModeFeatureExtractor,
    ModeHybridEvaluator,
)
from q_guardian.embeddings.manager import EmbeddingManager
from q_guardian.evaluation.benchmark import DetectionBenchmark, _aggregate
from q_guardian.evaluation.pipeline import ALL_PROVIDERS

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from q_guardian.benchmark.report import BenchmarkReport
    from q_guardian.benchmark.validate import DatasetValidation
    from q_guardian.evaluation.dataset import PromptBenchmarkDataset


class ModeDetectionBenchmark(DetectionBenchmark):
    """Runs the DetectionBenchmark harness in a single feature mode.

    Args:
        mode: Feature mode for every fold.
        feature_extractor: Mode-aware feature extractor (injectable; its
            embedding manager is used for embedding/hybrid modes).
        evaluator_kwargs: Forwarded to ``ModeHybridEvaluator`` (same keys as
            ``DetectionBenchmark``).
    """

    def __init__(
        self,
        *,
        mode: FeatureMode | str = FeatureMode.HYBRID,
        feature_extractor: ModeFeatureExtractor | None = None,
        evaluator_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(evaluator_kwargs)
        self.mode = FeatureMode(mode)
        self.feature_extractor = feature_extractor or ModeFeatureExtractor(mode=self.mode)

    def _make_evaluator(self) -> ModeHybridEvaluator:
        return ModeHybridEvaluator(
            mode=self.mode,
            mode_extractor=self.feature_extractor,
            **self.evaluator_kwargs,
        )

    def run(
        self,
        dataset: PromptBenchmarkDataset,
        k: int = 5,
        seed: int = 42,
        threshold: float = 0.5,
        ablate: bool = True,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Same contract and report shape as ``DetectionBenchmark.run``."""
        folds = dataset.kfold(k=k, seed=seed)
        report: dict[str, Any] = {
            "config": {
                "k": k,
                "seed": seed,
                "threshold": threshold,
                "mode": self.mode.value,
                "evaluator": {
                    "quantum": self.evaluator_kwargs.get("quantum", True),
                    "quantum_shots": self.evaluator_kwargs.get("quantum_shots", 128),
                    "quantum_feature_count": self.evaluator_kwargs.get("quantum_feature_count", 5),
                    "n_estimators": self.evaluator_kwargs.get("n_estimators", 50),
                    "contamination": self.evaluator_kwargs.get("contamination", 0.2),
                },
            },
            "dataset": dataset.describe(),
            "cross_validation": {
                "fold_count": len(folds),
                "folds": [],
            },
        }

        fold_results: list[dict[str, Any]] = []
        sample_scores: list[dict[str, Any]] = []
        for fold_idx, (train, test) in enumerate(folds):
            if progress:
                progress(
                    f"[{self.mode.value}] fold {fold_idx + 1}/{len(folds)} "
                    f"(train={len(train)}, test={len(test)})"
                )
            evaluator = self._make_evaluator()
            evaluator.fit(train.texts(), train.labels())
            fold_result = evaluator.evaluate(test, threshold=threshold, include_providers=None)
            fold_results.append(
                {
                    provider: fold_result[provider]
                    for provider in ["fusion", *evaluator.provider_ids()]
                }
            )
            sample_scores.extend(fold_result["scores"])
            report["cross_validation"]["folds"].append(
                {
                    "fold": fold_idx + 1,
                    "train_size": len(train),
                    "test_size": len(test),
                    "fusion_roc_auc": round(fold_result["fusion"]["roc_auc"], 6),
                    "fusion_f1": round(fold_result["fusion"]["f1_score"], 6),
                    "fusion_accuracy": round(fold_result["fusion"]["accuracy"], 6),
                }
            )

        report["cross_validation"]["metrics"] = _aggregate(fold_results)
        report["scores"] = sample_scores

        auc_table = report["cross_validation"]["metrics"]
        ranking = sorted(
            ((pid, m["roc_auc"]["mean"]) for pid, m in auc_table.items()),
            key=lambda x: x[1],
            reverse=True,
        )
        report["cross_validation"]["roc_auc_ranking"] = [
            {"provider": pid, "mean_roc_auc": round(auc, 6)} for pid, auc in ranking
        ]

        if ablate:
            fusion_mean = report["cross_validation"]["metrics"]["fusion"]
            full_auc = fusion_mean["roc_auc"]["mean"]
            full_f1 = fusion_mean["f1_score"]["mean"]
            report["ablation"] = self._ablate(
                dataset, k=k, seed=seed, threshold=threshold, progress=progress
            )
            report["ablation_summary"] = self._ablation_summary(
                report["ablation"], full_auc=full_auc, full_f1=full_f1
            )
        return report

    def _ablate(
        self,
        dataset: PromptBenchmarkDataset,
        k: int,
        seed: int,
        threshold: float,
        progress: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        ablation: dict[str, Any] = {}
        for removed in ALL_PROVIDERS:
            kept = [p for p in ALL_PROVIDERS if p != removed]
            fold_auc: list[float] = []
            fold_f1: list[float] = []
            for _fold_idx, (train, test) in enumerate(dataset.kfold(k=k, seed=seed)):
                evaluator = self._make_evaluator()
                evaluator.fit(train.texts(), train.labels())
                result = evaluator.evaluate(
                    test,
                    threshold=threshold,
                    include_providers=set(kept),
                )
                fold_auc.append(result["fusion"]["roc_auc"])
                fold_f1.append(result["fusion"]["f1_score"])
            if progress:
                progress(f"[{self.mode.value}] ablation: removed {removed}")
            ablation[removed] = {
                "removed": removed,
                "kept": kept,
                "fusion_roc_auc": {
                    "mean": round(_fmean_or_zero(fold_auc), 6),
                    "std": round(_stdev_or_zero(fold_auc), 6) if len(fold_auc) > 1 else 0.0,
                },
                "fusion_f1_mean": round(_fmean_or_zero(fold_f1), 6),
            }
        return ablation


def _fmean_or_zero(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / len(values)


def _stdev_or_zero(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _fmean_or_zero(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return float(variance**0.5)


def _build_comparison(modes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank feature modes by fused ROC-AUC."""
    rows: list[dict[str, Any]] = []
    for mode, report in modes.items():
        metrics = report.get("cross_validation", {}).get("metrics", {})
        fusion = metrics.get("fusion", {})
        rows.append(
            {
                "mode": mode,
                "fusion_roc_auc": _metric_mean(fusion, "roc_auc"),
                "fusion_roc_auc_std": _metric_std(fusion, "roc_auc"),
                "fusion_f1": _metric_mean(fusion, "f1_score"),
                "fusion_accuracy": _metric_mean(fusion, "accuracy"),
                "fusion_pr_auc": _metric_mean(fusion, "pr_auc"),
                "fusion_ece": _metric_mean(fusion, "expected_calibration_error"),
                "fusion_brier": _metric_mean(fusion, "brier_score"),
                "fusion_mcc": _metric_mean(fusion, "matthews_corrcoef"),
            }
        )
    rows.sort(key=lambda row: float(row["fusion_roc_auc"] or -1.0), reverse=True)
    return rows


def _metric_mean(block: dict[str, Any], key: str) -> float | None:
    entry = block.get(key)
    if entry is None:
        return None
    value = entry.get("mean")
    return None if value is None else float(value)


def _metric_std(block: dict[str, Any], key: str) -> float | None:
    entry = block.get(key)
    if entry is None:
        return None
    value = entry.get("std")
    return None if value is None else float(value)


def _recommendation(comparison: list[dict[str, Any]]) -> str:
    if not comparison:
        return "No modes produced usable metrics."
    winner = comparison[0]["mode"]
    loser = comparison[-1]["mode"]
    if len(comparison) == 1:
        return f"Only {winner} was benchmarked; add more modes for comparison."
    return (
        f"Best feature mode by fused ROC-AUC is {winner!r}; "
        f"weakest was {loser!r}. Use {winner!r} for production inference "
        "unless latency/storage constraints favour the smaller feature set."
    )


@dataclass
class ModeComparisonReport:
    """Comparison report for handcrafted vs embedding vs hybrid."""

    dataset_id: str
    name: str
    license: str
    homepage: str
    validation: DatasetValidation
    modes: dict[str, dict[str, Any]]
    comparison: list[dict[str, Any]]
    recommendation: str

    def winner(self) -> str:
        return self.comparison[0]["mode"] if self.comparison else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": {
                "id": self.dataset_id,
                "name": self.name,
                "license": self.license,
                "homepage": self.homepage,
            },
            "validation": self.validation.as_dict(),
            "comparison": self.comparison,
            "recommendation": self.recommendation,
            "modes": self.modes,
        }

    def as_benchmark_reports(
        self,
    ) -> dict[str, BenchmarkReport]:
        """Wrap each mode report in the benchmark package's report type."""
        from q_guardian.benchmark.report import BenchmarkReport

        return {
            mode: BenchmarkReport(
                dataset_id=self.dataset_id,
                name=self.name,
                license=self.license,
                homepage=self.homepage,
                validation=self.validation,
                benchmark=report,
            )
            for mode, report in self.modes.items()
        }


class ModeComparisonRunner:
    """Runs all feature modes over a dataset and compares them.

    Reuses the completed ``q_guardian.benchmark`` ingestion components
    (registry/downloader/validator/preprocessor) via dependency injection,
    then runs ``ModeDetectionBenchmark`` per mode on the same folds.

    Args:
        registry: Dataset catalog (defaults to the built-in registry).
        downloader: Fetches dataset splits (defaults to the benchmark
            package downloader).
        validator: Validates splits (defaults to the benchmark validator).
        preprocessor: Maps rows onto ``PromptBenchmarkDataset`` (defaults to
            the benchmark preprocessor).
        manager: Embedding manager used for embedding/hybrid modes.
        benchmark_kwargs: Forwarded to ``ModeDetectionBenchmark``.
        default_modes: Modes run when none are requested.
    """

    def __init__(
        self,
        *,
        registry: DatasetRegistry | None = None,
        downloader: DatasetDownloader | None = None,
        validator: DatasetValidator | None = None,
        preprocessor: DatasetPreprocessor | None = None,
        manager: EmbeddingManager | None = None,
        benchmark_kwargs: dict[str, Any] | None = None,
        default_modes: Sequence[FeatureMode | str] | None = None,
    ) -> None:
        self._registry = registry if registry is not None else DatasetRegistry.builtin()
        self._downloader = downloader if downloader is not None else DatasetDownloader()
        self._validator = validator if validator is not None else DatasetValidator()
        self._preprocessor = preprocessor if preprocessor is not None else DatasetPreprocessor()
        self._manager = manager if manager is not None else EmbeddingManager.default()
        self._benchmark_kwargs = dict(benchmark_kwargs or {})
        self._default_modes = tuple(
            default_modes
            if default_modes is not None
            else (
                FeatureMode.HANDCRAFTED_ONLY,
                FeatureMode.EMBEDDING_ONLY,
                FeatureMode.HYBRID,
            )
        )

    def run(
        self,
        dataset_id: str,
        *,
        modes: Sequence[FeatureMode | str] | None = None,
        k: int = 5,
        seed: int = 42,
        threshold: float = 0.5,
        ablate: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> ModeComparisonReport:
        """Benchmark every requested mode on one dataset and compare."""
        spec = self._registry.get(dataset_id)
        split_paths = self._downloader.download(spec)
        validation = self._validator.validate(spec, split_paths)
        dataset = self._preprocessor.preprocess(spec, split_paths)

        mode_list = tuple(modes) if modes else self._default_modes
        mode_reports: dict[str, dict[str, Any]] = {}
        for raw_mode in mode_list:
            mode = FeatureMode(raw_mode)
            if progress:
                progress(f"{dataset_id}: benchmarking mode {mode.value}")
            benchmark = ModeDetectionBenchmark(
                mode=mode,
                feature_extractor=ModeFeatureExtractor(mode=mode, manager=self._manager),
                evaluator_kwargs=self._benchmark_kwargs,
            )
            mode_reports[mode.value] = benchmark.run(
                dataset,
                k=k,
                seed=seed,
                threshold=threshold,
                ablate=ablate,
                progress=progress,
            )

        comparison = _build_comparison(mode_reports)
        return ModeComparisonReport(
            dataset_id=dataset_id,
            name=spec.name,
            license=spec.license,
            homepage=spec.homepage,
            validation=validation,
            modes=mode_reports,
            comparison=comparison,
            recommendation=_recommendation(comparison),
        )

    def benchmark_handcrafted_vs_embeddings(
        self,
        dataset_id: str,
        **kwargs: Any,
    ) -> ModeComparisonReport:
        """Convenience: run the three canonical modes."""
        return self.run(
            dataset_id,
            modes=(
                FeatureMode.HANDCRAFTED_ONLY,
                FeatureMode.EMBEDDING_ONLY,
                FeatureMode.HYBRID,
            ),
            **kwargs,
        )

    def run_all(
        self,
        dataset_ids: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, ModeComparisonReport]:
        """Benchmark several datasets (default: every public dataset)."""
        ids = dataset_ids if dataset_ids is not None else self._registry.public_ids()
        results: dict[str, ModeComparisonReport] = {}
        for dataset_id in ids:
            results[dataset_id] = self.run(dataset_id, **kwargs)
        return results
