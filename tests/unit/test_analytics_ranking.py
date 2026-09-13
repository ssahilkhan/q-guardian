"""Unit tests for cross-dataset provider ranking."""

from __future__ import annotations

import pytest

from q_guardian.analytics.models import MetricStats, NormalizedResult
from q_guardian.analytics.ranking import build_leaderboard


def _result(dataset_id: str, provider: str, roc: float) -> NormalizedResult:
    return NormalizedResult(
        dataset_id=dataset_id,
        name=dataset_id,
        source="benchmark",
        samples=100,
        metrics={provider: {"roc_auc": MetricStats.from_scalar(roc)}},
    )


class TestLeaderboard:
    def test_per_dataset_ranking_and_average(self) -> None:
        results = [
            _result("ds-a", "isolation-forest", 0.7),
            _result("ds-a", "fusion", 0.85),
            _result("ds-a", "qsvm", 0.88),
            _result("ds-b", "isolation-forest", 0.8),
            _result("ds-b", "fusion", 0.95),
            _result("ds-b", "qsvm", 0.7),
        ]
        board = build_leaderboard(results, metric="roc_auc")

        # ds-a ranks: iso=3, fusion=2, qsvm=1
        # ds-b ranks: qsvm=3, iso=2, fusion=1
        # avg: fusion=1.5, qsvm=2.0, iso=2.5
        assert board.order() == ["fusion", "qsvm", "isolation-forest"]
        assert board.providers["fusion"].average_rank == pytest.approx(1.5)
        assert board.providers["qsvm"].average_rank == pytest.approx(2.0)
        assert board.providers["isolation-forest"].average_rank == pytest.approx(2.5)
        assert board.providers["fusion"].datasets_ranked == 2

    def test_rows_contain_rank_and_class(self) -> None:
        results = [_result("ds-a", "fusion", 0.85), _result("ds-a", "qsvm", 0.7)]
        board = build_leaderboard(results, metric="roc_auc")

        assert len(board.rows) == 2
        row = next(r for r in board.rows if r.provider == "fusion")
        assert row.rank == 1
        assert row.cls == "fusion"

    def test_unsupported_metric_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported ranking metric"):
            build_leaderboard([], metric="unsupported")
