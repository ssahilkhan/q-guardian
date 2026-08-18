"""Threshold analysis experiment (root-cause research, Phase 2).

Protocol (dataset policy enforced):
- Thresholds are swept and SELECTED on the validation split only.
- The selected threshold is then applied ONCE to the frozen internal-test
  and external (JBB) scores. JBB never participates in selection.

The evaluator checkpoint is frozen (baseline). Only the decision threshold
changes, so all pools are scored once (cached in ``experiments/_common``) and
reused across thresholds.

Usage:
    python experiments/threshold_analysis.py
"""

from __future__ import annotations

import json

from _common import ROOT, load_pools, score_pools, silence_logging

from q_guardian.evaluation.metrics import detection_metrics

OUTPUT = ROOT / "artifacts/experiments/threshold_analysis"
THRESHOLDS = [round(i / 10, 1) for i in range(1, 10)]


def main() -> None:
    silence_logging()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    pools = load_pools()
    scored = score_pools()
    scores = {name: [row["score"] for row in rows] for name, rows in scored.items()}

    # 1) Sweep on validation only.
    sweep: list[dict[str, float]] = []
    for threshold in THRESHOLDS:
        m = detection_metrics(pools["validation"].labels(), scores["validation"], threshold)
        sweep.append(
            {
                "threshold": threshold,
                "precision": m["precision"],
                "recall": m["recall"],
                "f1": m["f1_score"],
                "fpr": m["false_positive_rate"],
                "youden": m["true_positive_rate"] - m["false_positive_rate"],
                "mcc": m["matthews_corrcoef"],
            }
        )

    # 2) Select best by validation F1 (tie-break: higher Youden). Compare
    #    rounded F1 so float noise cannot hijack the tie-break.
    best = max(sweep, key=lambda row: (round(row["f1"], 6), row["youden"]))
    selected = best["threshold"]

    # 3) Apply the frozen selection ONCE to test and JBB.
    frozen: dict[str, dict[str, float]] = {}
    for name in ("test", "external_jbb"):
        m = detection_metrics(pools[name].labels(), scores[name], selected)
        frozen[name] = {
            "threshold": selected,
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1_score"],
            "fpr": m["false_positive_rate"],
            "fnr": m["false_negative_rate"],
            "mcc": m["matthews_corrcoef"],
            "roc_auc": m["roc_auc"],
            "tp": m["true_positives"],
            "fp": m["false_positives"],
            "fn": m["false_negatives"],
            "tn": m["true_negatives"],
        }

    report = {
        "method": "validation-only threshold sweep; selection by validation F1 (tie-break Youden, rounded to 6dp); JBB excluded from selection",
        "selected_threshold": selected,
        "validation_sweep": sweep,
        "frozen_evaluation": frozen,
        "sanity_check_validation_at_selected": next(
            r for r in sweep if r["threshold"] == selected
        ),
        "baseline_threshold_0_5_frozen": {
            name: detection_metrics(pools[name].labels(), scores[name], 0.5)["f1_score"]
            for name in ("validation", "test", "external_jbb")
        },
        "jbb_score_distribution": jbb_distribution(scored["external_jbb"]),
        "jbb_detection_at_each_threshold": jbb_detection_at_each_threshold(
            scored["external_jbb"]
        ),
    }

    (OUTPUT / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUTPUT / "threshold_report.md").write_text(render(report), encoding="utf-8")
    print(f"selected threshold: {selected}")
    print(f"validation F1 at selected: {best['f1']:.4f}")
    print("frozen test:", {k: round(v, 4) for k, v in frozen["test"].items()})
    print("frozen jbb:", {k: round(v, 4) for k, v in frozen["external_jbb"].items()})


def jbb_distribution(rows: list[dict]) -> dict[str, float]:
    """Score distribution of JBB malicious/benign pools."""
    def _percentiles(scores: list[float]) -> list[float]:
        s = sorted(scores)
        out = []
        for p in (0, 10, 25, 50, 75, 90, 100):
            idx = min(len(s) - 1, max(0, int(len(s) * p / 100)))
            out.append(round(s[idx], 4))
        return out

    mal = [r["score"] for r in rows if r["label"] == 1]
    ben = [r["score"] for r in rows if r["label"] == 0]
    return {
        "malicious": {"n": len(mal), "min": round(min(mal), 4), "percentiles": _percentiles(mal), "max": round(max(mal), 4)},
        "benign": {"n": len(ben), "min": round(min(ben), 4), "percentiles": _percentiles(ben), "max": round(max(ben), 4)},
    }


def jbb_detection_at_each_threshold(rows: list[dict]) -> list[dict[str, float]]:
    """Detection rate (recall on JBB malicious) at each candidate threshold."""
    mal = [r["score"] for r in rows if r["label"] == 1]
    result = []
    for threshold in THRESHOLDS:
        detected = sum(1 for s in mal if s >= threshold)
        result.append({"threshold": threshold, "detection_rate": detected / len(mal)})
    return result


def render(report: dict) -> str:
    lines = [
        "# Threshold Analysis (validation-only selection)",
        "",
        "Selection rule: sweep 0.10-0.90 on **validation only**, pick max F1 "
        "(tie-break Youden, rounded to 6dp). The chosen threshold is applied "
        "once to frozen internal-test and external JBB scores. JBB never "
        "informs selection.",
        "",
        "## Validation sweep",
        "",
        "| Threshold | Precision | Recall | F1 | FPR | Youden | MCC |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["validation_sweep"]:
        lines.append(
            f"| {row['threshold']} | {row['precision']:.4f} | {row['recall']:.4f} "
            f"| {row['f1']:.4f} | {row['fpr']:.4f} | {row['youden']:.4f} "
            f"| {row['mcc']:.4f} |"
        )
    lines.append("")
    lines.append(f"**Selected threshold: {report['selected_threshold']}**")
    lines.append("")
    lines.append("## Frozen evaluation at selected threshold")
    lines.append("")
    lines.append(
        "| Pool | Precision | Recall | F1 | FPR | FNR | MCC | ROC-AUC | "
        "TP | FP | FN | TN |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, row in report["frozen_evaluation"].items():
        lines.append(
            f"| {name} | {row['precision']:.4f} | {row['recall']:.4f} | "
            f"{row['f1']:.4f} | {row['fpr']:.4f} | {row['fnr']:.4f} | "
            f"{row['mcc']:.4f} | {row['roc_auc']:.4f} | {row['tp']} | "
            f"{row['fp']} | {row['fn']} | {row['tn']} |"
        )
    lines.append("")
    lines.append("## Comparison with baseline threshold 0.5")
    lines.append("")
    lines.append("| Pool | F1 at 0.5 (baseline) |")
    lines.append("| --- | --- |")
    for name, f1 in report["baseline_threshold_0_5_frozen"].items():
        lines.append(f"| {name} | {f1:.4f} |")
    lines.append("")
    lines.append("## JBB malicious score distribution")
    lines.append("")
    dist = report["jbb_score_distribution"]
    for key in ("malicious", "benign"):
        d = dist[key]
        lines.append(
            f"- **{key}** (n={d['n']}): min {d['min']}, "
            f"percentiles {d['percentiles']}, max {d['max']}"
        )
    lines.append("")
    lines.append("## JBB detection rate if we had tuned on JBB (for diagnosis only)")
    lines.append("")
    lines.append("| Threshold | Detection rate |")
    lines.append("| --- | --- |")
    for row in report["jbb_detection_at_each_threshold"]:
        lines.append(f"| {row['threshold']} | {row['detection_rate']:.4f} |")
    lines.append("")
    lines.append(
        "> Note: the last table is diagnostic only — JBB must never be used to "
        "select a threshold. It shows whether ANY threshold would rescue JBB."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
