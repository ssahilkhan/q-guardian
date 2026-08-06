"""Benchmark metrics facade over the detection evaluation toolkit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from q_guardian.evaluation.metrics import DetectionMetrics

if TYPE_CHECKING:
    from q_guardian.benchmark.report import BenchmarkReport


class BenchmarkMetrics:
    """Read-only view of the per-provider metric aggregates of a run.

    The underlying numbers are produced by ``DetectionBenchmark`` (via
    ``q_guardian.evaluation``); this class exposes the fused and per-provider
    aggregates plus the ROC-AUC ranking, and re-exports the pure-Python
    metric computations for arbitrary score arrays.
    """

    def __init__(self, report: BenchmarkReport) -> None:
        self._report = report

    def provider(self, provider_id: str) -> dict[str, Any]:
        """Return the aggregate metric block for one provider."""
        result: dict[str, Any] = self._report.provider_metrics().get(provider_id, {})
        return result

    def fusion(self) -> dict[str, Any]:
        """Return the fused (ensemble) aggregate metric block."""
        return self.provider("fusion")

    @property
    def ranking(self) -> list[dict[str, Any]]:
        """Return the provider ROC-AUC ranking (best first)."""
        return self._report.ranking()

    @staticmethod
    def compute(
        y_true: list[int],
        scores: list[float],
        threshold: float = 0.5,
    ) -> dict[str, Any]:
        """Compute detection metrics from raw labels and threat scores."""
        return DetectionMetrics.compute(y_true, scores, threshold=threshold)
