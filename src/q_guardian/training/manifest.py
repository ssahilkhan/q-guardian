"""Dataset manifest: per-dataset counts and per-pool statistics.

The manifest makes every count auditable. Per dataset it records:

* ``requested``    — raw rows read from the downloaded split files
* ``filtered``     — rows dropped during normalization (invalid text/label)
* ``loaded``       — valid normalized records before capping
* ``capped``       — rows dropped by the configured per-dataset cap
* ``deduplicated`` — rows removed as duplicates within the training pool
* ``leaked``       — rows removed from evaluation pools due to training leakage
* ``final``        — records kept for the pipeline
* ``available``    — whether the dataset could be downloaded at all

Per pool it records total / benign / malicious counts.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from q_guardian.training.config import TrainingPipelineConfig
    from q_guardian.training.schema import DatasetRecord


@dataclass
class DatasetCounts:
    """Load/processing counts for a single source dataset."""

    source: str
    requested: int = 0
    filtered: int = 0
    loaded: int = 0
    capped: int = 0
    deduplicated: int = 0
    leaked: int = 0
    final: int = 0
    available: bool = True
    unavailable_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetManifest:
    """Reproducible record of a preparation run."""

    seed: int
    generated_at: str
    groups: dict[str, list[str]]
    datasets: dict[str, DatasetCounts]
    pools: dict[str, dict[str, int]]

    @classmethod
    def build(
        cls,
        config: TrainingPipelineConfig,
        counts: dict[str, DatasetCounts],
        pools: dict[str, list[DatasetRecord]],
    ) -> DatasetManifest:
        """Build a manifest from the prepared pools and per-source counts."""
        pool_stats: dict[str, dict[str, int]] = {}
        for name, records in pools.items():
            benign = sum(1 for r in records if r.label == 0)
            pool_stats[name] = {
                "samples": len(records),
                "benign": benign,
                "malicious": len(records) - benign,
            }
        return cls(
            seed=config.seed,
            generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
            groups={
                "train": list(config.datasets.train),
                "validation": list(config.datasets.validation),
                "test": list(config.datasets.test),
                "external_eval": list(config.datasets.external_eval),
            },
            datasets=counts,
            pools=pool_stats,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "generated_at": self.generated_at,
            "groups": self.groups,
            "datasets": {name: counts.as_dict() for name, counts in self.datasets.items()},
            "pools": self.pools,
        }

    def to_file(self, path: str | Path) -> None:
        """Serialize the manifest to a JSON file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self.as_dict(), f, indent=2, ensure_ascii=False)
