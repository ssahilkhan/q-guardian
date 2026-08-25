"""Controlled Random-Forest tuning for the arm_d diverse checkpoint.

Selection objective: internal validation split ROC-AUC ONLY.
JBB is scored exactly once for the selected configuration at the end and is
NEVER used for any selection decision (no leakage, no test-set tuning).

Grid (small, controlled):
    n_estimators     : {50, 200}
    max_depth        : {None, 20}
    min_samples_leaf : {1, 2}
    class_weight     : {None, "balanced_subsample"}

Usage:
    python experiments/training_diversity/09_tune_arm_d_rf.py
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import numpy as np
import structlog
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").CRITICAL)
)

from q_guardian.evaluation.metrics import detection_metrics

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "artifacts" / "experiments" / "training_diversity" / "cache"
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
OUT = ROOT / "artifacts" / "experiments" / "training_diversity"

SEED = 42


def load_cache(name: str) -> dict:
    d = np.load(CACHE / f"{name}.npz", allow_pickle=True)
    return {
        "texts": [str(t) for t in d["texts"].tolist()],
        "x43": d["x43"].astype(np.float64),
        "xemb": d["xemb"].astype(np.float64),
    }


def load_labels(path: Path) -> list[int]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return [int(r["label"]) for r in rows]


def main() -> None:
    t0 = time.monotonic()
    arm = load_cache("arm_d")
    val = load_cache("validation")
    jbb = load_cache("jbb")

    y_train = load_labels(ROOT / "experiments/training_diversity/train_sets/arm_d.jsonl")
    y_val = load_labels(SPLITS / "validation.jsonl")
    y_jbb = load_labels(SPLITS / "external_eval.jsonl")

    X_train = np.hstack([arm["x43"], arm["xemb"]])
    X_val = np.hstack([val["x43"], val["xemb"]])
    X_jbb = np.hstack([jbb["x43"], jbb["xemb"]])

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_jbb_s = scaler.transform(X_jbb)

    grid = list(
        itertools.product(
            (50, 200),  # n_estimators
            (None, 20),  # max_depth
            (1, 2),  # min_samples_leaf
            (None, "balanced_subsample"),  # class_weight
        )
    )

    results = []
    print(f"[tune] {len(grid)} configurations, selection = validation ROC-AUC")
    for n_est, depth, leaf, cw in grid:
        clf = RandomForestClassifier(
            n_estimators=n_est,
            max_depth=depth,
            min_samples_leaf=leaf,
            class_weight=cw,
            random_state=SEED,
            n_jobs=-1,
        )
        clf.fit(X_train_s, y_train)
        s_val = clf.predict_proba(X_val_s)[:, 1].tolist()
        m_val = detection_metrics(y_val, s_val, threshold=0.5)
        cfg = {
            "n_estimators": n_est,
            "max_depth": depth,
            "min_samples_leaf": leaf,
            "class_weight": cw,
            "random_state": SEED,
        }
        results.append(
            {
                "config": cfg,
                "validation_roc_auc": round(m_val["roc_auc"], 4),
                "validation_pr_auc": round(m_val["pr_auc"], 4),
                "validation_f1": round(m_val["f1_score"], 4),
            }
        )
        print(f"  {cfg} -> val auc={m_val['roc_auc']:.4f} f1={m_val['f1_score']:.4f}")

    best = max(results, key=lambda r: (r["validation_roc_auc"], r["validation_pr_auc"]))
    print(f"[tune] best by validation ROC-AUC: {best['config']}")

    # Final model: refit selected config deterministically, score JBB once.
    b = best["config"]
    final = RandomForestClassifier(
        n_estimators=b["n_estimators"],
        max_depth=b["max_depth"],
        min_samples_leaf=b["min_samples_leaf"],
        class_weight=b["class_weight"],
        random_state=b["random_state"],
        n_jobs=-1,
    )
    final.fit(X_train_s, y_train)
    m_val_f = detection_metrics(y_val, final.predict_proba(X_val_s)[:, 1].tolist(), threshold=0.5)
    m_jbb_f = detection_metrics(y_jbb, final.predict_proba(X_jbb_s)[:, 1].tolist(), threshold=0.5)

    baseline_val = detection_metrics(
        y_val,
        RandomForestClassifier(n_estimators=50, random_state=SEED)
        .fit(X_train_s, y_train)
        .predict_proba(X_val_s)[:, 1]
        .tolist(),
        threshold=0.5,
    )

    output = {
        "selection_objective": "validation ROC-AUC (JBB never used for selection)",
        "seed": SEED,
        "grid_results": sorted(results, key=lambda r: -r["validation_roc_auc"]),
        "selected_config": b,
        "final_metrics": {
            "validation": {
                "roc_auc": round(m_val_f["roc_auc"], 4),
                "pr_auc": round(m_val_f["pr_auc"], 4),
                "f1": round(m_val_f["f1_score"], 4),
            },
            "jbb_single_final_evaluation": {
                "roc_auc": round(m_jbb_f["roc_auc"], 4),
                "pr_auc": round(m_jbb_f["pr_auc"], 4),
                "accuracy": round(m_jbb_f["accuracy"], 4),
                "precision": round(m_jbb_f["precision"], 4),
                "recall": round(m_jbb_f["recall"], 4),
                "f1": round(m_jbb_f["f1_score"], 4),
                "confusion_matrix": {
                    "tp": m_jbb_f["true_positives"],
                    "fp": m_jbb_f["false_positives"],
                    "fn": m_jbb_f["false_negatives"],
                    "tn": m_jbb_f["true_negatives"],
                },
            },
        },
        "frozen_baseline_validation_roc_auc": round(baseline_val["roc_auc"], 4),
    }
    (OUT / "rf_tuning_results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(
        f"[final] validation auc={m_val_f['roc_auc']:.4f} | "
        f"JBB auc={m_jbb_f['roc_auc']:.4f} (single evaluation)"
    )
    print(f"[done] {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()
