"""Cross-dataset analytics and aggregate reporting.

A backend layer that aggregates Q-Guardian's existing benchmark, evaluation
and baseline artifacts across datasets, validates their compatibility,
computes aggregate metrics (macro / weighted / micro), ranks providers,
compares classical vs quantum performance, and analyzes internal→external
generalization. Results are emitted as JSON, CSV and Markdown reports.

It does not run detectors or download datasets; it consumes already-produced
result artifacts.
"""

from __future__ import annotations

from q_guardian.analytics.models import (
    CANONICAL_METRIC_ORDER,
    METRIC_LABELS,
    MetricStats,
    NormalizedResult,
    ordered_metric_keys,
)
from q_guardian.analytics.provider import (
    CLASSICAL_PROVIDERS,
    FUSION_PROVIDER,
    QUANTUM_PROVIDERS,
    provider_class,
)
from q_guardian.analytics.service import AnalyticsError, CrossDatasetAnalytics

__all__ = [
    "CANONICAL_METRIC_ORDER",
    "CLASSICAL_PROVIDERS",
    "FUSION_PROVIDER",
    "METRIC_LABELS",
    "QUANTUM_PROVIDERS",
    "AnalyticsError",
    "CrossDatasetAnalytics",
    "MetricStats",
    "NormalizedResult",
    "ordered_metric_keys",
    "provider_class",
]
