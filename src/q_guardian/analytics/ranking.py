"""Cross-dataset provider ranking and leaderboards.

Within each dataset the providers are ranked by a chosen metric (mean value).
Across datasets each provider's average rank is produced, together with the
per-dataset comparison table. Average rank is the robust cross-dataset
comparison because it is largely insensitive to dataset difficulty; it is
reported alongside raw metric means, never instead of them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from q_guardian.analytics import provider as provider_module

if TYPE_CHECKING:
    from q_guardian.analytics.models import NormalizedResult

_RANKING_METRICS = ("roc_auc", "f1_score", "accuracy")


@dataclass
class RankedRow:
    """Rank of one provider on one dataset for one metric."""

    dataset_id: str
    provider: str
    cls: str
    value: float | None
    rank: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "provider": self.provider,
            "class": self.cls,
            "value": self.value,
            "rank": self.rank,
        }


@dataclass
class LeaderboardEntry:
    """Average rank and mean metric value for one provider across datasets."""

    provider: str
    cls: str
    metric: str
    average_rank: float
    datasets_ranked: int
    mean_value: float
    ranks: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "class": self.cls,
            "metric": self.metric,
            "average_rank": self.average_rank,
            "datasets_ranked": self.datasets_ranked,
            "mean_value": self.mean_value,
            "ranks": self.ranks,
        }


@dataclass
class Leaderboard:
    """Cross-dataset leaderboard for a collection of results."""

    metric: str
    providers: dict[str, LeaderboardEntry] = field(default_factory=dict)
    rows: list[RankedRow] = field(default_factory=list)

    def order(self) -> list[str]:
        """Provider ids ordered best-to-worst by average rank."""
        return sorted(
            self.providers,
            key=lambda pid: (
                self.providers[pid].average_rank,
                -self.providers[pid].mean_value,
                pid,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "rows": [row.as_dict() for row in self.rows],
            "leaderboard": [
                self.providers[pid].as_dict() for pid in self.order() if pid in self.providers
            ],
        }


def build_leaderboard(
    results: list[NormalizedResult],
    metric: str = "roc_auc",
) -> Leaderboard:
    """Build a per-dataset ranking and average-rank leaderboard."""
    board = Leaderboard(metric=metric)
    if metric not in _RANKING_METRICS:
        raise ValueError(f"Unsupported ranking metric: {metric!r}")

    by_dataset: dict[str, dict[str, float]] = {}
    for result in results:
        for pid, _stats in result.metrics.items():
            lookup = result.provider_metric(pid, metric)
            if lookup is None:
                continue
            by_dataset.setdefault(result.dataset_id, {})[pid] = lookup.mean

    for dataset_id, values in by_dataset.items():
        ranked = sorted(values.items(), key=lambda item: item[1], reverse=True)
        for rank, (pid, value) in enumerate(ranked, start=1):
            board.rows.append(
                RankedRow(
                    dataset_id=dataset_id,
                    provider=pid,
                    cls=provider_module.provider_class(pid),
                    value=value,
                    rank=rank,
                )
            )

    ranks_by_provider: dict[str, list[int]] = {}
    means_by_provider: dict[str, list[float]] = {}
    for row in board.rows:
        if row.rank is None:
            continue
        ranks_by_provider.setdefault(row.provider, []).append(row.rank)
        if row.value is not None:
            means_by_provider.setdefault(row.provider, []).append(row.value)

    for pid, ranks in ranks_by_provider.items():
        dataset_count = len(ranks)
        board.providers[pid] = LeaderboardEntry(
            provider=pid,
            cls=provider_module.provider_class(pid),
            metric=metric,
            average_rank=round(sum(ranks) / dataset_count, 6),
            datasets_ranked=dataset_count,
            mean_value=round(_fmean_or_zero(means_by_provider.get(pid, [])), 6),
            ranks=ranks,
        )
    return board


def _fmean_or_zero(values: list[float]) -> float:
    if not values:
        return 0.0
    total = 0.0
    for value in values:
        if math.isfinite(value):
            total += value
    return total / len(values)
