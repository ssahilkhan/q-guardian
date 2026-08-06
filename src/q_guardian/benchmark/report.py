"""Report container for single-dataset benchmark runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from q_guardian.benchmark.metrics import BenchmarkMetrics

if TYPE_CHECKING:
    from q_guardian.benchmark.validate import DatasetValidation


@dataclass
class BenchmarkReport:
    """High-level results of a single-dataset benchmark run.

    Wraps the raw ``DetectionBenchmark`` report together with dataset
    metadata and the validation outcome so every number is traceable to a
    source, license and quality check.
    """

    dataset_id: str
    name: str
    license: str
    homepage: str
    validation: DatasetValidation
    benchmark: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialize the report (metadata + validation + benchmark)."""
        return {
            "dataset": {
                "id": self.dataset_id,
                "name": self.name,
                "license": self.license,
                "homepage": self.homepage,
            },
            "validation": self.validation.as_dict(),
            "benchmark": self.benchmark,
        }

    def provider_metrics(self) -> dict[str, Any]:
        """Return the per-provider aggregate metrics from the run."""
        result: dict[str, Any] = self.benchmark.get("cross_validation", {}).get("metrics", {})
        return result

    def ranking(self) -> list[dict[str, Any]]:
        """Return the provider ROC-AUC ranking (best first)."""
        result: list[dict[str, Any]] = self.benchmark.get("cross_validation", {}).get(
            "roc_auc_ranking", []
        )
        return result

    @property
    def metrics(self) -> BenchmarkMetrics:
        """A read-only facade over this report's metric aggregates."""
        return BenchmarkMetrics(self)
