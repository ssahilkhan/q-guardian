"""Provider classification for cross-dataset analytics.

Maps detector provider identifiers onto the research classes used by the
aggregate reports: classical, quantum and the hybrid fusion ensemble. The
classification is data-private and central so every consumer agrees on the
same grouping.
"""

from __future__ import annotations

FUSION_PROVIDER = "fusion"

CLASSICAL_PROVIDERS = (
    "rule-engine",
    "isolation-forest",
    "random-forest",
    "xgboost",
)

QUANTUM_PROVIDERS = ("qsvm",)

_CLASS_LABELS = {
    "classical": "Classical",
    "quantum": "Quantum",
    "fusion": "Fusion",
    "other": "Other",
}


def provider_class(provider: str) -> str:
    """Classify a provider id: ``classical``, ``quantum``, ``fusion`` or ``other``."""
    if provider == FUSION_PROVIDER:
        return "fusion"
    if provider in CLASSICAL_PROVIDERS:
        return "classical"
    if provider in QUANTUM_PROVIDERS:
        return "quantum"
    return "other"


def class_label(cls: str) -> str:
    """Human-readable label for a provider class."""
    return _CLASS_LABELS.get(cls, cls)
