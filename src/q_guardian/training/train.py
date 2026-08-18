"""Training pipeline: fit the existing hybrid detector on prepared data.

Training reuses ``q_guardian.evaluation.HybridEvaluator`` — the framework's
real injection-detection model (normalizer -> feature extractor -> rule engine
-> isolation forest -> random forest -> optional quantum QSVM -> weighted-voting
fusion). No second training framework is introduced; this module only wires the
prepared train/validation pools into that evaluator and writes the run
artifacts:

* ``training_config.json`` — frozen pipeline configuration
* ``metrics.json`` — holdout/validation metrics from ``evaluate()``
* ``model/`` — ``HybridEvaluator`` joblib checkpoint
* ``training_log.txt`` — human-readable training log

``epochs`` / ``batch_size`` / ``learning_rate`` are accepted by the CLI for
interface parity but are recorded, not applied: the hybrid pipeline is
scikit-learn/quantum based, not a neural trainer.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.evaluation.dataset import BenchmarkSample, PromptBenchmarkDataset
from q_guardian.evaluation.pipeline import HybridEvaluator
from q_guardian.ml.models.classifier import XGBoostThreatClassifier
from q_guardian.training.artifacts import label_distribution, write_json

if TYPE_CHECKING:
    from collections.abc import Callable

    from q_guardian.training.config import TrainingPipelineConfig
    from q_guardian.training.prepare import PreparedDatasets
    from q_guardian.training.schema import DatasetRecord

logger = structlog.get_logger("training.train")


@dataclass
class TrainingRun:
    """Result of a training run, with artifact locations."""

    config: TrainingPipelineConfig
    output_dir: Path
    train_samples: int
    validation_samples: int
    metrics: dict[str, Any]
    checkpoint_dir: Path
    training_log_path: Path
    elapsed_seconds: float
    extra: dict[str, Any] = field(default_factory=dict)


class TrainingPipeline:
    """Fits ``HybridEvaluator`` on prepared training data.

    Args:
        evaluator_factory: Callable returning a ``HybridEvaluator``-like
            object (test seam; defaults to ``HybridEvaluator``).
    """

    def __init__(
        self,
        evaluator_factory: Callable[..., HybridEvaluator] | None = None,
    ) -> None:
        self._evaluator_factory = evaluator_factory or HybridEvaluator

    def train(
        self,
        config: TrainingPipelineConfig,
        prepared: PreparedDatasets,
        *,
        output_dir: str | Path | None = None,
        max_samples_per_class: int | None = None,
    ) -> TrainingRun:
        """Train the hybrid detector and persist run artifacts.

        Args:
            config: Pipeline configuration.
            prepared: Datasets prepared by ``DatasetPreparationPipeline``.
            output_dir: Run directory (defaults to ``prepared.output_dir``).
            max_samples_per_class: Optional override of the configured
                per-class training cap.

        Raises:
            ValueError: If there is no usable training data.
        """
        run_dir = Path(output_dir) if output_dir is not None else prepared.output_dir
        run_dir.mkdir(parents=True, exist_ok=True)

        cap = (
            max_samples_per_class
            if max_samples_per_class is not None
            else config.max_samples_per_class
        )
        train_records = self._cap_train(config, prepared.train, cap)
        if not train_records:
            msg = "no training samples available"
            raise ValueError(msg)

        evaluator = self._evaluator_factory(**config.evaluator_kwargs())
        start = time.monotonic()
        evaluator.fit(
            [record.text for record in train_records],
            [record.label for record in train_records],
        )
        elapsed = round(time.monotonic() - start, 3)

        checkpoint_dir = run_dir / "model"
        evaluator.save_state(checkpoint_dir)

        validation_metrics = self._validation_metrics(evaluator, config, prepared.validation)

        write_json(run_dir / "training_config.json", config.as_dict())
        metrics: dict[str, Any] = {
            "train_samples": len(train_records),
            "validation_samples": len(prepared.validation),
            "elapsed_seconds": elapsed,
            "validation": validation_metrics,
        }
        write_json(run_dir / "metrics.json", metrics)
        write_json(
            run_dir / "label_distribution.json",
            {name: label_distribution(records) for name, records in prepared.splits().items()},
        )

        log_path = self._write_log(
            run_dir,
            config,
            train_records,
            prepared.validation,
            validation_metrics,
            elapsed,
        )
        logger.info(
            "training_completed",
            train_samples=len(train_records),
            validation_samples=len(prepared.validation),
            elapsed_seconds=elapsed,
            checkpoint=str(checkpoint_dir),
        )
        return TrainingRun(
            config=config,
            output_dir=run_dir,
            train_samples=len(train_records),
            validation_samples=len(prepared.validation),
            metrics=metrics,
            checkpoint_dir=checkpoint_dir,
            training_log_path=log_path,
            elapsed_seconds=elapsed,
        )

    @staticmethod
    def _cap_train(
        config: TrainingPipelineConfig,
        records: list[DatasetRecord],
        cap: int | None,
    ) -> list[DatasetRecord]:
        if cap is None:
            return records
        by_label: dict[int, list[DatasetRecord]] = {}
        for record in records:
            by_label.setdefault(record.label, []).append(record)
        kept: list[DatasetRecord] = []
        for group in by_label.values():
            group = list(group)
            group.sort(key=lambda r: (r.text, r.source))
            kept.extend(group[:cap])
        return kept

    @staticmethod
    def _validation_metrics(
        evaluator: HybridEvaluator,
        config: TrainingPipelineConfig,
        validation: list[DatasetRecord],
    ) -> dict[str, Any]:
        if not validation:
            return {"note": "no validation split configured"}
        dataset = PromptBenchmarkDataset(
            [BenchmarkSample(r.text, r.label, r.category) for r in validation]
        )
        result = evaluator.evaluate(dataset, threshold=config.eval.threshold)
        return {provider: metrics for provider, metrics in result.items() if provider != "scores"}

    @staticmethod
    def _write_log(
        run_dir: Path,
        config: TrainingPipelineConfig,
        train_records: list[DatasetRecord],
        validation: list[DatasetRecord],
        validation_metrics: dict[str, Any],
        elapsed: float,
    ) -> Path:
        path = run_dir / "training_log.txt"
        lines = [
            "Q-Guardian training log",
            "=" * 60,
            f"timestamp            : {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"seed                 : {config.seed}",
            f"train sources        : {', '.join(config.datasets.train)}",
            f"validation sources   : {', '.join(config.datasets.validation)}",
            f"test sources         : {', '.join(config.datasets.test)}",
            f"external eval sources: {', '.join(config.datasets.external_eval)}",
            f"model                : quantum={config.model.quantum} "
            f"n_estimators={config.model.n_estimators} "
            f"contamination={config.model.contamination}",
            f"xgboost              : available={XGBoostThreatClassifier().is_available} "
            "(classical classifier provider; skipped only if the optional "
            "dependency is not installed)",
            f"train samples        : {len(train_records)}",
            f"validation samples   : {len(validation)}",
            f"elapsed              : {elapsed}s",
            "",
            "Validation metrics:",
            json.dumps(validation_metrics, indent=2, ensure_ascii=False),
            "",
            "NOTE: epochs/batch_size/learning_rate are recorded for CLI parity",
            "but the hybrid pipeline is scikit-learn/quantum based and does not",
            "apply them.",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
