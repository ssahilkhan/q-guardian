"""Evaluation toolkit for measuring detection quality of the hybrid pipeline.

Provides the curated benchmark dataset, probability-based detection metrics
(ROC-AUC, PR-AUC, ECE, Brier, confusion-matrix metrics), the end-to-end
hybrid pipeline evaluator, K-fold cross-validation with ablation, and
JSON/Markdown report rendering.

Public API:
    - ``PromptBenchmarkDataset`` — labeled dataset (JSONL load/save, splits).
    - ``detection_metrics`` / ``DetectionMetrics`` — metric computations.
    - ``HybridEvaluator`` — fit + score the real hybrid pipeline.
    - ``DetectionBenchmark`` — K-fold CV + ablation.
    - ``write_json`` / ``to_markdown`` / ``write_markdown`` — reports.
"""

from q_guardian.evaluation.benchmark import DetectionBenchmark
from q_guardian.evaluation.dataset import (
    BenchmarkSample,
    PromptBenchmarkDataset,
)
from q_guardian.evaluation.metrics import (
    DetectionMetrics,
    brier_score,
    detection_metrics,
    expected_calibration_error,
    pr_auc,
    roc_auc,
)
from q_guardian.evaluation.pipeline import (
    ALL_PROVIDERS,
    ANOMALY_PROVIDER,
    CLASSIFIER_PROVIDER,
    DEFAULT_PROVIDER_WEIGHTS,
    QUANTUM_PROVIDER,
    RULE_PROVIDER,
    XGBOOST_PROVIDER,
    HybridEvaluator,
)
from q_guardian.evaluation.report import to_markdown, write_json, write_markdown

__all__ = [
    "ALL_PROVIDERS",
    "ANOMALY_PROVIDER",
    "CLASSIFIER_PROVIDER",
    "DEFAULT_PROVIDER_WEIGHTS",
    "QUANTUM_PROVIDER",
    "RULE_PROVIDER",
    "XGBOOST_PROVIDER",
    "BenchmarkSample",
    "DetectionBenchmark",
    "DetectionMetrics",
    "HybridEvaluator",
    "PromptBenchmarkDataset",
    "brier_score",
    "detection_metrics",
    "expected_calibration_error",
    "pr_auc",
    "roc_auc",
    "to_markdown",
    "write_json",
    "write_markdown",
]
