"""Benchmark runner: download -> validate -> preprocess -> evaluate.

Orchestrates the full QGuardianBench pipeline for one or more registered
datasets. Every component (downloader, validator, preprocessor, evaluation
backend) is injectable, which keeps the runner usable with local fixtures
in tests and with real Hugging Face downloads in production.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from q_guardian.benchmark.download import DatasetDownloader
from q_guardian.benchmark.preprocessing import DatasetPreprocessor
from q_guardian.benchmark.registry import DatasetRegistry
from q_guardian.benchmark.report import BenchmarkReport
from q_guardian.benchmark.validate import DatasetValidator
from q_guardian.evaluation.benchmark import DetectionBenchmark

if TYPE_CHECKING:
    from collections.abc import Callable


class BenchmarkRunner:
    """Runs the framework's real detection pipeline per benchmark dataset.

    Args:
        registry: Dataset catalog (defaults to the built-in registry).
        downloader: Fetches dataset splits into a local cache.
        validator: Quality-checks downloaded splits.
        preprocessor: Maps raw rows onto ``PromptBenchmarkDataset``.
        benchmark_kwargs: Keyword arguments forwarded to
            ``DetectionBenchmark`` / ``HybridEvaluator`` for every run
            (e.g. ``{"quantum": False, "n_estimators": 20}``).
    """

    def __init__(
        self,
        *,
        registry: DatasetRegistry | None = None,
        downloader: DatasetDownloader | None = None,
        validator: DatasetValidator | None = None,
        preprocessor: DatasetPreprocessor | None = None,
        benchmark_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._registry = registry if registry is not None else DatasetRegistry.builtin()
        self._downloader = downloader if downloader is not None else DatasetDownloader()
        self._validator = validator if validator is not None else DatasetValidator()
        self._preprocessor = preprocessor if preprocessor is not None else DatasetPreprocessor()
        self._benchmark_kwargs = dict(benchmark_kwargs or {})

    def run(
        self,
        dataset_id: str,
        *,
        k: int = 5,
        seed: int = 42,
        threshold: float = 0.5,
        ablate: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> BenchmarkReport:
        """Run the full pipeline for one dataset and return its report.

        Args:
            dataset_id: Registry key of the dataset to benchmark.
            k: Number of cross-validation folds.
            seed: Random seed for fold generation.
            threshold: Decision threshold for binary metrics.
            ablate: Whether to also run provider ablation.
            progress: Optional callback for progress messages.

        Raises:
            KeyError: If the dataset is not registered.
            DatasetError: If the dataset cannot be downloaded.
        """
        spec = self._registry.get(dataset_id)
        split_paths = self._downloader.download(spec)
        validation = self._validator.validate(spec, split_paths)
        dataset = self._preprocessor.preprocess(spec, split_paths)

        if progress:
            progress(
                f"{dataset_id}: {len(dataset)} samples "
                f"({dataset.positives()} threats / {dataset.negatives()} benign)"
            )

        benchmark = DetectionBenchmark(evaluator_kwargs=self._benchmark_kwargs)
        report = benchmark.run(
            dataset,
            k=k,
            seed=seed,
            threshold=threshold,
            ablate=ablate,
            progress=progress,
        )
        report["config"]["dataset_id"] = dataset_id

        return BenchmarkReport(
            dataset_id=dataset_id,
            name=spec.name,
            license=spec.license,
            homepage=spec.homepage,
            validation=validation,
            benchmark=report,
        )

    def run_all(
        self,
        dataset_ids: list[str] | None = None,
        *,
        k: int = 5,
        seed: int = 42,
        threshold: float = 0.5,
        ablate: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, BenchmarkReport]:
        """Run benchmarks for several datasets, keyed by ``dataset_id``.

        When ``dataset_ids`` is omitted every public (token-less) dataset
        in the registry is benchmarked.
        """
        ids = dataset_ids if dataset_ids is not None else self._registry.public_ids()
        results: dict[str, BenchmarkReport] = {}
        for dataset_id in ids:
            results[dataset_id] = self.run(
                dataset_id,
                k=k,
                seed=seed,
                threshold=threshold,
                ablate=ablate,
                progress=progress,
            )
        return results
