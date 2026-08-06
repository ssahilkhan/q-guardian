"""Cross-validation and ablation benchmarking for the detection pipeline.

Runs K-fold cross-validation of the hybrid pipeline, aggregates detection
metrics per provider and for the fused result, and (optionally) measures
the impact of removing each provider (ablation). This is the measurement
harness behind every accuracy-related claim in the project.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Any

from q_guardian.evaluation.pipeline import (
    ALL_PROVIDERS,
    HybridEvaluator,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from q_guardian.evaluation.dataset import PromptBenchmarkDataset

_METRIC_KEYS = [
    "accuracy",
    "precision",
    "recall",
    "f1_score",
    "roc_auc",
    "pr_auc",
    "expected_calibration_error",
    "brier_score",
    "matthews_corrcoef",
]

_FUSION_ONLY = ["fusion"]


def _aggregate(fold_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-fold metric dicts into mean/std summaries."""
    aggregated: dict[str, Any] = {}
    for provider in _FUSION_ONLY + ALL_PROVIDERS:
        if provider not in fold_results[0]:
            continue
        metrics = fold_results[0][provider]
        entry: dict[str, Any] = {}
        for key in _METRIC_KEYS:
            if key not in metrics:
                continue
            values = [r[provider][key] for r in fold_results]
            entry[key] = {
                "mean": round(statistics.fmean(values), 6),
                "std": round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
                "min": round(min(values), 6),
                "max": round(max(values), 6),
            }
        entry["support"] = sum(r[provider].get("support", 0) for r in fold_results)
        aggregated[provider] = entry
    return aggregated


class DetectionBenchmark:
    """Runs K-fold CV and ablation for a hybrid pipeline configuration.

    Args:
        evaluator_kwargs: Keyword arguments forwarded to ``HybridEvaluator``
            for every fold (e.g. ``quantum=True``, ``quantum_shots=128``).
    """

    def __init__(self, evaluator_kwargs: dict[str, Any] | None = None) -> None:
        self.evaluator_kwargs = dict(evaluator_kwargs or {})

    def run(
        self,
        dataset: PromptBenchmarkDataset,
        k: int = 5,
        seed: int = 42,
        threshold: float = 0.5,
        ablate: bool = True,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Run K-fold cross-validation and optional ablation.

        Args:
            dataset: Labeled dataset to evaluate on.
            k: Number of folds.
            seed: Random seed for fold generation.
            threshold: Decision threshold for binary metrics.
            ablate: Whether to also run provider ablation.
            progress: Optional callback for progress messages.

        Returns:
            Nested dict with config, dataset stats, cross-validation
            aggregates and optional ablation results.
        """
        folds = dataset.kfold(k=k, seed=seed)
        report: dict[str, Any] = {
            "config": {
                "k": k,
                "seed": seed,
                "threshold": threshold,
                "evaluator": {
                    "quantum": self.evaluator_kwargs.get("quantum", True),
                    "quantum_shots": self.evaluator_kwargs.get("quantum_shots", 128),
                    "quantum_feature_count": self.evaluator_kwargs.get("quantum_feature_count", 5),
                    "n_estimators": self.evaluator_kwargs.get("n_estimators", 50),
                    "contamination": self.evaluator_kwargs.get("contamination", 0.2),
                },
            },
            "dataset": dataset.describe(),
            "cross_validation": {
                "fold_count": len(folds),
                "folds": [],
            },
        }

        fold_results: list[dict[str, Any]] = []
        sample_scores: list[dict[str, Any]] = []
        for fold_idx, (train, test) in enumerate(folds):
            if progress:
                progress(f"fold {fold_idx + 1}/{len(folds)} (train={len(train)}, test={len(test)})")
            evaluator = HybridEvaluator(**self.evaluator_kwargs)
            evaluator.fit(train.texts(), train.labels())
            fold_result = evaluator.evaluate(test, threshold=threshold, include_providers=None)
            fold_results.append(
                {
                    provider: fold_result[provider]
                    for provider in ["fusion", *evaluator.provider_ids()]
                }
            )
            sample_scores.extend(fold_result["scores"])
            report["cross_validation"]["folds"].append(
                {
                    "fold": fold_idx + 1,
                    "train_size": len(train),
                    "test_size": len(test),
                    "fusion_roc_auc": round(fold_result["fusion"]["roc_auc"], 6),
                    "fusion_f1": round(fold_result["fusion"]["f1_score"], 6),
                    "fusion_accuracy": round(fold_result["fusion"]["accuracy"], 6),
                }
            )

        report["cross_validation"]["metrics"] = _aggregate(fold_results)

        # Out-of-fold per-sample scores: every sample appears in exactly one
        # test fold, so this is a complete OOF prediction table.
        report["scores"] = sample_scores

        # Determine the strongest provider by mean ROC-AUC.
        auc_table = report["cross_validation"]["metrics"]
        ranking = sorted(
            ((pid, m["roc_auc"]["mean"]) for pid, m in auc_table.items()),
            key=lambda x: x[1],
            reverse=True,
        )
        report["cross_validation"]["roc_auc_ranking"] = [
            {"provider": pid, "mean_roc_auc": round(auc, 6)} for pid, auc in ranking
        ]

        if ablate:
            fusion_mean = report["cross_validation"]["metrics"]["fusion"]
            full_auc = fusion_mean["roc_auc"]["mean"]
            full_f1 = fusion_mean["f1_score"]["mean"]
            report["ablation"] = self._ablate(
                dataset, k=k, seed=seed, threshold=threshold, progress=progress
            )
            report["ablation_summary"] = self._ablation_summary(
                report["ablation"], full_auc=full_auc, full_f1=full_f1
            )

        return report

    def _ablate(
        self,
        dataset: PromptBenchmarkDataset,
        k: int,
        seed: int,
        threshold: float,
        progress: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        """For each provider, run CV with that provider removed from fusion."""
        ablation: dict[str, Any] = {}
        for removed in ALL_PROVIDERS:
            kept = [p for p in ALL_PROVIDERS if p != removed]
            fold_auc: list[float] = []
            fold_f1: list[float] = []
            for _fold_idx, (train, test) in enumerate(dataset.kfold(k=k, seed=seed)):
                evaluator = HybridEvaluator(**self.evaluator_kwargs)
                evaluator.fit(train.texts(), train.labels())
                result = evaluator.evaluate(
                    test,
                    threshold=threshold,
                    include_providers=set(kept),
                )
                fold_auc.append(result["fusion"]["roc_auc"])
                fold_f1.append(result["fusion"]["f1_score"])
            if progress:
                progress(f"ablation: removed {removed}")
            ablation[removed] = {
                "removed": removed,
                "kept": kept,
                "fusion_roc_auc": {
                    "mean": round(statistics.fmean(fold_auc), 6),
                    "std": round(statistics.stdev(fold_auc), 6) if len(fold_auc) > 1 else 0.0,
                },
                "fusion_f1_mean": round(statistics.fmean(fold_f1), 6),
            }
        return ablation

    def _ablation_summary(
        self,
        ablation: dict[str, Any],
        full_auc: float,
        full_f1: float,
    ) -> dict[str, Any]:
        """Summarize ablation results and derive recommendations.

        Deltas are ``full - without``, so a positive delta means removing
        the provider hurts the metric; a negative delta means the provider
        is (on that metric) redundant or slightly harmful. Both ROC-AUC and
        F1 are considered because ranking power alone can mask large F1
        drops.
        """
        summary: dict[str, Any] = {
            "full_fusion_roc_auc": round(full_auc, 6),
            "full_fusion_f1": round(full_f1, 6),
            "providers": {},
            "most_valuable_provider": None,
            "most_valuable_delta": 0.0,
            "redundant_providers": [],
            "recommendation": "",
        }
        deltas: dict[str, float] = {}
        redundant: list[str] = []
        for pid, entry in ablation.items():
            auc_without = entry["fusion_roc_auc"]["mean"]
            f1_without = entry["fusion_f1_mean"]
            auc_delta = round(full_auc - auc_without, 6)
            f1_delta = round(full_f1 - f1_without, 6)
            deltas[pid] = auc_delta + f1_delta
            summary["providers"][pid] = {
                "roc_auc_without": auc_without,
                "roc_auc_delta": auc_delta,
                "f1_without": f1_without,
                "f1_delta": f1_delta,
                "impact": "negative" if auc_delta > 0 or f1_delta > 0 else "positive",
            }
            if auc_delta <= 0.0 and f1_delta <= 0.0:
                redundant.append(pid)
        if deltas:
            summary["most_valuable_provider"] = max(deltas, key=lambda p: deltas[p])
            summary["most_valuable_delta"] = deltas[summary["most_valuable_provider"]]
        summary["redundant_providers"] = redundant
        summary["recommendation"] = self._recommendation(summary)
        return summary

    def _recommendation(self, summary: dict[str, Any]) -> str:
        provider = summary["most_valuable_provider"]
        redundant = summary.get("redundant_providers", [])
        parts: list[str] = []
        if provider is not None:
            parts.append(
                f"Removing {provider} hurts the fused result most "
                f"(composite delta {summary['most_valuable_delta']:.4f}); the fusion "
                f"relies most on {provider}."
            )
        if redundant:
            parts.append(
                "Removing "
                + ", ".join(sorted(redundant))
                + " neither lowers ROC-AUC nor F1; these providers are "
                "candidates for weight reduction or removal."
            )
        if not parts:
            parts.append("No provider is clearly redundant; keep the full ensemble.")
        return " ".join(parts)
