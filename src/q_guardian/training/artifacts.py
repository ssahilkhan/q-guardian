"""Artifact helpers for training runs: run directory layout, JSON and splits.

The canonical training-run directory looks like::

    <output_dir>/
      dataset_manifest.json     # per-dataset + per-pool counts (prepare)
      leakage_report.json       # train/eval contamination report (prepare)
      label_distribution.json   # label + category counts (prepare)
      splits/
        train.jsonl
        validation.jsonl
        test.jsonl
        external_eval.jsonl
      training_config.json      # frozen pipeline configuration (train)
      training_log.txt          # human-readable training log (train)
      metrics.json              # holdout/validation metrics (train)
      model/                    # HybridEvaluator checkpoint (train)
      evaluation.json           # per-dataset security metrics matrix (evaluate)
      evaluation.md             # rendered matrix (evaluate)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from q_guardian.training.schema import DatasetRecord

SPLIT_FILES = {
    "train": "train.jsonl",
    "validation": "validation.jsonl",
    "test": "test.jsonl",
    "external_eval": "external_eval.jsonl",
}


def write_json(path: str | Path, data: Any) -> None:
    """Write ``data`` as pretty JSON to ``path`` (mkdir parents)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def label_distribution(records: list[DatasetRecord]) -> dict[str, Any]:
    """Compute label and category counts for a pool of records."""
    labels: dict[str, int] = {"benign": 0, "malicious": 0}
    categories: dict[str, int] = {}
    for record in records:
        labels["benign" if record.label == 0 else "malicious"] += 1
        categories[record.category] = categories.get(record.category, 0) + 1
    return {
        "total": len(records),
        "labels": labels,
        "categories": categories,
    }


def write_splits(
    run_dir: str | Path,
    pools: dict[str, list[DatasetRecord]],
) -> None:
    """Persist each pool as JSONL under ``run_dir/splits``."""
    splits_dir = Path(run_dir) / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    for name, records in pools.items():
        filename = SPLIT_FILES.get(name)
        if filename is None:
            continue
        with open(splits_dir / filename, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def read_splits(run_dir: str | Path) -> dict[str, list[DatasetRecord]]:
    """Load prepared pools from ``run_dir/splits``."""
    splits_dir = Path(run_dir) / "splits"
    result: dict[str, list[DatasetRecord]] = {}
    for pool, filename in SPLIT_FILES.items():
        path = splits_dir / filename
        if not path.exists():
            continue
        records: list[DatasetRecord] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(DatasetRecord.from_dict(json.loads(line)))
        result[pool] = records
    return result
