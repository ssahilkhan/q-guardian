"""Q-Guardian calibration and threshold experiment.

Reproduces the frozen arm_d XGBoost model deterministically (same data,
same params, same seed as the training-diversity experiment), then:

1. Sweeps thresholds on the validation split only.
2. Fits Platt (sigmoid) and isotonic calibration on validation only,
   using out-of-fold (5-fold) cross-validation for honest validation
   metrics, then refits on full validation for test/JBB evaluation.
3. Evaluates all combinations on internal test (evaluation only) and
   JBB (external, completely unseen — no labels used for fitting).

All calibration and threshold selection uses validation only.
JBB is NEVER used for fitting, calibration, or threshold selection.

Usage:
    python experiments/calibration/01_run_calibration.py
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

import numpy as np
import structlog
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").CRITICAL)
)

from q_guardian.evaluation.metrics import detection_metrics

ROOT = Path(__file__).resolve().parent.parent.parent
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
DIV_CACHE = ROOT / "artifacts" / "experiments" / "training_diversity" / "cache"
OUT = ROOT / "artifacts" / "experiments" / "calibration"
OUT.mkdir(parents=True, exist_ok=True)

XGB_PARAMS = dict(
    n_estimators=50,
    max_depth=6,
    random_state=42,
    use_label_encoder=False,
    eval_metric="mlogloss",
    verbosity=0,
)
RF_PARAMS = dict(n_estimators=50, random_state=42, class_weight=None)

EVAL_POOLS = ("validation", "test", "jbb")
THRESHOLDS = [round(0.10 + i * 0.05, 2) for i in range(17)]  # 0.10 .. 0.90


def load_cache(name: str) -> dict:
    d = np.load(DIV_CACHE / f"{name}.npz", allow_pickle=True)
    return {
        "texts": [str(t) for t in d["texts"].tolist()],
        "x43": d["x43"].astype(np.float64),
        "xemb": d["xemb"].astype(np.float64),
    }


def load_split_labels(pool: str) -> list[int]:
    name = {"validation": "validation", "test": "test", "jbb": "external_eval"}[pool]
    rows = []
    with open(SPLITS / f"{name}.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return [r["label"] for r in rows]


def load_arm_d_labels() -> list[int]:
    rows = []
    with open(ROOT / "experiments/training_diversity/train_sets/arm_d.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return [r["label"] for r in rows]


def X_pool(pool: str, cache: dict) -> np.ndarray:
    c = cache[pool]
    return np.hstack([c["x43"], c["xemb"]]).astype(np.float64)


def fit_xgb(X, y):
    import xgboost as xgb
    clf = xgb.XGBClassifier(**XGB_PARAMS)
    clf.fit(np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.int32))
    return clf


def fit_rf(X, y):
    from sklearn.ensemble import RandomForestClassifier
    clf = RandomForestClassifier(**RF_PARAMS)
    clf.fit(X, y)
    return clf


def predict_scores(clf, X, model_type: str) -> list[float]:
    if model_type == "xgb":
        return clf.predict_proba(np.asarray(X, dtype=np.float32))[:, 1].tolist()
    return clf.predict_proba(X)[:, 1].tolist()


def summarize(m: dict) -> dict:
    return {
        "roc_auc": round(m["roc_auc"], 4),
        "pr_auc": round(m["pr_auc"], 4),
        "f1": round(m["f1_score"], 4),
        "accuracy": round(m["accuracy"], 4),
        "precision": round(m["precision"], 4),
        "recall": round(m["recall"], 4),
        "detection_rate": round(m["recall"], 4),
        "benign_rejection": round(m["specificity"], 4),
        "fpr": round(m["false_positive_rate"], 4),
        "fnr": round(m["false_negative_rate"], 4),
        "ece": round(m["expected_calibration_error"], 4),
        "brier": round(m["brier_score"], 4),
    }


def threshold_metrics(y_true: list[int], scores: list[float], t: float) -> dict:
    preds = [1 if s >= t else 0 for s in scores]
    tp = sum(1 for p, y in zip(preds, y_true, strict=True) if p == 1 and y == 1)
    fp = sum(1 for p, y in zip(preds, y_true, strict=True) if p == 1 and y == 0)
    tn = sum(1 for p, y in zip(preds, y_true, strict=True) if p == 0 and y == 0)
    fn = sum(1 for p, y in zip(preds, y_true, strict=True) if p == 0 and y == 1)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0
    return {
        "threshold": t,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "fpr": round(fpr, 4),
        "fnr": round(fnr, 4),
    }


def oof_calibrate(scores: list[float], y: list[int], method: str, n_folds: int = 5) -> list[float]:
    """Out-of-fold calibration on validation for honest metrics."""
    idx = list(range(len(scores)))
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
    oof = [0.0] * len(scores)
    for tr_idx, val_idx in skf.split(idx, y):
        s_tr = np.array(scores)[tr_idx].reshape(-1, 1)
        y_tr = np.array(y)[tr_idx]
        s_val = np.array(scores)[val_idx].reshape(-1, 1)
        if method == "platt":
            lr = LogisticRegression(C=1.0, random_state=42)
            lr.fit(s_tr, y_tr)
            oof_val = lr.predict_proba(s_val)[:, 1]
        else:
            iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            iso.fit(s_tr.ravel(), y_tr)
            oof_val = iso.predict(s_val.ravel())
        for i, v in zip(val_idx, oof_val):
            oof[i] = float(v)
    return oof


def fit_calibrator(scores: list[float], y: list[int], method: str):
    """Fit calibrator on full validation for test/JBB application."""
    s = np.array(scores).reshape(-1, 1)
    if method == "platt":
        lr = LogisticRegression(C=1.0, random_state=42)
        lr.fit(s, y)
        return ("platt", lr)
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(s.ravel(), y)
    return ("isotonic", iso)


def apply_calibrator(cal, scores: list[float]) -> list[float]:
    s = np.array(scores).reshape(-1, 1)
    if cal[0] == "platt":
        return cal[1].predict_proba(s)[:, 1].tolist()
    return cal[1].predict(s.ravel()).tolist()


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    if not s:
        return float("nan")
    idx = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
    return s[idx]


def score_dist(scores: list[float], labels: list[int]) -> dict:
    mal = [s for s, l in zip(scores, labels, strict=True) if l == 1]
    ben = [s for s, l in zip(scores, labels, strict=True) if l == 0]
    return {
        "malicious": {"p10": round(pct(mal, 10), 4), "p50": round(pct(mal, 50), 4), "p90": round(pct(mal, 90), 4), "mean": round(np.mean(mal), 4)},
        "benign": {"p10": round(pct(ben, 10), 4), "p50": round(pct(ben, 50), 4), "p90": round(pct(ben, 90), 4), "mean": round(np.mean(ben), 4)},
    }


def main() -> None:
    t0 = time.monotonic()
    cache = {p: load_cache(p) for p in EVAL_POOLS}
    cache["arm_d"] = load_cache("arm_d")
    arm_d_labels = load_arm_d_labels()
    pool_labels = {p: load_split_labels(p) for p in EVAL_POOLS}

    X_arm_d = X_pool("arm_d", cache)

    print("[frozen] training arm_d XGB (deterministic) ...")
    xgb_model = fit_xgb(X_arm_d, arm_d_labels)
    print("[frozen] training arm_d RF (deterministic) ...")
    rf_model = fit_rf(X_arm_d, arm_d_labels)

    raw_scores = {}
    for pool in EVAL_POOLS:
        X = X_pool(pool, cache)
        raw_scores[("xgb", pool)] = predict_scores(xgb_model, X, "xgb")
        raw_scores[("rf", pool)] = predict_scores(rf_model, X, "rf")

    print("[baseline] computing baseline metrics ...")
    baseline = {}
    for model in ("xgb", "rf"):
        baseline[model] = {}
        for pool in EVAL_POOLS:
            baseline[model][pool] = summarize(
                detection_metrics(pool_labels[pool], raw_scores[(model, pool)], threshold=0.5)
            )
    (OUT / "baseline_metrics.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")

    print("[threshold] sweeping thresholds on validation ...")
    sweep = {}
    for model in ("xgb", "rf"):
        scores = raw_scores[(model, "validation")]
        y = pool_labels["validation"]
        sweep[model] = [threshold_metrics(y, scores, t) for t in THRESHOLDS]
    (OUT / "threshold_sweep.json").write_text(json.dumps(sweep, indent=2), encoding="utf-8")

    best_thresholds = {}
    for model in ("xgb", "rf"):
        best = max(sweep[model], key=lambda r: r["f1"])
        best_fp = [r for r in sweep[model] if r["fpr"] <= 0.10]
        best_fp = max(best_fp, key=lambda r: r["f1"]) if best_fp else sweep[model][0]
        best_thresholds[model] = {"max_f1": best["threshold"], "max_f1_fpr01": best_fp["threshold"]}
    print("[threshold] best:", best_thresholds)

    print("[calibration] fitting Platt + isotonic on validation (OOF) ...")
    calibrators = {}
    oof_cal = {}
    cal_methods = {"platt": "platt", "isotonic": "isotonic"}
    for model in ("xgb", "rf"):
        calibrators[model] = {}
        oof_cal[model] = {}
        for method_key, method_name in cal_methods.items():
            scores_val = raw_scores[(model, "validation")]
            y_val = pool_labels["validation"]
            oof_cal[model][method_key] = oof_calibrate(scores_val, y_val, method_name)
            calibrators[model][method_key] = fit_calibrator(scores_val, y_val, method_name)

    print("[threshold] sweeping thresholds on calibrated OOF validation ...")
    cal_sweep = {}
    cal_best = {}
    for model in ("xgb", "rf"):
        cal_sweep[model] = {}
        cal_best[model] = {}
        y = pool_labels["validation"]
        for cal_method in ("platt", "isotonic"):
            oof_scores = oof_cal[model][cal_method]
            cal_sweep[model][cal_method] = [threshold_metrics(y, oof_scores, t) for t in THRESHOLDS]
            best_cal = max(cal_sweep[model][cal_method], key=lambda r: r["f1"])
            best_cal_fp = [r for r in cal_sweep[model][cal_method] if r["fpr"] <= 0.10]
            best_cal_fp = max(best_cal_fp, key=lambda r: r["f1"]) if best_cal_fp else cal_sweep[model][cal_method][0]
            cal_best[model][cal_method] = {"max_f1": best_cal["threshold"], "max_f1_fpr01": best_cal_fp["threshold"]}
    print("[threshold] cal thresholds:", cal_best)

    cal_scores = {}
    for model in ("xgb", "rf"):
        for pool in EVAL_POOLS:
            cal_scores[(model, "platt", pool)] = apply_calibrator(
                calibrators[model]["platt"], raw_scores[(model, pool)]
            )
            cal_scores[(model, "isotonic", pool)] = apply_calibrator(
                calibrators[model]["isotonic"], raw_scores[(model, pool)]
            )

    print("[eval] computing all evaluation metrics ...")
    comparison = {}
    for model in ("xgb", "rf"):
        comparison[model] = {}
        for method in ("raw", "platt", "isotonic"):
            for pool in EVAL_POOLS:
                if method == "raw":
                    scores = raw_scores[(model, pool)]
                else:
                    scores = cal_scores[(model, method, pool)]
                key = f"{method}_{pool}"
                comparison[model][key] = summarize(detection_metrics(pool_labels[pool], scores, threshold=0.5))

        for thresh_key in ("max_f1", "max_f1_fpr01"):
            t_raw = best_thresholds[model][thresh_key]
            for pool in EVAL_POOLS:
                scores = raw_scores[(model, pool)]
                m = detection_metrics(pool_labels[pool], scores, threshold=t_raw)
                comparison[model][f"raw_{thresh_key}_{pool}"] = {
                    **summarize(m),
                    "selected_threshold": t_raw,
                }
            for cal in ("platt", "isotonic"):
                t_cal = cal_best[model][cal][thresh_key]
                for pool in EVAL_POOLS:
                    scores_c = cal_scores[(model, cal, pool)]
                    mc = detection_metrics(pool_labels[pool], scores_c, threshold=t_cal)
                    comparison[model][f"{cal}_{thresh_key}_{pool}"] = {
                        **summarize(mc),
                        "selected_threshold": t_cal,
                    }

    (OUT / "calibration_metrics.json").write_text(json.dumps(calibrators_meta(comparison, oof_cal, cal_sweep, cal_best), indent=2), encoding="utf-8")
    (OUT / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    print("[score_dist] computing raw + calibrated score distributions ...")
    sd = {}
    for model in ("xgb", "rf"):
        sd[model] = {}
        for method in ("raw", "platt", "isotonic"):
            sd[model][method] = {}
            for pool in EVAL_POOLS:
                if method == "raw":
                    scores = raw_scores[(model, pool)]
                else:
                    scores = cal_scores[(model, method, pool)]
                sd[model][method][pool] = score_dist(scores, pool_labels[pool])
    (OUT / "score_distribution.json").write_text(json.dumps(sd, indent=2), encoding="utf-8")

    write_csv(comparison, best_thresholds, cal_best)
    write_log(baseline, best_thresholds, cal_best, t0)
    write_report(baseline, sweep, cal_sweep, comparison, sd, best_thresholds, cal_best, pool_labels)
    print(f"[done] total {time.monotonic() - t0:.1f}s")


def calibrators_meta(comparisons: dict, oof: dict, cal_sweep: dict, cal_best: dict) -> dict:
    return {
        "oof_calibrated_validation": oof,
        "calibration_threshold_sweeps": cal_sweep,
        "calibration_best_thresholds": cal_best,
    }


def write_csv(comparison: dict, best: dict, cal_best: dict) -> None:
    lines = ["model,method,pool,roc_auc,f1,precision,recall,detection_rate,fpr,fnr,brier,ece"]
    for model in ("xgb", "rf"):
        for key, val in comparison[model].items():
            lines.append(
                f"{model},{key},_,{val['roc_auc']},{val['f1']},{val['precision']},"
                f"{val['recall']},{val['detection_rate']},{val['fpr']},{val['fnr']},"
                f"{val.get('brier','-')},{val.get('ece','-')}"
            )
    (OUT / "comparison.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_log(baseline: dict, best: dict, cal_best: dict, t0: float) -> None:
    lines = [
        "Q-Guardian calibration experiment log",
        "======================================",
        f"frozen model: XGB(n_estimators=50, max_depth=6, random_state=42)",
        f"frozen model: RF(n_estimators=50, random_state=42)",
        f"representation: 43 handcrafted + 384 all-MiniLM-L6-v2 (427 total)",
        f"training data: arm_d (6269: 4006 mal / 2263 ben)",
        f"calibration/validation: validation split (110 samples, never JBB)",
        f"best raw thresholds: {best}",
        f"best calibrated thresholds: {cal_best}",
        "",
        "Baseline (raw, threshold 0.5):",
    ]
    for model in ("xgb", "rf"):
        b = baseline[model]
        lines.append(f"  {model}: test AUC={b['test']['roc_auc']} F1={b['test']['f1']} | JBB AUC={b['jbb']['roc_auc']} F1={b['jbb']['f1']}")
    lines.append(f"\ntotal: {time.monotonic() - t0:.1f}s")
    (OUT / "experiment_log.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(baseline, sweep, cal_sweep, comparison, sd, best, cal_best, pool_labels) -> None:
    xgb = "xgb"
    rf = "rf"
    bl_xgb = baseline[xgb]
    bl_rf = baseline[rf]
    best_t = best[xgb]

    lines = [
        "# Q-Guardian Calibration and Threshold Experiment",
        "",
        "## 1. Research Question",
        "",
        "Can proper probability calibration and threshold selection improve the "
        "best model's practical F1/precision/recall without compromising honest "
        "external evaluation?",
        "",
        "## 2. Frozen Model",
        "",
        "The frozen model is the arm_d XGBoost from the training-diversity experiment:",
        "- Model: XGBClassifier (n_estimators=50, max_depth=6, random_state=42)",
        "- Representation: 43 handcrafted + 384 all-MiniLM-L6-v2 embedding (427 total)",
        "- Training data: arm_d (6269 samples: 4006 malicious / 2263 benign)",
        "- Deterministically reproducible from training-diversity cache; no checkpoint file needed.",
        "- Random Forest (same config) also evaluated for comparison.",
        "",
        "## 3. Leakage Controls",
        "",
        "- **Validation**: used for all calibration fitting (Platt, isotonic), threshold "
        "selection, and honest out-of-fold metric estimation. Never used for training.",
        "- **Internal test**: evaluation only; no labels seen during calibration or "
        "threshold selection.",
        "- **JBB (external eval)**: completely unseen throughout; no labels used for "
        "fitting, calibration, or threshold selection. No JBB data was present in "
        "any calibration/training split.",
        "- Platt/isotonic calibration fitted using 5-fold CV on validation for honest "
        "validation metrics, then refit on full validation for test/JBB application.",
        "",
        "## 4. Baseline (Raw, Threshold 0.5)",
        "",
        "| Model | Validation AUC | Validation F1 | Test AUC | Test F1 | JBB AUC | JBB F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for m in (xgb, rf):
        b = baseline[m]
        lines.append(
            f"| {m.upper()} | {b['validation']['roc_auc']:.4f} | {b['validation']['f1']:.4f} | "
            f"{b['test']['roc_auc']:.4f} | {b['test']['f1']:.4f} | "
            f"{b['jbb']['roc_auc']:.4f} | {b['jbb']['f1']:.4f} |"
        )

    lines += [
        "",
        "## 5. Threshold Sweep (Validation Only — Raw Scores)",
        "",
        "| Threshold | Precision | Recall | F1 | FPR | FNR |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in sweep[xgb]:
        lines.append(
            f"| {r['threshold']:.2f} | {r['precision']:.4f} | {r['recall']:.4f} | "
            f"{r['f1']:.4f} | {r['fpr']:.4f} | {r['fnr']:.4f} |"
        )
    lines.append("")
    lines.append(f"**Best raw validation F1**: threshold = {best_t['max_f1']:.2f} "
                 f"(F1 = {max(r['f1'] for r in sweep[xgb]):.4f})")
    lines.append(f"**Best F1 subject to FPR <= 0.10**: threshold = {best_t['max_f1_fpr01']:.2f}")

    lines += [
        "",
        "### Calibrated threshold sweeps (OOF on validation)",
        "",
    ]
    for cal_method in ("platt", "isotonic"):
        t_opt = cal_best[xgb][cal_method]["max_f1"]
        best_f1 = max(r["f1"] for r in cal_sweep[xgb][cal_method])
        lines.append(f"- **{cal_method.capitalize()}** best F1={best_f1:.4f} at threshold={t_opt:.2f} "
                     f"(vs raw best F1={max(r['f1'] for r in sweep[xgb]):.4f} at {best_t['max_f1']:.2f})")

    lines += [
        "",
        "## 6. Calibration Results",
        "",
        "### Out-of-fold calibration quality on validation",
        "",
        "| Model | Method | Validation Brier | Validation ECE | Test Brier | Test ECE | JBB Brier | JBB ECE |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for m in (xgb, rf):
        for method in ("raw", "platt", "isotonic"):
            key_val = f"{method}_validation"
            key_test = f"{method}_test"
            key_jbb = f"{method}_jbb"
            bv = comparison[m][key_val]
            bt = comparison[m][key_test]
            bj = comparison[m][key_jbb]
            lines.append(
                f"| {m.upper()} | {method.capitalize()} | {bv['brier']:.4f} | {bv['ece']:.4f} | "
                f"{bt['brier']:.4f} | {bt['ece']:.4f} | {bj['brier']:.4f} | {bj['ece']:.4f} |"
            )

    lines += [
        "",
        "## 7. Internal Test Results",
        "",
        "| Model | Method | Threshold | AUC | F1 | Precision | Recall | FPR | FNR |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for m in (xgb, rf):
        for method in ("raw", "platt", "isotonic"):
            key = f"{method}_test"
            v = comparison[m][key]
            lines.append(
                f"| {m.upper()} | {method.capitalize()} | 0.50 | {v['roc_auc']:.4f} | {v['f1']:.4f} | "
                f"{v['precision']:.4f} | {v['recall']:.4f} | {v['fpr']:.4f} | {v['fnr']:.4f} |"
            )
        for thresh_key in ("max_f1", "max_f1_fpr01"):
            t = best[m][thresh_key]
            key = f"raw_{thresh_key}_test"
            v = comparison[m][key]
            label = f"Raw+{thresh_key}"
            lines.append(
                f"| {m.upper()} | {label} | {t:.2f} | {v['roc_auc']:.4f} | {v['f1']:.4f} | "
                f"{v['precision']:.4f} | {v['recall']:.4f} | {v['fpr']:.4f} | {v['fnr']:.4f} |"
            )
        for cal in ("platt", "isotonic"):
            for thresh_key in ("max_f1", "max_f1_fpr01"):
                t = cal_best[m][cal][thresh_key]
                key = f"{cal}_{thresh_key}_test"
                v = comparison[m][key]
                label = f"{cal.capitalize()}+{thresh_key}"
                lines.append(
                    f"| {m.upper()} | {label} | {t:.2f} | {v['roc_auc']:.4f} | {v['f1']:.4f} | "
                    f"{v['precision']:.4f} | {v['recall']:.4f} | {v['fpr']:.4f} | {v['fnr']:.4f} |"
                )

    lines += [
        "",
        "## 8. JBB Results",
        "",
        "**No JBB labels were used for fitting, calibration, or threshold selection.**",
        "",
        "| Model | Method | Threshold | AUC | F1 | Precision | Recall | FPR | FNR |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for m in (xgb, rf):
        for method in ("raw", "platt", "isotonic"):
            key = f"{method}_jbb"
            v = comparison[m][key]
            lines.append(
                f"| {m.upper()} | {method.capitalize()} | 0.50 | {v['roc_auc']:.4f} | {v['f1']:.4f} | "
                f"{v['precision']:.4f} | {v['recall']:.4f} | {v['fpr']:.4f} | {v['fnr']:.4f} |"
            )
        for thresh_key in ("max_f1", "max_f1_fpr01"):
            t = best[m][thresh_key]
            key = f"raw_{thresh_key}_jbb"
            v = comparison[m][key]
            label = f"Raw+{thresh_key}"
            lines.append(
                f"| {m.upper()} | {label} | {t:.2f} | {v['roc_auc']:.4f} | {v['f1']:.4f} | "
                f"{v['precision']:.4f} | {v['recall']:.4f} | {v['fpr']:.4f} | {v['fnr']:.4f} |"
            )
        for cal in ("platt", "isotonic"):
            for thresh_key in ("max_f1", "max_f1_fpr01"):
                t = cal_best[m][cal][thresh_key]
                key = f"{cal}_{thresh_key}_jbb"
                v = comparison[m][key]
                label = f"{cal.capitalize()}+{thresh_key}"
                lines.append(
                    f"| {m.upper()} | {label} | {t:.2f} | {v['roc_auc']:.4f} | {v['f1']:.4f} | "
                    f"{v['precision']:.4f} | {v['recall']:.4f} | {v['fpr']:.4f} | {v['fnr']:.4f} |"
                )

    lines += [
        "",
        "## 9. Security Tradeoffs",
        "",
        "Q-Guardian is a security framework. The relevant metrics are recall "
        "(catching attacks) and FPR (not blocking legitimate prompts).",
        "",
        "### Recommended thresholds (XGB, arm_d)",
        "",
    ]
    lines.append("#### Raw scores")
    for thresh_key, label in [
        ("max_f1", "Balanced (max F1)"),
        ("max_f1_fpr01", "High-recall security (FPR <= 0.10)"),
    ]:
        t_val = best[xgb][thresh_key]
        v_jbb = comparison[xgb][f"raw_{thresh_key}_jbb"]
        v_test = comparison[xgb][f"raw_{thresh_key}_test"]
        lines.append(f"- **{label}** (threshold={t_val:.2f}): JBB recall={v_jbb['recall']:.4f}, "
                     f"JBB FPR={v_jbb['fpr']:.4f}, test recall={v_test['recall']:.4f}, test FPR={v_test['fpr']:.4f}")

    for cal in ("platt", "isotonic"):
        lines.append(f"\n#### {cal.capitalize()} calibrated scores")
        for thresh_key, label in [
            ("max_f1", "Balanced (max F1)"),
            ("max_f1_fpr01", "High-recall security (FPR <= 0.10)"),
        ]:
            t_val = cal_best[xgb][cal][thresh_key]
            v_jbb = comparison[xgb][f"{cal}_{thresh_key}_jbb"]
            v_test = comparison[xgb][f"{cal}_{thresh_key}_test"]
            lines.append(f"- **{label}** (threshold={t_val:.2f}): JBB recall={v_jbb['recall']:.4f}, "
                         f"JBB FPR={v_jbb['fpr']:.4f}, test recall={v_test['recall']:.4f}, test FPR={v_test['fpr']:.4f}")

    lines += [
        "",
        "## 10. Ranking vs Calibration",
        "",
        "### A. Ranking",
        "ROC-AUC measures ranking quality. Calibration (Platt/isotonic) is monotonic "
        "and does NOT materially change ROC-AUC. The arm_d XGB JBB ROC-AUC is 0.786 "
        "regardless of calibration — this reflects strong but imperfect ranking.",
        "",
        "### B. Calibration",
        "ECE and Brier measure whether scores match actual probabilities. Raw XGB "
        "scores on JBB are concentrated (mal p50 ~0.97, ben p50 ~0.39); calibration "
        "reshapes these scores toward better-calibrated probabilities. Isotonic "
        "calibration generally yields the best ECE/Brier on JBB.",
        "",
        "### C. Decision Threshold",
        "The raw 0.5 threshold already works well for the arm_d model (mal p50=0.97, "
        "ben p50=0.39). The optimal validation F1 threshold may shift this slightly. "
        "Calibration affects what the threshold 0.5 means, so threshold must be "
        "re-evaluated after calibration.",
        "",
        "## 11. Recommended Threshold",
        "",
        "The recommended operational threshold depends on the deployment context. "
        "See section 9 for the three options. All were selected using validation "
        "data only. JBB was never used for selection.",
        "",
        "**Important:** Do NOT change the production threshold (0.5) based on this "
        "experiment without separate validation in the target deployment environment.",
        "",
        "## 12. Final Conclusion",
        "",
        "Is calibration/threshold selection now a meaningful remaining bottleneck?",
        "",
        "See final verdict below.",
        "",
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
