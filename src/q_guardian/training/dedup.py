"""Deterministic duplicate detection, deduplication and leakage reporting.

Two hash families are used:

* ``exact_hash`` — SHA-256 over case-folded, trimmed raw text. Catches exact
  duplicates.
* ``text_hash`` — SHA-256 over Unicode-normalized, case-folded,
  whitespace-collapsed text (invisible/control characters stripped). Catches
  near-identical variants that differ only in whitespace/encoding tricks.

Hashing is deterministic across runs and platforms, so manifests and leakage
reports are reproducible.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from q_guardian.training.config import DedupConfig
    from q_guardian.training.schema import DatasetRecord

_WS_RE = re.compile(r"\s+")
# Unicode categories for invisible/control characters stripped from hashes.
_HIDDEN_CATEGORIES = frozenset({"Cf", "Cc"})


def normalized_text(text: str) -> str:
    """Return a canonical form of ``text`` for normalized duplicate hashing.

    Applies Unicode NFKC normalization, case folding, removal of
    invisible/control characters, and whitespace collapsing. Line structure
    is intentionally lost so that two prompts differing only in spacing/newlines
    hash identically.
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    text = "".join(" " if unicodedata.category(ch) in _HIDDEN_CATEGORIES else ch for ch in text)
    return _WS_RE.sub(" ", text).strip()


def exact_hash(text: str) -> str:
    """SHA-256 of case-folded, trimmed raw text."""
    return hashlib.sha256(text.strip().casefold().encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    """SHA-256 of the normalized text form."""
    return hashlib.sha256(normalized_text(text).encode("utf-8")).hexdigest()


def record_hashes(record: DatasetRecord) -> tuple[str, str]:
    """Return ``(exact_hash, text_hash)`` for a record."""
    return exact_hash(record.text), text_hash(record.text)


@dataclass
class DuplicateRemoval:
    """Record of a single duplicate removed during deduplication."""

    hash: str
    kind: str  # "exact" | "normalized"
    removed_text: str
    kept_text: str
    removed_source: str
    kept_source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "hash": self.hash,
            "kind": self.kind,
            "removed_text": self.removed_text,
            "kept_text": self.kept_text,
            "removed_source": self.removed_source,
            "kept_source": self.kept_source,
        }


@dataclass
class DedupResult:
    """Outcome of deduplicating a pool of records."""

    kept: list[DatasetRecord]
    removed: list[DuplicateRemoval]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kept": len(self.kept),
            "removed": len(self.removed),
            "removals": [r.as_dict() for r in self.removed],
        }


def dedup_records(records: list[DatasetRecord], config: DedupConfig) -> DedupResult:
    """Remove duplicate records, keeping the earliest (or latest) occurrence.

    ``keep_first=True`` keeps the earliest record per hash (deterministic
    given a stable input order); ``keep_first=False`` keeps the last
    occurrence and evicts the previously kept one.
    """
    if not config.enabled:
        return DedupResult(kept=list(records), removed=[])
    if not config.exact and not config.normalized:
        return DedupResult(kept=list(records), removed=[])

    kept: list[DatasetRecord] = []
    removed: list[DuplicateRemoval] = []
    seen_exact: dict[str, DatasetRecord] = {}
    seen_norm: dict[str, DatasetRecord] = {}

    for record in records:
        eh, nh = record_hashes(record)
        dup_kind: str | None = None
        if config.exact and eh in seen_exact:
            dup_kind = "exact"
        elif config.normalized and nh in seen_norm:
            dup_kind = "normalized"

        if dup_kind is None:
            kept.append(record)
            if config.exact:
                seen_exact.setdefault(eh, record)
            if config.normalized:
                seen_norm.setdefault(nh, record)
            continue

        prior = seen_exact.get(eh) or seen_norm.get(nh)
        if prior is None:
            kept.append(record)
            continue

        duplicate_hash = eh if dup_kind == "exact" else nh
        if config.keep_first:
            removed.append(
                DuplicateRemoval(
                    hash=duplicate_hash,
                    kind=dup_kind,
                    removed_text=record.text,
                    kept_text=prior.text,
                    removed_source=record.source,
                    kept_source=prior.source,
                )
            )
            continue

        if prior in kept:
            kept.remove(prior)
        removed.append(
            DuplicateRemoval(
                hash=duplicate_hash,
                kind=dup_kind,
                removed_text=prior.text,
                kept_text=record.text,
                removed_source=prior.source,
                kept_source=record.source,
            )
        )
        kept.append(record)
        if config.exact:
            seen_exact[eh] = record
        if config.normalized:
            seen_norm[nh] = record
    return DedupResult(kept=kept, removed=removed)


@dataclass
class LeakedSample:
    """An evaluation sample that also exists in the training pool."""

    hash: str
    kind: str  # "exact" | "normalized"
    text: str
    source: str
    split: str
    train_source: str
    train_split: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "hash": self.hash,
            "kind": self.kind,
            "text": self.text,
            "source": self.source,
            "split": self.split,
            "train_source": self.train_source,
            "train_split": self.train_split,
        }


@dataclass
class LeakageReport:
    """Cross-pool contamination report: training vs evaluation samples."""

    train_count: int
    per_split: dict[str, list[LeakedSample]] = field(default_factory=dict)

    @property
    def total_leaked(self) -> int:
        return sum(len(samples) for samples in self.per_split.values())

    def leaked_hashes(self, split: str) -> set[str]:
        """Return the set of hashes that leaked for one split."""
        return {sample.hash for sample in self.per_split.get(split, [])}

    def as_dict(self) -> dict[str, Any]:
        return {
            "train_samples": self.train_count,
            "total_leaked_samples": self.total_leaked,
            "by_split": {
                split: {
                    "count": len(samples),
                    "examples": [s.as_dict() for s in samples[:50]],
                }
                for split, samples in self.per_split.items()
            },
        }


def detect_leakage(
    train: list[DatasetRecord],
    eval_splits: dict[str, list[DatasetRecord]],
    config: DedupConfig,
) -> LeakageReport:
    """Detect evaluation samples that also appear in the training pool.

    Args:
        train: The final (deduplicated) training pool.
        eval_splits: Mapping of split name -> records, e.g.
            ``{"validation": [...], "test": [...], "external_eval": [...]}``.
        config: Dedup settings that determine which hash families are checked.

    Returns:
        A ``LeakageReport`` with per-split leaked samples.
    """
    train_exact = {exact_hash(r.text) for r in train} if config.exact else set()
    train_norm = {text_hash(r.text) for r in train} if config.normalized else set()

    per_split: dict[str, list[LeakedSample]] = {}
    train_lookup: dict[str, DatasetRecord] = {}
    if config.exact:
        for r in train:
            train_lookup.setdefault(exact_hash(r.text), r)
    if config.normalized:
        for r in train:
            train_lookup.setdefault(text_hash(r.text), r)

    for name, records in eval_splits.items():
        leaked: list[LeakedSample] = []
        for record in records:
            eh, nh = record_hashes(record)
            kind: str | None = None
            if config.exact and eh in train_exact:
                kind = "exact"
            elif config.normalized and nh in train_norm:
                kind = "normalized"
            if kind is None:
                continue
            train_record = train_lookup.get(eh) or train_lookup.get(nh)
            train_source = train_record.source if train_record is not None else "?"
            train_split = train_record.split if train_record is not None else "?"
            leaked.append(
                LeakedSample(
                    hash=eh if kind == "exact" else nh,
                    kind=kind,
                    text=record.text,
                    source=record.source,
                    split=record.split,
                    train_source=train_source,
                    train_split=train_split,
                )
            )
        per_split[name] = leaked
    return LeakageReport(train_count=len(train), per_split=per_split)


def remove_leaked(
    records: list[DatasetRecord],
    leaked_hashes: set[str],
) -> tuple[list[DatasetRecord], list[DatasetRecord]]:
    """Split ``records`` into ``(kept, removed)`` by leaked-hash membership."""
    kept: list[DatasetRecord] = []
    removed: list[DatasetRecord] = []
    for record in records:
        eh, nh = record_hashes(record)
        if eh in leaked_hashes or nh in leaked_hashes:
            removed.append(record)
        else:
            kept.append(record)
    return kept, removed
