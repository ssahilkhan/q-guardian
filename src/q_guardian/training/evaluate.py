"""Evaluation pipeline: per-dataset security metrics matrix + threshold analysis.

This is the measurement stage. After training, the fitted ``HybridEvaluator``
is scored on:

* the internal test pool (official held-out split when available)
* the validation pool (diagnostic)
* every external generalization dataset (never seen in training)

and a per-dataset matrix is produced that makes it obvious whether Q-Guardian
generalizes beyond its training distribution:

    Dataset                    Samples  Detection  Benign-rej  FPR    FNR    F1
    --------------------------------------------------------------------------
    deepset-prompt-injections  ...
    JailbreakBench/JBB-Behaviors ...

Metrics are computed from real model output only. Datasets that could not be
downloaded (e.g. gated without a token) appear as ``available: false`` rows —
no metrics are fabricated for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.evaluation.metrics import detection_metrics
from q_guardian.evaluation.pipeline import HybridEvaluator
from q_guardian.training.artifacts import write_json

if TYPE_CHECKING:
    from q_guardian.training.config import TrainingPipelineConfig
    from q_guardian.training.prepare import PreparedDatasets
    from q_guardian.training.schema import DatasetRecord

logger = structlog.get_logger("training.evaluate")


@dataclass
class EvaluationReport:
    """The full evaluation output: matrix, per-category, threshold analysis."""

    config: TrainingPipelineConfig
    matrix: list[dict[str, Any]]
    per_category: list[dict[str, Any]]
    threshold_analysis: list[dict[str, Any]]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.as_dict(),
            "matrix": self.matrix,
            "per_category": self.per_category,
            "threshold_analysis": self.threshold_analysis,
            "summary": self.summary,
        }

    def to_markdown(self) -> str:
        """Render the evaluation matrix as Markdown (for humans/CI)."""
        lines = [
            "# Q-Guardian Evaluation Report",
            "",
            "## Per-dataset detection matrix",
            "",
            "| Dataset | Pool | Samples | Benign | Malicious | Detection rate | "
            "Benign rejection | FPR | FNR | F1 | ROC-AUC |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in self.matrix:
            lines.append(
                f"| {row['dataset']} | {row['pool']} | {row['samples']} | "
                f"{row['benign']} | {row['malicious']} | "
                f"{_fmt_pct(row['detection_rate'])} | "
                f"{_fmt_pct(row['benign_rejection_rate'])} | "
                f"{_fmt_pct(row['fpr'])} | {_fmt_pct(row['fnr'])} | "
                f"{_fmt_pct(row['f1'])} | {_fmt_pct(row['roc_auc'])} |"
            )
        lines.append("")
        if self.per_category:
            lines.append("## Per-category detection rate")
            lines.append("")
            lines.append("| Category | Samples | Malicious | Detection rate | Benign rejection |")
            lines.append("| --- | --- | --- | --- | --- |")
            for row in self.per_category:
                lines.append(
                    f"| {row['category']} | {row['samples']} | {row['malicious']} | "
                    f"{_fmt_pct(row['detection_rate'])} | "
                    f"{_fmt_pct(row['benign_rejection_rate'])} |"
                )
            lines.append("")
        if self.threshold_analysis:
            lines.append("## Threshold analysis (internal test)")
            lines.append("")
            lines.append("| Threshold | Precision | Recall | F1 | FPR |")
            lines.append("| --- | --- | --- | --- | --- |")
            for row in self.threshold_analysis:
                lines.append(
                    f"| {row['threshold']} | {_fmt_pct(row['precision'])} | "
                    f"{_fmt_pct(row['recall'])} | {_fmt_pct(row['f1'])} | "
                    f"{_fmt_pct(row['fpr'])} |"
                )
            lines.append("")
        summary = self.summary
        lines.append("## Summary")
        lines.append("")
        for key in (
            "datasets_evaluated",
            "external_datasets_evaluated",
            "total_samples_evaluated",
            "mean_external_detection_rate",
            "mean_external_benign_rejection_rate",
            "mean_external_f1",
            "internal_test_detection_rate",
            "internal_test_benign_rejection_rate",
            "internal_test_f1",
            "best_threshold",
            "best_threshold_f1",
        ):
            if key in summary:
                lines.append(f"- **{key}**: {summary[key]}")
        lines.append("")
        return "\n".join(lines) + "\n"


class EvaluationPipeline:
    """Scores a fitted detector over all evaluation pools and reports metrics.

    Args:
        evaluator: A fitted ``HybridEvaluator``. When ``None`` it is loaded
            from ``checkpoint_dir``.
    """

    def __init__(self, evaluator: HybridEvaluator | None = None) -> None:
        self._evaluator = evaluator

    def evaluate(
        self,
        config: TrainingPipelineConfig,
        prepared: PreparedDatasets,
        *,
        checkpoint_dir: str | Path | None = None,
        output_dir: str | Path | None = None,
    ) -> EvaluationReport:
        """Run the evaluation and persist ``evaluation.json`` / ``evaluation.md``.

        Args:
            config: Pipeline configuration (threshold, sweep, model params).
            prepared: Prepared datasets (train is unused here, kept for
                signature symmetry).
            checkpoint_dir: Where to load the evaluator from when
                ``self._evaluator`` is None.
            output_dir: Where reports are written (defaults to
                ``prepared.output_dir``).

        Raises:
            RuntimeError: If no fitted evaluator is available.
        """
        evaluator = self._evaluator or self._load_evaluator(checkpoint_dir)
        run_dir = Path(output_dir) if output_dir is not None else prepared.output_dir
        threshold = config.eval.threshold

        matrix: list[dict[str, Any]] = []
        # Internal test (per source + combined) and validation (combined).
        combined_test = self._row_for_pool("test", "test", prepared.test, evaluator, threshold)
        matrix.append(combined_test)
        if prepared.validation:
            matrix.append(
                self._row_for_pool(
                    "validation", "validation", prepared.validation, evaluator, threshold
                )
            )
        test_by_source = self._group_by_source(prepared.test)
        for source, records in test_by_source.items():
            matrix.append(
                self._row_for_pool(f"test:{source}", "test", records, evaluator, threshold)
            )

        external_by_source = self._group_by_source(prepared.external_eval)
        for source, records in external_by_source.items():
            matrix.append(
                self._row_for_pool(source, "external_eval", records, evaluator, threshold)
            )

        configured_external = set(config.datasets.external_eval)
        covered_external = {row["dataset"] for row in matrix if row["pool"] == "external_eval"}
        for dataset_id in sorted(configured_external):
            if dataset_id not in covered_external:
                matrix.append(
                    {
                        "dataset": dataset_id,
                        "pool": "external_eval",
                        "samples": 0,
                        "benign": 0,
                        "malicious": 0,
                        "detection_rate": None,
                        "benign_rejection_rate": None,
                        "fpr": None,
                        "fnr": None,
                        "f1": None,
                        "accuracy": None,
                        "roc_auc": None,
                        "pr_auc": None,
                        "available": False,
                        "note": "not downloaded or no valid samples",
                    }
                )

        per_category = self._per_category(prepared, evaluator, threshold)
        threshold_analysis = self._threshold_analysis(prepared.test, evaluator, config)

        summary = self._summary(matrix, threshold_analysis)
        report = EvaluationReport(
            config=config,
            matrix=matrix,
            per_category=per_category,
            threshold_analysis=threshold_analysis,
            summary=summary,
        )
        write_json(run_dir / "evaluation.json", report.as_dict())
        (run_dir / "evaluation.md").write_text(report.to_markdown(), encoding="utf-8")
        logger.info("evaluation_completed", datasets=len(matrix), summary=summary)
        return report

    # ── internals ─────────────────────────────────────────────────────

    @staticmethod
    def _load_evaluator(checkpoint_dir: str | Path | None) -> HybridEvaluator:
        if checkpoint_dir is None:
            msg = "no fitted evaluator provided and no checkpoint_dir given"
            raise RuntimeError(msg)
        return HybridEvaluator.load_state(checkpoint_dir)

    @staticmethod
    def _group_by_source(
        records: list[DatasetRecord],
    ) -> dict[str, list[DatasetRecord]]:
        grouped: dict[str, list[DatasetRecord]] = {}
        for record in records:
            grouped.setdefault(record.source, []).append(record)
        return grouped

    def _row_for_pool(
        self,
        name: str,
        pool: str,
        records: list[DatasetRecord],
        evaluator: HybridEvaluator,
        threshold: float,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {
            "dataset": name,
            "pool": pool,
            "samples": len(records),
            "benign": sum(1 for r in records if r.label == 0),
            "malicious": sum(1 for r in records if r.label == 1),
            "available": True,
            "note": "",
        }
        if not records:
            base.update(
                {
                    "detection_rate": None,
                    "benign_rejection_rate": None,
                    "fpr": None,
                    "fnr": None,
                    "f1": None,
                    "accuracy": None,
                    "roc_auc": None,
                    "pr_auc": None,
                    "note": "no valid samples",
                }
            )
            return base
        labels = [r.label for r in records]
        scores = evaluator.score_texts([r.text for r in records])
        metrics = detection_metrics(labels, scores, threshold=threshold)
        base.update(_extract_row_metrics(metrics))
        return base

    def _per_category(
        self,
        prepared: PreparedDatasets,
        evaluator: HybridEvaluator,
        threshold: float,
    ) -> list[dict[str, Any]]:
        records = prepared.test + prepared.external_eval
        grouped: dict[str, list[DatasetRecord]] = {}
        for record in records:
            grouped.setdefault(record.category, []).append(record)

        rows: list[dict[str, Any]] = []
        for category in sorted(grouped):
            category_records = grouped[category]
            labels = [r.label for r in category_records]
            scores = evaluator.score_texts([r.text for r in category_records])
            metrics = detection_metrics(labels, scores, threshold=threshold)
            rows.append(
                {
                    "category": category,
                    "samples": len(category_records),
                    "benign": sum(1 for label in labels if label == 0),
                    "malicious": sum(1 for label in labels if label == 1),
                    "detection_rate": _or_none(metrics["recall"], metrics["positives"] > 0),
                    "benign_rejection_rate": _or_none(
                        metrics["specificity"], metrics["negatives"] > 0
                    ),
                    "fpr": _or_none(metrics["false_positive_rate"], metrics["negatives"] > 0),
                    "f1": _or_none(metrics["f1_score"], metrics["support"] > 0),
                }
            )
        return rows

    def _threshold_analysis(
        self,
        test_records: list[DatasetRecord],
        evaluator: HybridEvaluator,
        config: TrainingPipelineConfig,
    ) -> list[dict[str, Any]]:
        if not test_records:
            return []
        labels = [r.label for r in test_records]
        scores = evaluator.score_texts([r.text for r in test_records])
        rows: list[dict[str, Any]] = []
        for threshold in config.eval.threshold_sweep:
            metrics = detection_metrics(labels, scores, threshold=threshold)
            rows.append(
                {
                    "threshold": threshold,
                    "precision": _or_none(metrics["precision"], metrics["support"] > 0),
                    "recall": _or_none(metrics["recall"], metrics["support"] > 0),
                    "f1": _or_none(metrics["f1_score"], metrics["support"] > 0),
                    "fpr": _or_none(metrics["false_positive_rate"], metrics["negatives"] > 0),
                }
            )
        return rows

    @staticmethod
    def _summary(
        matrix: list[dict[str, Any]],
        threshold_analysis: list[dict[str, Any]],
    ) -> dict[str, Any]:
        evaluated = [row for row in matrix if row["available"] and row["samples"] > 0]
        external = [row for row in evaluated if row["pool"] == "external_eval"]
        test_row = next((row for row in matrix if row["dataset"] == "test"), {})

        def _mean(values: list[float]) -> float | None:
            if not values:
                return None
            return round(sum(values) / len(values), 4)

        detection = [
            float(row["detection_rate"]) for row in external if row["detection_rate"] is not None
        ]
        rejection = [
            float(row["benign_rejection_rate"])
            for row in external
            if row["benign_rejection_rate"] is not None
        ]
        f1 = [float(row["f1"]) for row in external if row["f1"] is not None]

        best = None
        if threshold_analysis:
            best = max(threshold_analysis, key=lambda r: r["f1"] or 0.0)

        summary: dict[str, Any] = {
            "datasets_evaluated": len(evaluated),
            "external_datasets_evaluated": len(external),
            "total_samples_evaluated": sum(int(row["samples"]) for row in evaluated),
            "mean_external_detection_rate": _mean(detection),
            "mean_external_benign_rejection_rate": _mean(rejection),
            "mean_external_f1": _mean(f1),
            "internal_test_detection_rate": test_row.get("detection_rate"),
            "internal_test_benign_rejection_rate": test_row.get("benign_rejection_rate"),
            "internal_test_f1": test_row.get("f1"),
        }
        if best is not None:
            summary["best_threshold"] = best["threshold"]
            summary["best_threshold_f1"] = best["f1"]
            summary["best_threshold_precision"] = best["precision"]
            summary["best_threshold_recall"] = best["recall"]
        return summary


def _extract_row_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "detection_rate": _or_none(metrics["recall"], metrics["positives"] > 0),
        "benign_rejection_rate": _or_none(metrics["specificity"], metrics["negatives"] > 0),
        "fpr": _or_none(metrics["false_positive_rate"], metrics["negatives"] > 0),
        "fnr": _or_none(metrics["false_negative_rate"], metrics["positives"] > 0),
        "f1": _or_none(metrics["f1_score"], metrics["support"] > 0),
        "accuracy": _or_none(metrics["accuracy"], metrics["support"] > 0),
        "roc_auc": metrics["roc_auc"],
        "pr_auc": metrics["pr_auc"],
    }


def _or_none(value: float, usable: bool) -> float | None:
    return round(float(value), 6) if usable else None


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "-"
    if value <= 1.0:
        return f"{value:.4f}"
    return f"{value:.4f}"
