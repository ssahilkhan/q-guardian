"""Model ablation experiment (root-cause research, Phase 5).

Compares rule-engine / isolation-forest / random-forest / fusion on
validation, held-out test, and frozen external JBB using the baseline
checkpoint. No retraining; per-sample provider scores are cached by
``experiments/_common``.

Ablations:
- single-provider metrics (own scores, threshold 0.5)
- fused with each provider excluded (remaining providers re-weight)
- fused with single provider only (weight normalized to 1)

Usage:
    python experiments/model_ablation.py
"""

from __future__ import annotations

import json

from _common import ROOT, provider_scores, score_provider_pools, silence_logging

from q_guardian.evaluation.metrics import detection_metrics

OUTPUT = ROOT / "artifacts/experiments/model_ablation"
PROVIDER_IDS = ("rule-engine", "isolation-forest", "random-forest", "fusion")
POOLS = ("validation", "test", "external_jbb")


def main() -> None:
    silence_logging()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    score_provider_pools()  # ensure cache

    labels = {
        pool: [r["label"] for r in score_provider_pools()[pool]] for pool in POOLS
    }

    report: dict = {"per_provider_at_threshold_0_5": {}, "leave_one_out_fusion": {}}

    # Per-provider metrics.
    for pool in POOLS:
        rule, if_, rf, fusion = provider_scores(pool)
        report["per_provider_at_threshold_0_5"][pool] = {
            "rule-engine": metrics(labels[pool], rule),
            "isolation-forest": metrics(labels[pool], if_),
            "random-forest": metrics(labels[pool], rf),
            "fusion": metrics(labels[pool], fusion),
        }

    # Leave-one-out fusion: fused score when each provider is dropped.
    for pool in POOLS:
        rule, if_, rf, fusion = provider_scores(pool)
        report["leave_one_out_fusion"][pool] = {
            "all": metrics(labels[pool], fusion),
            "without_rule": metrics(
                labels[pool],
                [(0.15 * a + 0.55 * c) / (0.15 + 0.55) for a, c in zip(if_, rf)],
            ),
            "without_if": metrics(
                labels[pool],
                [(0.15 * a + 0.55 * c) / (0.15 + 0.55) for a, c in zip(rule, rf)],
            ),
            "without_rf": metrics(
                labels[pool],
                [(0.15 * a + 0.15 * b) / 0.3 for a, b in zip(rule, if_)],
            ),
        }

    # RF-only dominance check: correlation between RF score and fusion score.
    report["rf_fusion_correlation"] = {
        pool: pearson(provider_scores(pool)[2], provider_scores(pool)[3])
        for pool in POOLS
    }

    (OUTPUT / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUTPUT / "model_ablation_report.md").write_text(render(report), encoding="utf-8")
    print("done")


def metrics(labels: list[int], scores: list[float]) -> dict[str, float]:
    m = detection_metrics(labels, scores, threshold=0.5)
    return {
        "precision": m["precision"],
        "recall": m["recall"],
        "f1": m["f1_score"],
        "fpr": m["false_positive_rate"],
        "mcc": m["matthews_corrcoef"],
        "roc_auc": m["roc_auc"],
    }


def pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    va = sum((x - ma) ** 2 for x in a) ** 0.5
    vb = sum((y - mb) ** 2 for y in b) ** 0.5
    if va == 0 or vb == 0:
        return 0.0
    return round(cov / (va * vb), 4)


def render(report: dict) -> str:
    lines = [
        "# Model Ablation (frozen baseline, threshold 0.5)",
        "",
        "Per-provider scores come from the same frozen checkpoint; only the "
        "metric computation differs per provider. JBB is never trained on or "
        "used for any selection here.",
        "",
        "## Per-provider F1 / ROC-AUC at threshold 0.5",
        "",
        "| Pool | Model | F1 | Precision | Recall | FPR | MCC | ROC-AUC |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for pool in POOLS:
        for model, m in report["per_provider_at_threshold_0_5"][pool].items():
            lines.append(
                f"| {pool} | {model} | {m['f1']:.4f} | {m['precision']:.4f} "
                f"| {m['recall']:.4f} | {m['fpr']:.4f} | {m['mcc']:.4f} "
                f"| {m['roc_auc']:.4f} |"
            )
    lines.append("")
    lines.append("## Leave-one-out fusion (weights renormalized)")
    lines.append("")
    lines.append(
        "| Pool | Fusion | Without rule | Without IF | Without RF |",
    )
    lines.append("| --- | --- | --- | --- | --- |")
    for pool in POOLS:
        row = report["leave_one_out_fusion"][pool]
        lines.append(
            f"| {pool} | {row['all']['f1']:.4f} | "
            f"{row['without_rule']['f1']:.4f} | "
            f"{row['without_if']['f1']:.4f} | "
            f"{row['without_rf']['f1']:.4f} |"
        )
    lines.append("")
    lines.append("## RF vs fusion score correlation")
    lines.append("")
    lines.append("| Pool | Pearson r |")
    lines.append("| --- | --- |")
    for pool, r in report["rf_fusion_correlation"].items():
        lines.append(f"| {pool} | {r} |")
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
