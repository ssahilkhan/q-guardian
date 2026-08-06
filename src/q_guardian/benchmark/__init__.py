"""QGuardianBench — reproducible, multi-dataset benchmarking for Q-Guardian.

Phase 1 of the V2.0 research program: a registry of public benchmark
datasets, a plain-HTTP downloader (Hugging Face datasets-server), dataset
validation, unified preprocessing into the canonical evaluation schema, and
a runner that executes the framework's real detection pipeline
(``q_guardian.evaluation.DetectionBenchmark``) per dataset.

Public API:
    - ``DatasetSpec`` / ``DatasetRegistry`` — dataset metadata + catalog.
    - ``DatasetDownloader`` / ``DatasetError`` — fetch + cache splits.
    - ``DatasetValidator`` / ``DatasetValidation`` — schema/quality checks.
    - ``DatasetPreprocessor`` — raw rows -> ``PromptBenchmarkDataset``.
    - ``BenchmarkRunner`` — download/validate/preprocess/evaluate pipeline.
    - ``BenchmarkReport`` / ``BenchmarkMetrics`` — results + metric view.
"""

from q_guardian.benchmark.download import DatasetDownloader, DatasetError
from q_guardian.benchmark.metrics import BenchmarkMetrics
from q_guardian.benchmark.preprocessing import DatasetPreprocessor
from q_guardian.benchmark.registry import DatasetRegistry, DatasetSpec
from q_guardian.benchmark.report import BenchmarkReport
from q_guardian.benchmark.run import BenchmarkRunner
from q_guardian.benchmark.validate import DatasetValidation, DatasetValidator

__all__ = [
    "BenchmarkMetrics",
    "BenchmarkReport",
    "BenchmarkRunner",
    "DatasetDownloader",
    "DatasetError",
    "DatasetPreprocessor",
    "DatasetRegistry",
    "DatasetSpec",
    "DatasetValidation",
    "DatasetValidator",
]
