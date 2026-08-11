"""Deterministic, source-aware, stratified data splitting.

Rules:

* Official splits are preferred: when a source provides a ``test`` split and
  the dataset is listed in both ``train`` and ``test`` groups, the official
  ``test`` rows go straight to the internal test pool (never re-split).
* Sources listed in both ``train`` and ``validation`` are stratified by label
  into a train/validation pair; sources listed only in ``train`` keep all
  their rows in training.
* Splitting is deterministic: ``random.Random(seed)`` is seeded explicitly and
  never the global RNG.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from q_guardian.training.config import DatasetGroupConfig
    from q_guardian.training.schema import DatasetRecord

PoolName = str


def _shuffle(records: list[DatasetRecord], seed: int) -> None:
    random.Random(seed).shuffle(records)


def split_by_label(
    records: list[DatasetRecord],
    validation_ratio: float,
    seed: int,
) -> tuple[list[DatasetRecord], list[DatasetRecord]]:
    """Stratified split preserving per-label balance.

    Returns ``(train, validation)``. Both classes are shuffled with the same
    seeded RNG and split at ``validation_ratio``.
    """
    if validation_ratio <= 0.0:
        return records, []
    by_label: dict[int, list[DatasetRecord]] = {}
    for record in records:
        by_label.setdefault(record.label, []).append(record)

    train: list[DatasetRecord] = []
    validation: list[DatasetRecord] = []
    for group in by_label.values():
        _shuffle(group, seed)
        n_validation = round(len(group) * validation_ratio)
        validation.extend(group[:n_validation])
        train.extend(group[n_validation:])
    return train, validation


def assign_groups(
    records: list[DatasetRecord],
    groups: DatasetGroupConfig,
) -> dict[str, list[DatasetRecord]]:
    """Assign records to ``train`` / ``validation`` / ``test`` / ``external_eval``.

    Official ``test``-split rows of a dataset listed in both ``train`` and
    ``test`` go to the internal test pool; all other rows of train-group
    datasets go to the train pool. Validation/test/external sources map
    directly to their pools. Unlisted sources are never used for training and
    fall back to ``external_eval`` (or ``test`` for an official test split).
    """
    train_set = set(groups.train)
    validation_set = set(groups.validation)
    test_set = set(groups.test)
    external_set = set(groups.external_eval)

    pools: dict[str, list[DatasetRecord]] = {
        "train": [],
        "validation": [],
        "test": [],
        "external_eval": [],
    }
    for record in records:
        if record.source in train_set:
            if record.split == "test" and record.source in test_set:
                pools["test"].append(record)
            else:
                pools["train"].append(record)
        elif record.source in validation_set:
            pools["validation"].append(record)
        elif record.source in test_set:
            pools["test"].append(record)
        elif record.source in external_set:
            pools["external_eval"].append(record)
        elif record.split == "test":
            pools["test"].append(record)
        else:
            pools["external_eval"].append(record)
    return pools


def split_train_pool(
    train_pool: list[DatasetRecord],
    validation_sources: Iterable[str],
    validation_ratio: float,
    seed: int,
) -> tuple[list[DatasetRecord], list[DatasetRecord]]:
    """Stratify train-pool records of validation-group sources into train/val.

    Sources not listed in ``validation_sources`` keep every row in training.
    Returns ``(train, validation)``.
    """
    validation_set = set(validation_sources)
    by_source: dict[str, list[DatasetRecord]] = {}
    for record in train_pool:
        by_source.setdefault(record.source, []).append(record)

    train: list[DatasetRecord] = []
    validation: list[DatasetRecord] = []
    for source, source_records in by_source.items():
        if source in validation_set:
            t, v = split_by_label(source_records, validation_ratio, seed)
            train.extend(t)
            validation.extend(v)
        else:
            train.extend(source_records)
    return train, validation


def cap_records(
    records: list[DatasetRecord],
    cap: int | None,
    seed: int,
) -> tuple[list[DatasetRecord], int]:
    """Cap a per-source record list while preserving class balance.

    Returns ``(kept, removed_count)``. When the source exceeds ``cap`` the
    kept subset is chosen deterministically (seeded shuffle per label) so the
    label ratio of the original source is preserved. ``cap=None`` keeps all.
    """
    if cap is None or len(records) <= cap:
        return records, 0
    by_label: dict[int, list[DatasetRecord]] = {}
    for record in records:
        by_label.setdefault(record.label, []).append(record)

    kept: list[DatasetRecord] = []
    remaining = cap
    for group in by_label.values():
        if remaining <= 0:
            break
        _shuffle(group, seed)
        share = round(cap * len(group) / len(records))
        take = max(1, share) if group else 0
        take = min(take, remaining, len(group))
        kept.extend(group[:take])
        remaining -= take
    return kept, len(records) - len(kept)
