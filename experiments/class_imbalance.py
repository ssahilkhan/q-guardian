"""Class-imbalance ablation experiment (root-cause research, Phase 3).

Trains the same HybridEvaluator pipeline on differently balanced training
sets and compares validation / held-out test / frozen external JBB metrics.
No JBB data participates in any decision made here — every strategy is
selected only by which imbalance hypothesis is being tested.

Strategies:
- full: the baseline training pool (436 positive deepset + 1989 dolly benign)
- class_weight_balanced: RF with ``class_weight="balanced"``
- undersample_1_1 / _1_2 / _1_5: dolly benign randomly undersampled (seed 42)
  to positive:negative ratios of 1:1, 1:2, 1:5 (diversity preserved by
  random selection, no oversampling of identical positives)

Usage:
    python experiments/class_imbalance.py
"""

from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

from _common import ROOT, SPLITS, load_pools, silence_logging
from ablation_base import AblationEvaluator

if TYPE_CHECKING:
    from pathlib import Path

OUTPUT = ROOT / "artifacts/experiments/class_imbalance"
THRESHOLD = 0.5


def main() -> None:
    silence_logging()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    train = _load(SPLITS / "train.jsonl")
    pos_idx = [i for i, r in enumerate(train) if r["label"] == 1]
    neg_idx = [i for i, r in enumerate(train) if r["label"] == 0]
    pools = load_pools()

    # IMPORTANT: row order changes RandomForest/IsolationForest results in this
    # environment (verified empirically). Production trains on train.jsonl in
    # file order, which reproduces the baseline checkpoint exactly. All
    # strategies below therefore keep positive rows in place and only REMOVE a
    # subset of negatives (preserving file order), never reorder the pool.
    rng = random.Random(42)
    strategies = {
        "full": (list(range(len(train))), None),
        "class_weight_balanced": (list(range(len(train))), "balanced"),
        "undersample_1_1": (pos_idx + _sample(neg_idx, len(pos_idx), rng), None),
        "undersample_1_2": (pos_idx + _sample(neg_idx, 2 * len(pos_idx), rng), None),
        "undersample_1_5": (pos_idx + _sample(neg_idx, 5 * len(pos_idx), rng), None),
    }

    report: dict = {"threshold": THRESHOLD, "strategies": {}}
    for name, (selected, class_weight) in strategies.items():
        # Sort selected indices so positives and retained negatives keep their
        # original relative (file) order: positives first? No — preserve the
        # original order of ALL kept rows to stay closest to production.
        rows = [train[i] for i in sorted(selected)]
        texts = [r["text"] for r in rows]
        labels = [r["label"] for r in rows]
        evalr = AblationEvaluator(
            quantum=False,
            n_estimators=50,
            contamination=0.2,
            random_state=42,
            rf_class_weight=class_weight,
        )
        evalr.fit(texts, labels)
        pool_metrics = {}
        for pool_name, ds in pools.items():
            result = evalr.evaluate(ds, threshold=THRESHOLD)
            pool_metrics[pool_name] = _metrics(result["fusion"])
        n_pos = sum(labels)
        n_neg = len(labels) - n_pos
        report["strategies"][name] = {
            "train_samples": len(labels),
            "positive": n_pos,
            "negative": n_neg,
            "ratio": f"1:{round(n_neg / n_pos, 2)}" if n_pos else "n/a",
            "rf_class_weight": class_weight,
            "pools": pool_metrics,
        }
        print(
            f"{name}: {pool_metrics['validation']['f1']:.3f} / "
            f"{pool_metrics['test']['f1']:.3f} / "
            f"{pool_metrics['external_jbb']['f1']:.3f}"
        )

    (OUTPUT / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUTPUT / "class_imbalance_report.md").write_text(render(report), encoding="utf-8")
    print("done")


def _load(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _sample(items: list[int], n: int, rng: random.Random) -> list[int]:
    return rng.sample(items, n)


def _metrics(m: dict) -> dict[str, float]:
    return {
        "f1": m["f1_score"],
        "precision": m["precision"],
        "recall": m["recall"],
        "fpr": m["false_positive_rate"],
        "roc_auc": m["roc_auc"],
        "mcc": m["matthews_corrcoef"],
    }


def render(report: dict) -> str:
    lines = [
        "# Class-Imbalance Ablation",
        "",
        "Every strategy trains the identical HybridEvaluator pipeline "
        "(seed 42, n_estimators 50, contamination 0.2) on a differently "
        "balanced subset of the SAME training sources. JBB is measured only; "
        "no strategy is selected using JBB.",
        "",
        "| Strategy | Train | Ratio | val F1 | test F1 | JBB F1 | JBB AUC | JBB detect |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, s in report["strategies"].items():
        v, t, j = s["pools"]["validation"], s["pools"]["test"], s["pools"]["external_jbb"]
        lines.append(
            f"| {name} | {s['train_samples']} (p={s['positive']}, n={s['negative']}) "
            f"| {s['ratio']} | {v['f1']:.4f} | {t['f1']:.4f} | {j['f1']:.4f} "
            f"| {j['roc_auc']:.4f} | {j['recall']:.4f} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
