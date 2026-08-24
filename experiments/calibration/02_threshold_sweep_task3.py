"""Person 1 — Task 3: threshold sweep on calibrated models.

Loads the frozen Task 2 arm_d checkpoint (``artifacts/training_arm_d/model``),
fits probability calibration on the validation split ONLY (out-of-fold for
honest validation metrics, then a full-validation refit applied to internal
test and JBB), sweeps the production decision threshold over calibrated
probabilities, and persists a calibrated checkpoint plus machine-readable
results.

Leakage controls
----------------
- Validation (110 samples): the ONLY pool whose labels touch calibration
  fitting or threshold selection. Selection uses out-of-fold calibrated
  probabilities (StratifiedKFold(5, shuffle=True, random_state=42)).
- Internal test / JBB: evaluation only; scored with the full-validation-refit
  calibrator. JBB labels are never used for any fitting or selection.
- Calibration method per model is selected by the lowest validation OOF Brier
  score (a proper scoring rule measured on validation alone).

Usage:
    python experiments/calibration/02_threshold_sweep_task3.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import structlog
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from q_guardian.evaluation.metrics import detection_metrics
from q_guardian.evaluation.pipeline import (
    CLASSIFIER_PROVIDER,
    XGBOOST_PROVIDER,
    HybridEvaluator,
    apply_probability_calibration,
)

ROOT = Path(__file__).resolve().parent.parent.parent
CHECKPOINT = ROOT / "artifacts" / "training_arm_d" / "model"
CALIBRATED_CHECKPOINT = ROOT / "artifacts" / "training_arm_d" / "model_calibrated"
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
OUT = ROOT / "artifacts" / "experiments" / "threshold_sweep"
OUT.mkdir(parents=True, exist_ok=True)

POOL_FILES = {
    "validation": SPLITS / "validation.jsonl",
    "test": SPLITS / "test.jsonl",
    "jbb": SPLITS / "external_eval.jsonl",
}
THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
PRODUCTION_THRESHOLD = 0.2
MODELS = {"xgboost": XGBOOST_PROVIDER, "random_forest": CLASSIFIER_PROVIDER}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def metrics_row(y_true: list[int], scores: list[float], t: float) -> dict:
    m = detection_metrics(y_true, scores, threshold=t)
    return {
        "threshold": t,
        "precision": round(m["precision"], 4),
        "recall": round(m["recall"], 4),
        "f1": round(m["f1_score"], 4),
        "accuracy": round(m["accuracy"], 4),
        "tp": int(m["true_positives"]),
        "tn": int(m["true_negatives"]),
        "fp": int(m["false_positives"]),
        "fn": int(m["false_negatives"]),
        "fpr": round(m["false_positive_rate"], 4),
        "fnr": round(m["false_negative_rate"], 4),
    }


def brier(y_true: list[int], scores: list[float]) -> float:
    p = np.asarray(scores, dtype=np.float64)
    y = np.asarray(y_true, dtype=np.float64)
    return float(np.mean((p - y) ** 2))


def oof_calibrate(scores: list[float], y: list[int], method: str, n_folds: int = 5) -> list[float]:
    """Out-of-fold calibration on validation for honest selection metrics."""
    s = np.asarray(scores, dtype=np.float64)
    arr_y = np.asarray(y)
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
    oof = np.zeros(len(scores), dtype=np.float64)
    for tr_idx, val_idx in skf.split(np.zeros(len(scores)), y):
        if method == "platt":
            cal = LogisticRegression(C=1.0, random_state=42)
            cal.fit(s[tr_idx].reshape(-1, 1), arr_y[tr_idx])
            oof[val_idx] = cal.predict_proba(s[val_idx].reshape(-1, 1))[:, 1]
        else:
            cal = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            cal.fit(s[tr_idx].ravel(), arr_y[tr_idx])
            oof[val_idx] = cal.predict(s[val_idx].ravel())
    return oof.tolist()


def fit_calibrator(scores: list[float], y: list[int], method: str):
    """Fit the production calibrator on the full validation split."""
    s = np.asarray(scores, dtype=np.float64).reshape(-1, 1)
    if method == "platt":
        cal = LogisticRegression(C=1.0, random_state=42)
        cal.fit(s, y)
    else:
        cal = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        cal.fit(s.ravel(), y)
    return (method, cal)


def main() -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").CRITICAL)
    )
    t0 = time.monotonic()

    # ── 1. Load the frozen Task 2 checkpoint and verify its identity ──────
    print("[load] loading Task 2 arm_d checkpoint ...")
    evaluator = HybridEvaluator.load_state(CHECKPOINT)
    params = json.loads((CHECKPOINT / "params.json").read_text(encoding="utf-8"))
    assert params.get("use_semantic_embedding") is True, "expected semantic-feature checkpoint"
    assert params.get("rf_n_estimators") == 200, "expected RF n_estimators=200 (Task 2)"
    assert params.get("random_state") == 42, "expected seed 42"

    pools = {name: load_jsonl(path) for name, path in POOL_FILES.items()}
    texts = {name: [r["text"] for r in rows] for name, rows in pools.items()}
    labels = {name: [int(r["label"]) for r in rows] for name, rows in pools.items()}
    data_info = {
        name: {"samples": len(y), "positives": sum(y), "negatives": len(y) - sum(y)}
        for name, y in labels.items()
    }
    print(f"[data] {data_info}")

    # ── 2. Raw probabilities straight from the loaded checkpoint ──────────
    print("[scores] computing raw probabilities from checkpoint ...")
    raw = {pool: evaluator.raw_probability_matrix(t) for pool, t in texts.items()}

    # Identity check against the Task 2 recorded evaluation (raw, thr=0.5).
    task2_eval = json.loads((CHECKPOINT.parent / "evaluation.json").read_text(encoding="utf-8"))
    for pool in ("validation", "test", "jbb"):
        for model, provider in MODELS.items():
            auc_now = detection_metrics(labels[pool], raw[pool][provider], threshold=0.5)["roc_auc"]
            auc_ref = task2_eval[pool][provider]["roc_auc"]
            # Task 2 records are rounded to 4 decimals.
            assert abs(auc_now - auc_ref) < 5e-5, (
                f"{model} {pool} ROC-AUC mismatch vs Task 2 record: {auc_now} != {auc_ref}"
            )
    print("[verify] raw ROC-AUC matches Task 2 evaluation.json for every model/pool")

    # ── 3. Calibration: fit on validation ONLY ────────────────────────────
    # Production method is selected PER MODEL on validation out-of-fold
    # probabilities alone: the method with the higher honest F1 at the fixed
    # production threshold wins (ties -> lower OOF Brier). Isotonic steps can
    # collapse neighbouring thresholds into identical operating points on a
    # 110-sample calibration set, so both methods are always swept and
    # reported for transparency. Test/JBB never influence this choice.
    print("[calibrate] OOF calibration on validation (platt/isotonic) ...")
    val_raw = raw["validation"]
    y_val = labels["validation"]
    calibration_meta: dict[str, dict] = {}
    chosen_method: dict[str, str] = {}
    for model, provider in MODELS.items():
        oof_scores = {m: oof_calibrate(val_raw[provider], y_val, m) for m in ("platt", "isotonic")}
        oof_briers = {m: round(brier(y_val, s), 6) for m, s in oof_scores.items()}
        f1_at_prod = {
            m: detection_metrics(y_val, s, threshold=PRODUCTION_THRESHOLD)["f1_score"]
            for m, s in oof_scores.items()
        }
        chosen = max(
            ("platt", "isotonic"),
            key=lambda m: (round(f1_at_prod[m], 10), -oof_briers[m]),
        )
        chosen_method[model] = chosen
        calibration_meta[model] = {
            "validation_oof_brier": oof_briers,
            "validation_oof_f1_at_threshold": {m: round(f1_at_prod[m], 4) for m in oof_scores},
            "selection_rule": (
                "per-model: highest validation out-of-fold F1 at the fixed "
                f"production threshold ({PRODUCTION_THRESHOLD}); ties broken "
                "by lower OOF Brier. Validation labels only."
            ),
            "selected_method": chosen,
        }
        print(
            f"[calibrate] {model}: OOF f1@{PRODUCTION_THRESHOLD}="
            f"{ {m: round(f1_at_prod[m], 4) for m in f1_at_prod} } -> {chosen}"
        )

    # Attach production calibrators (full-validation refit) so
    # probability_matrix() returns calibrated probabilities.
    for model, provider in MODELS.items():
        cal = fit_calibrator(val_raw[provider], y_val, chosen_method[model])
        evaluator.set_calibrator(provider, cal[0], cal[1])

    # ── 4. Threshold sweep on CALIBRATED probabilities ────────────────────
    print("[sweep] sweeping thresholds on calibrated probabilities ...")
    methods_to_sweep = ("platt", "isotonic")
    sweep: dict[str, dict] = {}
    for model, provider in MODELS.items():
        sweep[model] = {}
        # Validation: honest out-of-fold calibrated scores, both methods.
        for method in methods_to_sweep:
            oof_val = oof_calibrate(val_raw[provider], y_val, method)
            sweep[model][f"validation_oof_{method}"] = [
                metrics_row(y_val, oof_val, t) for t in THRESHOLDS
            ]
        # Test / JBB: full-validation-refit calibrators of BOTH methods
        # (evaluation only — never used for fitting or selection).
        refit = {m: fit_calibrator(val_raw[provider], y_val, m) for m in methods_to_sweep}
        for pool in ("test", "jbb"):
            pool_raw = raw[pool][provider]
            sweep[model][f"{pool}_raw"] = [
                metrics_row(labels[pool], pool_raw, t) for t in THRESHOLDS
            ]
            for method in methods_to_sweep:
                cal_scores = apply_probability_calibration(refit[method], pool_raw)
                sweep[model][f"{pool}_{method}"] = [
                    metrics_row(labels[pool], cal_scores, t) for t in THRESHOLDS
                ]

    # ── 5. Persist calibrated checkpoint + results ────────────────────────
    CALIBRATED_CHECKPOINT.mkdir(parents=True, exist_ok=True)
    import shutil

    evaluator.save_state(CALIBRATED_CHECKPOINT)
    for fname in ("params.json",):
        shutil.copyfile(CHECKPOINT / fname, CALIBRATED_CHECKPOINT / fname)

    results = {
        "task": "person1-task3-threshold-sweep",
        "production_threshold": PRODUCTION_THRESHOLD,
        "production_calibration": {
            model: calibration_meta[model]["selected_method"] for model in MODELS
        },
        "checkpoint_source": str(CHECKPOINT.relative_to(ROOT)),
        "checkpoint_params": params,
        "identity_check": "raw ROC-AUC equals artifacts/training_arm_d/evaluation.json",
        "data_pools": data_info,
        "split_files": {k: str(v.relative_to(ROOT)) for k, v in POOL_FILES.items()},
        "leakage_controls": {
            "calibration_fitting": "validation split only",
            "threshold_selection": (
                f"fixed policy threshold {PRODUCTION_THRESHOLD}; no data-driven "
                "threshold optimization on test or JBB"
            ),
            "jbb": "evaluation only; labels never used for fitting or selection",
        },
        "calibration": calibration_meta,
        "threshold_sweep": sweep,
    }
    (OUT / "task3_threshold_sweep.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    lines = [
        "# Person 1 — Task 3: threshold sweep (calibrated arm_d models)",
        "",
        f"- Checkpoint: `{results['checkpoint_source']}` (Task 2, verified)",
        "- Production calibration (per model, validation-only selection): "
        + ", ".join(f"{model}={calibration_meta[model]['selected_method']}" for model in MODELS),
        f"- Pools: validation={data_info['validation']['samples']} "
        f"(OOF), test={data_info['test']['samples']}, "
        f"jbb={data_info['jbb']['samples']} (evaluation only)",
        f"- Production threshold: **{PRODUCTION_THRESHOLD}**",
        "",
    ]
    for model in sweep:
        selected_key = calibration_meta[model]["selected_method"]
        for key in list(sweep[model]):
            marker = " **[SELECTED]**" if key.endswith(f"_{selected_key}") else ""
            rows = sweep[model][key]
            header = (
                "| Threshold | Precision | Recall | F1 | Accuracy | TP | TN | FP | FN | FPR | FNR |"
            )
            lines += [
                f"## {model} — {key}{marker}",
                "",
                header,
                "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
            for r in rows:
                lines.append(
                    f"| {r['threshold']:.2f} | {r['precision']:.4f} | {r['recall']:.4f} | "
                    f"{r['f1']:.4f} | {r['accuracy']:.4f} | {r['tp']} | {r['tn']} | "
                    f"{r['fp']} | {r['fn']} | {r['fpr']:.4f} | {r['fnr']:.4f} |"
                )
            lines.append("")
    (OUT / "task3_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] total {time.monotonic() - t0:.1f}s; results in {OUT}")


if __name__ == "__main__":
    main()
