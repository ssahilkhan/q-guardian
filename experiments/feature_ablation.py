"""Feature ablation experiment (root-cause research, Phase 4).

Retrains the baseline HybridEvaluator on the SAME 2425 training rows (train.jsonl
in file order, reproducing the baseline) but restricts the 43-feature vector to
logical groups, to see which feature family carries the in-domain signal and
whether any family helps the frozen JBB pool.

Feature groups (indices from MLFeatureProvider.feature_names):
- statistical        : 0-8   (length, word_count, ..., special_char_count, suspicious_keyword_count)
- keyword_flags      : 9-32  (24 keyword occurrence counts)
- pattern            : 33-38 (code blocks, urls, markdown, unicode escapes, html, repeats)
- character          : 39-42 (unique_char_ratio, avg_word_length, punctuation, whitespace)

Strategies (all = baseline re-run):
- all, no_keywords, keywords_only, no_statistical, statistical_only,
  no_pattern, no_character

JBB is measured only; no strategy is selected using JBB.

Usage:
    python experiments/feature_ablation.py
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from _common import ROOT, SPLITS, load_pools, silence_logging
from ablation_base import AblationEvaluator

from q_guardian.ml.feature_pipeline import MLFeatureProvider

if TYPE_CHECKING:
    from pathlib import Path

OUTPUT = ROOT / "artifacts/experiments/feature_ablation"
THRESHOLD = 0.5


def main() -> None:
    silence_logging()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    names = MLFeatureProvider().feature_names
    assert len(names) == 43, f"expected 43 features, got {len(names)}"
    statistical = list(range(0, 9))  # includes suspicious_keyword_count at index 8
    keywords = list(range(9, 33))
    pattern = list(range(33, 39))
    character = list(range(39, 43))
    all_idx = list(range(43))

    strategies = {
        "all": None,
        "no_keywords": [i for i in all_idx if i not in keywords],
        "keywords_only": keywords,
        "no_statistical": [i for i in all_idx if i not in statistical],
        "statistical_only": statistical,
        "no_pattern": [i for i in all_idx if i not in pattern],
        "no_character": [i for i in all_idx if i not in character],
    }

    train = _load(SPLITS / "train.jsonl")
    texts = [r["text"] for r in train]
    labels = [r["label"] for r in train]
    pools = load_pools()

    report: dict = {"threshold": THRESHOLD, "strategies": {}}
    for name, feature_indices in strategies.items():
        evalr = AblationEvaluator(
            quantum=False,
            n_estimators=50,
            contamination=0.2,
            random_state=42,
            feature_indices=feature_indices,
        )
        evalr.fit(texts, labels)
        pool_metrics = {}
        for pool_name, ds in pools.items():
            result = evalr.evaluate(ds, threshold=THRESHOLD)
            pool_metrics[pool_name] = _metrics(result["fusion"])
        report["strategies"][name] = {
            "n_features": len(feature_indices) if feature_indices else 43,
            "pools": pool_metrics,
        }
        print(f"{name}: val {pool_metrics['validation']['f1']:.3f} / "
              f"test {pool_metrics['test']['f1']:.3f} / "
              f"jbb {pool_metrics['external_jbb']['f1']:.3f}")

    (OUTPUT / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUTPUT / "feature_ablation_report.md").write_text(render(report), encoding="utf-8")
    print("done")


def _load(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


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
        "# Feature Ablation (frozen JBB measurement only)",
        "",
        "Same 2425 training rows (file order = baseline), same model family; "
        "only the 43-feature vector is restricted per strategy.",
        "",
        "| Strategy | Features | val F1 | test F1 | JBB F1 | JBB AUC | JBB recall |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, s in report["strategies"].items():
        v, t, j = s["pools"]["validation"], s["pools"]["test"], s["pools"]["external_jbb"]
        lines.append(
            f"| {name} | {s['n_features']} | {v['f1']:.4f} | {t['f1']:.4f} "
            f"| {j['f1']:.4f} | {j['roc_auc']:.4f} | {j['recall']:.4f} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
