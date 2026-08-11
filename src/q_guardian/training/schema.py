"""Canonical schema for dataset preparation and training.

Every external dataset is normalized onto this canonical record before it
enters the training, validation, test or external-evaluation pools. The
canonical binary label space is fixed and documented:

    0 = benign
    1 = malicious / injection

Original attack categories (when the source provides them) are preserved in
``category`` so per-category reporting remains possible without throwing the
information away. Rows are never silently relabeled: if a source only offers
a binary label, the generic fallback category ``malicious`` is used for
positive rows instead of inventing a fine-grained label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LABEL_BENIGN = 0
LABEL_MALICIOUS = 1

LABEL_NAMES: dict[int, str] = {
    LABEL_BENIGN: "benign",
    LABEL_MALICIOUS: "malicious",
}

# Category tag used when a source provides no explicit category column.
DEFAULT_CATEGORY = "benign"
# Fallback category for malicious rows whose source has no category column.
GENERIC_MALICIOUS_CATEGORY = "malicious"


@dataclass(frozen=True)
class DatasetRecord:
    """One canonical, normalized dataset example.

    Args:
        text: The prompt text (kept verbatim from the source so raw attack
            strings stay inspectable).
        label: Canonical binary label (``0`` = benign, ``1`` = malicious).
        source: Stable ``dataset_id`` of the source dataset (registry key).
        split: Original split name from the source (``train``/``test``/...).
        category: Attack-category tag preserved from the source, or the
            ``benign`` / ``malicious`` fallbacks.
        metadata: Source-specific extra data (e.g. the raw row) kept for
            auditability without affecting the canonical columns.
    """

    text: str
    label: int
    source: str
    split: str = "default"
    category: str = DEFAULT_CATEGORY
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "text": self.text,
            "label": self.label,
            "source": self.source,
            "split": self.split,
            "category": self.category,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatasetRecord:
        """Rehydrate a record from ``to_dict()`` output."""
        return cls(
            text=str(data["text"]),
            label=int(data["label"]),
            source=str(data["source"]),
            split=str(data.get("split", "default")),
            category=str(data.get("category", DEFAULT_CATEGORY)),
            metadata=dict(data.get("metadata", {}) or {}),
        )
