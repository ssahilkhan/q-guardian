"""Dataset preparation + training pipeline for the injection-detection model.

This package turns the benchmark dataset registry into reproducible
training/evaluation runs for Q-Guardian's hybrid detector
(``q_guardian.evaluation.HybridEvaluator``). It is intentionally thin: it
reuses the existing dataset registry/downloader/preprocessing layer
(``q_guardian.benchmark``) and the existing detection pipeline
(``q_guardian.evaluation``) rather than introducing a competing framework.

Public API:
    - ``DatasetRecord`` / label constants — canonical schema (``schema``).
    - ``TrainingPipelineConfig`` / dataset groups — configuration (``config``).
    - ``DatasetPreparationPipeline`` / ``PreparedDatasets`` — prepare stage.
    - ``TrainingPipeline`` — train the hybrid detector.
    - ``EvaluationPipeline`` / ``EvaluationReport`` — security metrics matrix.
    - ``detect_leakage`` / ``dedup_records`` — leakage protection (``dedup``).
"""

from q_guardian.training.config import (
    DatasetGroupConfig,
    DedupConfig,
    EvalConfig,
    ModelConfig,
    TrainingPipelineConfig,
)
from q_guardian.training.dedup import (
    DedupResult,
    DuplicateRemoval,
    LeakageReport,
    LeakedSample,
    dedup_records,
    detect_leakage,
    exact_hash,
    normalized_text,
    remove_leaked,
    text_hash,
)
from q_guardian.training.evaluate import EvaluationPipeline, EvaluationReport
from q_guardian.training.manifest import DatasetCounts, DatasetManifest
from q_guardian.training.normalize import DatasetRecordPreprocessor
from q_guardian.training.prepare import DatasetPreparationPipeline, PreparedDatasets
from q_guardian.training.schema import (
    DEFAULT_CATEGORY,
    GENERIC_MALICIOUS_CATEGORY,
    LABEL_BENIGN,
    LABEL_MALICIOUS,
    LABEL_NAMES,
    DatasetRecord,
)
from q_guardian.training.train import TrainingPipeline, TrainingRun

__all__ = [
    "DEFAULT_CATEGORY",
    "GENERIC_MALICIOUS_CATEGORY",
    "LABEL_BENIGN",
    "LABEL_MALICIOUS",
    "LABEL_NAMES",
    "DatasetCounts",
    "DatasetGroupConfig",
    "DatasetManifest",
    "DatasetPreparationPipeline",
    "DatasetRecord",
    "DatasetRecordPreprocessor",
    "DedupConfig",
    "DedupResult",
    "DuplicateRemoval",
    "EvalConfig",
    "EvaluationPipeline",
    "EvaluationReport",
    "LeakageReport",
    "LeakedSample",
    "ModelConfig",
    "PreparedDatasets",
    "TrainingPipeline",
    "TrainingPipelineConfig",
    "TrainingRun",
    "dedup_records",
    "detect_leakage",
    "exact_hash",
    "normalized_text",
    "remove_leaked",
    "text_hash",
]
