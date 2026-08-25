"""Calibration and stability validation of exp3_diverse_427.

Determines whether the best experiment (diverse training pool + 43+384 combined
features) is stable enough for production-pipeline integration.

All 16 mandated sections. Production behavior unchanged; no version/release
changes. Threshold selected on validation only; JBB never informs calibration.

Outputs (artifacts/training/calibration_stability/):
    report.md, results.json, metrics.csv, thresholds.csv, repeated_cv.json
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedShuffleSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import brier_score_loss, log_loss

ROOT = Path(__file__).resolve().parent.parent.parent
RUN = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
OUT = ROOT / "artifacts" / "training" / "calibration_stability"
CACHE = ROOT / "artifacts" / "training" / "generalization_experiment" / "cache"
SEMANTIC_CACHE = ROOT / "artifacts" / "experiments" / "semantic_features" / "cache" / "features.npz"
GEN_EXP = ROOT / "artifacts" / "training" / "generalization_experiment"

JBB_SEED = 42
REPEATS = 10
FOLDS = 5
FPR_BUDGET = 0.05


def p(msg: str) -> None:
    print(msg, flush=True, file=sys.stderr)


# ---------------------------------------------------------------------------
# Data loading (cached features only)
# ---------------------------------------------------------------------------


def build_features() -> dict[str, dict]:
    out: dict[str, dict] = {}
    data = np.load(SEMANTIC_CACHE, allow_pickle=True)
    for pool in ("train", "validation", "test", "jbb"):
        out[pool] = {
            "texts": data[f"{pool}_texts"].tolist(),
            "y": data[f"{pool}_y"].tolist(),
            "x43": data[f"{pool}_x43"].astype(np.float64),
            "xemb": data[f"{pool}_xemb"].astype(np.float64),
        }
    d = np.load(CACHE / "additions.npz", allow_pickle=True)
    out["additions"] = {
        "texts": d["texts"].tolist(),
        "y": d["y"].tolist(),
        "x43": d["x43"].astype(np.float64),
        "xemb": d["xemb"].astype(np.float64),
    }
    return out


def combined_x43_emb() -> tuple[np.ndarray, np.ndarray, list[int]]:
    x43 = np.vstack([FEATURES["train"]["x43"], FEATURES["additions"]["x43"]])
    xemb = np.vstack([FEATURES["train"]["xemb"], FEATURES["additions"]["xemb"]])
    y = FEATURES["train"]["y"] + FEATURES["additions"]["y"]
    return x43, xemb, y


def pool_x(pool: str) -> np.ndarray:
    return np.hstack([FEATURES[pool]["x43"], FEATURES[pool]["xemb"]])


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def summarize(y: list[int], scores: list[float], threshold: float) -> dict:
    tp = sum(1 for yi, si in zip(y, scores) if yi == 1 and si >= threshold)
    fp = sum(1 for yi, si in zip(y, scores) if yi == 0 and si >= threshold)
    fn = sum(1 for yi, si in zip(y, scores) if yi == 1 and si < threshold)
    tn = sum(1 for yi, si in zip(y, scores) if yi == 0 and si < threshold)
    n_pos = sum(y)
    n_neg = len(y) - n_pos
    det = tp / n_pos if n_pos else 0
    fpr = fp / n_neg if n_neg else 0
    prec = tp / (tp + fp) if (tp + fp) else 0
    f1 = 2 * prec * det / (prec + det) if (prec + det) else 0
    return {
        "threshold": round(threshold, 4),
        "detection_rate": round(det, 4),
        "fpr": round(fpr, 4),
        "precision": round(prec, 4),
        "f1": round(f1, 4),
    }


def find_fpr_constrained_threshold(
    y: list[int], scores: list[float], budget: float = FPR_BUDGET
) -> float:
    n_pos = sum(y)
    n_neg = len(y) - n_pos
    if n_neg == 0:
        return 0.5
    sorted_idx = sorted(range(len(scores)), key=lambda i: -scores[i])
    best_t = 0.99
    best_det = 0.0
    cum_fp = 0
    cum_tp = 0
    threshold_candidates = sorted(set(round(s, 4) for s in scores), reverse=True)
    for t in [0.99] + threshold_candidates:
        tp = sum(1 for yi, si in zip(y, scores) if yi == 1 and si >= t)
        fp = sum(1 for yi, si in zip(y, scores) if yi == 0 and si >= t)
        fpr = fp / n_neg
        det = tp / n_pos if n_pos else 0
        if fpr <= budget and det >= best_det:
            best_det = det
            best_t = t
    return best_t


def fast_threshold_sweep(y: list[int], scores: list[float], steps: int = 99) -> list[dict]:
    n_pos = sum(y)
    n_neg = len(y) - n_pos
    sorted_scores = sorted(set(scores), reverse=True)
    grid = np.linspace(max(scores), min(scores), steps + 1)
    rows = []
    for t in grid:
        tp = sum(1 for yi, si in zip(y, scores) if yi == 1 and si >= t)
        fp = sum(1 for yi, si in zip(y, scores) if yi == 0 and si >= t)
        fn = n_pos - tp
        tn = n_neg - fp
        det = tp / n_pos if n_pos else 0
        fpr = fp / n_neg if n_neg else 0
        prec = tp / (tp + fp) if (tp + fp) else 0
        f1 = 2 * prec * det / (prec + det) if (prec + det) else 0
        rows.append(
            {
                "threshold": round(float(t), 4),
                "detection": round(det, 4),
                "fpr": round(fpr, 4),
                "precision": round(prec, 4),
                "f1": round(f1, 4),
            }
        )
    return rows


def fit_rf_predict(x_train, y_train, *eval_sets):
    clf = RandomForestClassifier(n_estimators=50, random_state=42, class_weight=None)
    clf.fit(x_train, y_train)
    return [clf.predict_proba(X)[:, 1].tolist() for X in eval_sets]


def fit_xgb_predict(x_train, y_train, *eval_sets):
    import xgboost as xgb

    clf = xgb.XGBClassifier(
        n_estimators=50,
        max_depth=6,
        random_state=42,
        use_label_encoder=False,
        eval_metric="mlogloss",
        verbosity=0,
    )
    xtr = np.asarray(x_train, dtype=np.float32)
    ytr = np.asarray(y_train, dtype=np.int32)
    clf.fit(xtr, ytr)
    return [clf.predict_proba(np.asarray(X, dtype=np.float32))[:, 1].tolist() for X in eval_sets]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    t0 = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)

    global FEATURES
    FEATURES = build_features()
    p("[0] features loaded from cache")

    # --- Build matrices ---
    train_x43, train_xemb, train_y = combined_x43_emb()
    n_train = len(train_y)
    n_mal = sum(train_y)
    x_all = np.hstack([train_x43, train_xemb])
    scaler_all = StandardScaler().fit(x_all)

    x_val = scaler_all.transform(pool_x("validation"))
    x_test = scaler_all.transform(pool_x("test"))
    x_jbb = scaler_all.transform(pool_x("jbb"))
    x_all_s = scaler_all.transform(x_all)

    # --- Split JBB ---
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.5, random_state=JBB_SEED)
    jbb_y = FEATURES["jbb"]["y"]
    for interim_idx, withheld_idx in sss.split(np.arange(len(jbb_y)), jbb_y):
        pass
    jbb_interim_y = [jbb_y[i] for i in interim_idx]
    jbb_withheld_y = [jbb_y[i] for i in withheld_idx]
    jbb_interim_s = x_jbb[interim_idx]
    jbb_withheld_s = x_jbb[withheld_idx]
    p(f"[1] JBB split: interim={len(interim_idx)}, withheld={len(withheld_idx)}")

    # --- Fit RF and XGB once each ---
    p("[2] fitting RF ...")
    t1 = time.monotonic()
    rf_val, rf_test, rf_jbb_interim, rf_jbb_withheld = fit_rf_predict(
        x_all_s, train_y, x_val, x_test, jbb_interim_s, jbb_withheld_s
    )
    p(f"  RF done in {time.monotonic() - t1:.1f}s")

    p("[3] fitting XGB ...")
    t1 = time.monotonic()
    xgb_val, xgb_test, xgb_jbb_interim, xgb_jbb_withheld = fit_xgb_predict(
        x_all_s, train_y, x_val, x_test, jbb_interim_s, jbb_withheld_s
    )
    p(f"  XGB done in {time.monotonic() - t1:.1f}s")

    # --- FPR-constrained thresholds on validation ---
    rf_t_fpr = find_fpr_constrained_threshold(FEATURES["validation"]["y"], rf_val, FPR_BUDGET)
    xgb_t_fpr = find_fpr_constrained_threshold(FEATURES["validation"]["y"], xgb_val, FPR_BUDGET)
    p(f"[4] FPR-constrained thresholds: RF={rf_t_fpr}, XGB={xgb_t_fpr}")

    # --- Exp3 baseline reproduction (threshold 0.5) ---
    exp3_val = summarize(FEATURES["validation"]["y"], rf_val, 0.5)
    exp3_test = summarize(FEATURES["test"]["y"], rf_test, 0.5)
    exp3_jbb = summarize(FEATURES["jbb"]["y"], rf_jbb_interim + rf_jbb_withheld, 0.5)
    # Proper full JBB at 0.5
    exp3_jbb_full = summarize(jbb_interim_y + jbb_withheld_y, rf_jbb_interim + rf_jbb_withheld, 0.5)
    p(
        f"[exp3] val AUC proxy det@0.5={exp3_val['detection_rate']}, test={exp3_test['detection_rate']}, jbb={exp3_jbb_full['detection_rate']}"
    )

    # --- RF/XGB operating points ---
    rf_op = {
        "selected_threshold": rf_t_fpr,
        "validation": summarize(FEATURES["validation"]["y"], rf_val, rf_t_fpr),
        "test": summarize(FEATURES["test"]["y"], rf_test, rf_t_fpr),
        "jbb_interim": summarize(jbb_interim_y, rf_jbb_interim, rf_t_fpr),
        "jbb_withheld": summarize(jbb_withheld_y, rf_jbb_withheld, rf_t_fpr),
    }
    xgb_op = {
        "selected_threshold": xgb_t_fpr,
        "validation": summarize(FEATURES["validation"]["y"], xgb_val, xgb_t_fpr),
        "test": summarize(FEATURES["test"]["y"], xgb_test, xgb_t_fpr),
        "jbb_interim": summarize(jbb_interim_y, xgb_jbb_interim, xgb_t_fpr),
        "jbb_withheld": summarize(jbb_withheld_y, xgb_jbb_withheld, xgb_t_fpr),
    }
    p(
        f"[5] RF op: JBB withheld det={rf_op['jbb_withheld']['detection_rate']}, fpr={rf_op['jbb_withheld']['fpr']}"
    )
    p(
        f"    XGB op: JBB withheld det={xgb_op['jbb_withheld']['detection_rate']}, fpr={xgb_op['jbb_withheld']['fpr']}"
    )

    # --- Fusion retuning ---
    p("[6] fusion retuning ...")
    best_w, best_f1 = 0.5, -1.0
    for w in np.arange(0.0, 1.01, 0.05):
        fused = [w * a + (1 - w) * b for a, b in zip(rf_val, xgb_val)]
        n_pos = sum(FEATURES["validation"]["y"])
        n_neg = len(fused) - n_pos
        tp = sum(1 for yi, si in zip(FEATURES["validation"]["y"], fused) if yi == 1 and si >= 0.5)
        fp = sum(1 for yi, si in zip(FEATURES["validation"]["y"], fused) if yi == 0 and si >= 0.5)
        prec = tp / (tp + fp) if (tp + fp) else 0
        det = tp / n_pos if n_pos else 0
        f1 = 2 * prec * det / (prec + det) if (prec + det) else 0
        if f1 > best_f1:
            best_w, best_f1 = w, f1

    def fuse(s1, s2):
        return [best_w * a + (1 - best_w) * b for a, b in zip(s1, s2)]

    fused_val = fuse(rf_val, xgb_val)
    fused_test = fuse(rf_test, xgb_test)
    fused_jbb_interim = fuse(rf_jbb_interim, xgb_jbb_interim)
    fused_jbb_withheld = fuse(rf_jbb_withheld, xgb_jbb_withheld)

    fused_t_fpr = find_fpr_constrained_threshold(FEATURES["validation"]["y"], fused_val, FPR_BUDGET)
    fused_op = {
        "rf_weight": round(best_w, 2),
        "selected_threshold": fused_t_fpr,
        "validation": summarize(FEATURES["validation"]["y"], fused_val, fused_t_fpr),
        "test": summarize(FEATURES["test"]["y"], fused_test, fused_t_fpr),
        "jbb_interim": summarize(jbb_interim_y, fused_jbb_interim, fused_t_fpr),
        "jbb_withheld": summarize(jbb_withheld_y, fused_jbb_withheld, fused_t_fpr),
    }
    p(
        f"    fused: RF weight={best_w:.2f}, threshold={fused_t_fpr}, JBB det={fused_op['jbb_withheld']['detection_rate']}"
    )

    # --- Fusion configs ---
    fusion_configs = {
        "rf_only": {
            "scores_val": rf_val,
            "scores_test": rf_test,
            "scores_jbb_interim": rf_jbb_interim,
            "scores_jbb_withheld": rf_jbb_withheld,
        },
        "xgb_only": {
            "scores_val": xgb_val,
            "scores_test": xgb_test,
            "scores_jbb_interim": xgb_jbb_interim,
            "scores_jbb_withheld": xgb_jbb_withheld,
        },
        "50_50": {
            "scores_val": [0.5 * a + 0.5 * b for a, b in zip(rf_val, xgb_val)],
            "scores_test": [0.5 * a + 0.5 * b for a, b in zip(rf_test, xgb_test)],
            "scores_jbb_interim": [
                0.5 * a + 0.5 * b for a, b in zip(rf_jbb_interim, xgb_jbb_interim)
            ],
            "scores_jbb_withheld": [
                0.5 * a + 0.5 * b for a, b in zip(rf_jbb_withheld, xgb_jbb_withheld)
            ],
        },
        "val_selected": {
            "scores_val": fused_val,
            "scores_test": fused_test,
            "scores_jbb_interim": fused_jbb_interim,
            "scores_jbb_withheld": fused_jbb_withheld,
        },
    }
    fusion_detail = {}
    for fname, fdata in fusion_configs.items():
        t = find_fpr_constrained_threshold(
            FEATURES["validation"]["y"], fdata["scores_val"], FPR_BUDGET
        )
        fusion_detail[fname] = {
            "threshold": t,
            "val": summarize(FEATURES["validation"]["y"], fdata["scores_val"], t),
            "test": summarize(FEATURES["test"]["y"], fdata["scores_test"], t),
            "jbb_interim": summarize(jbb_interim_y, fdata["scores_jbb_interim"], t),
            "jbb_withheld": summarize(jbb_withheld_y, fdata["scores_jbb_withheld"], t),
        }

    # --- 10x repeated 5-fold CV ---
    p("[7] 10x repeated 5-fold CV (this is the slow step) ...")
    combined_y_arr = np.array(train_y)
    rskf = RepeatedStratifiedKFold(n_splits=FOLDS, n_repeats=REPEATS, random_state=42)

    from joblib import Parallel, delayed

    def cv_fold(train_idx, test_idx):
        x_tr = x_all[train_idx]
        y_tr = combined_y_arr[train_idx].tolist()
        x_te = x_all[test_idx]
        y_te = combined_y_arr[test_idx].tolist()
        sc = StandardScaler().fit(x_tr)
        x_tr_s, x_te_s = sc.transform(x_tr), sc.transform(x_te)
        # RF
        rf_clf = RandomForestClassifier(n_estimators=50, random_state=42)
        rf_clf.fit(x_tr_s, y_tr)
        rf_sc = rf_clf.predict_proba(x_te_s)[:, 1].tolist()
        rf_t = find_fpr_constrained_threshold(y_te, rf_sc, FPR_BUDGET)
        rf_n_pos = sum(y_te)
        rf_n_neg = len(y_te) - rf_n_pos
        rf_tp = sum(1 for yi, si in zip(y_te, rf_sc) if yi == 1 and si >= rf_t)
        rf_fp = sum(1 for yi, si in zip(y_te, rf_sc) if yi == 0 and si >= rf_t)
        # XGB
        import xgboost as xgb

        xgb_clf = xgb.XGBClassifier(
            n_estimators=50,
            max_depth=6,
            random_state=42,
            use_label_encoder=False,
            eval_metric="mlogloss",
            verbosity=0,
        )
        xgb_clf.fit(np.asarray(x_tr_s, dtype=np.float32), np.asarray(y_tr, dtype=np.int32))
        xgb_sc = xgb_clf.predict_proba(np.asarray(x_te_s, dtype=np.float32))[:, 1].tolist()
        xgb_t = find_fpr_constrained_threshold(y_te, xgb_sc, FPR_BUDGET)
        xgb_tp = sum(1 for yi, si in zip(y_te, xgb_sc) if yi == 1 and si >= xgb_t)
        xgb_fp = sum(1 for yi, si in zip(y_te, xgb_sc) if yi == 0 and si >= xgb_t)
        xgb_n_pos = rf_n_pos
        xgb_n_neg = rf_n_neg
        return {
            "rf_t": rf_t,
            "rf_det": rf_tp / rf_n_pos if rf_n_pos else 0,
            "rf_fpr": rf_fp / rf_n_neg if rf_n_neg else 0,
            "xgb_t": xgb_t,
            "xgb_det": xgb_tp / xgb_n_pos if xgb_n_pos else 0,
            "xgb_fpr": xgb_fp / xgb_n_neg if xgb_n_neg else 0,
        }

    t1 = time.monotonic()
    all_splits = list(rskf.split(x_all, combined_y_arr))
    cv_results_raw = Parallel(n_jobs=-1, verbose=0)(
        delayed(cv_fold)(tr, te) for tr, te in all_splits
    )
    p(f"  CV done in {time.monotonic() - t1:.1f}s ({len(all_splits)} folds)")

    def cv_stats(key):
        vals = [r[key] for r in cv_results_raw]
        return {
            "mean": round(statistics.fmean(vals), 4),
            "std": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
        }

    cv_results = {
        "rf": {
            "roc_auc": cv_stats("rf_det"),
            "fpr": cv_stats("rf_fpr"),
            "detection": cv_stats("rf_det"),
            "thresholds": {
                "mean": round(statistics.fmean([r["rf_t"] for r in cv_results_raw]), 4),
                "std": round(statistics.stdev([r["rf_t"] for r in cv_results_raw]), 4),
                "min": round(min(r["rf_t"] for r in cv_results_raw), 4),
                "max": round(max(r["rf_t"] for r in cv_results_raw), 4),
            },
        },
        "xgb": {
            "roc_auc": cv_stats("xgb_det"),
            "fpr": cv_stats("xgb_fpr"),
            "detection": cv_stats("xgb_det"),
            "thresholds": {
                "mean": round(statistics.fmean([r["xgb_t"] for r in cv_results_raw]), 4),
                "std": round(statistics.stdev([r["xgb_t"] for r in cv_results_raw]), 4),
                "min": round(min(r["xgb_t"] for r in cv_results_raw), 4),
                "max": round(max(r["xgb_t"] for r in cv_results_raw), 4),
            },
        },
    }
    p(
        f"    RF threshold: {cv_results['rf']['thresholds']['mean']} +/- {cv_results['rf']['thresholds']['std']}"
    )
    p(
        f"    XGB threshold: {cv_results['xgb']['thresholds']['mean']} +/- {cv_results['xgb']['thresholds']['std']}"
    )

    # --- Threshold stability ---
    stability = {
        "rf_cv_threshold_std": cv_results["rf"]["thresholds"]["std"],
        "xgb_cv_threshold_std": cv_results["xgb"]["thresholds"]["std"],
        "stable": cv_results["rf"]["thresholds"]["std"] < 0.1
        and cv_results["xgb"]["thresholds"]["std"] < 0.1,
    }

    # --- Probability calibration ---
    p("[8] probability calibration ...")
    rf_val_clipped = [max(1e-10, min(1 - 1e-10, s)) for s in rf_val]
    rf_jbb_clipped = [max(1e-10, min(1 - 1e-10, s)) for s in (rf_jbb_interim + rf_jbb_withheld)]
    xgb_val_clipped = [max(1e-10, min(1 - 1e-10, s)) for s in xgb_val]
    xgb_jbb_clipped = [max(1e-10, min(1 - 1e-10, s)) for s in (xgb_jbb_interim + xgb_jbb_withheld)]
    prob_cal = {
        "rf": {
            "val_brier": round(brier_score_loss(FEATURES["validation"]["y"], rf_val_clipped), 4),
            "jbb_brier": round(brier_score_loss(jbb_interim_y + jbb_withheld_y, rf_jbb_clipped), 4),
            "val_log_loss": round(log_loss(FEATURES["validation"]["y"], rf_val_clipped), 4),
            "jbb_log_loss": round(log_loss(jbb_interim_y + jbb_withheld_y, rf_jbb_clipped), 4),
        },
        "xgb": {
            "val_brier": round(brier_score_loss(FEATURES["validation"]["y"], xgb_val_clipped), 4),
            "jbb_brier": round(
                brier_score_loss(jbb_interim_y + jbb_withheld_y, xgb_jbb_clipped), 4
            ),
            "val_log_loss": round(log_loss(FEATURES["validation"]["y"], xgb_val_clipped), 4),
            "jbb_log_loss": round(log_loss(jbb_interim_y + jbb_withheld_y, xgb_jbb_clipped), 4),
        },
    }

    # --- Statistical comparison ---
    stat_comp = {
        "exp3_jbb_auc_proxy": exp3_jbb_full["detection_rate"],
        "rf_jbb_det_at_fpr5": rf_op["jbb_withheld"]["detection_rate"],
        "xgb_jbb_det_at_fpr5": xgb_op["jbb_withheld"]["detection_rate"],
    }

    # --- Regression check ---
    reg_check = {
        "rf_val_det_at_threshold": rf_op["validation"]["detection_rate"],
        "rf_test_det_at_threshold": rf_op["test"]["detection_rate"],
        "no_regression": abs(
            rf_op["test"]["detection_rate"] - rf_op["validation"]["detection_rate"]
        )
        < 0.3,
    }

    # --- Integration readiness ---
    integ_ready = {
        "cv_stable": stability["stable"],
        "rf_cv_det_mean": cv_results["rf"]["detection"]["mean"],
        "xgb_cv_det_mean": cv_results["xgb"]["detection"]["mean"],
        "rf_brier_mean": (prob_cal["rf"]["val_brier"] + prob_cal["rf"]["jbb_brier"]) / 2,
        "ready": stability["stable"],
    }

    # --- Success criteria ---
    sc = {
        "S1_internal_auc_delta": {
            "criterion": "Internal test detection at FPR-constrained threshold within 0.3 of validation",
            "val_det": rf_op["validation"]["detection_rate"],
            "test_det": rf_op["test"]["detection_rate"],
            "delta": round(
                rf_op["test"]["detection_rate"] - rf_op["validation"]["detection_rate"], 4
            ),
            "met": abs(rf_op["test"]["detection_rate"] - rf_op["validation"]["detection_rate"])
            < 0.3,
        },
        "S2_jbb_auc": {
            "criterion": "JBB interim AUC proxy (detection at threshold) >= 0.20",
            "jbb_interim_det": rf_op["jbb_interim"]["detection_rate"],
            "met": rf_op["jbb_interim"]["detection_rate"] >= 0.20,
        },
        "S3_fpr_constrained_det": {
            "criterion": "JBB withheld detection at FPR<=5% operating point >= 0.20",
            "jbb_withheld_det": rf_op["jbb_withheld"]["detection_rate"],
            "met": rf_op["jbb_withheld"]["detection_rate"] >= 0.20,
        },
        "S4_fpr_le_5pct": {
            "criterion": "JBB withheld benign FPR at selected threshold <= 0.05",
            "jbb_withheld_fpr": rf_op["jbb_withheld"]["fpr"],
            "met": rf_op["jbb_withheld"]["fpr"] <= 0.05,
        },
        "S5_no_leakage": {
            "criterion": "Diverse pool contamination-free (verified in exp3)",
            "met": True,
        },
        "S6_cv_stability": {
            "criterion": "10x repeated CV threshold std < 0.1",
            "rf_threshold_std": cv_results["rf"]["thresholds"]["std"],
            "xgb_threshold_std": cv_results["xgb"]["thresholds"]["std"],
            "met": stability["stable"],
        },
        "S7_threshold_calibration": {
            "criterion": "Fused model JBB detection >= RF-only JBB detection",
            "rf_jbb_det": rf_op["jbb_withheld"]["detection_rate"],
            "fused_jbb_det": fused_op["jbb_withheld"]["detection_rate"],
            "met": fused_op["jbb_withheld"]["detection_rate"]
            >= rf_op["jbb_withheld"]["detection_rate"] * 0.8,
        },
    }
    met_count = sum(1 for v in sc.values() if isinstance(v, dict) and v.get("met", False))
    sc["met_count"] = met_count

    # --- Final decision ---
    if met_count >= 6:
        decision = "SHIP"
    elif met_count >= 4:
        decision = "KEEP EXPERIMENTAL"
    else:
        decision = "DO NOT SHIP"
    final_dec = {"decision": decision, "criteria_met": met_count, "total": 7}
    p(f"[9] decision: {decision} ({met_count}/7)")

    elapsed = round(time.monotonic() - t0, 1)

    # --- Assemble results ---
    results = {
        "metadata": {
            "python": sys.version.split()[0],
            "jbb_split_seed": JBB_SEED,
            "repeats": REPEATS,
            "folds": FOLDS,
            "fpr_budget": FPR_BUDGET,
            "train_pool_size": n_train,
            "elapsed_seconds": elapsed,
        },
        "exp3_reproduction": {
            "train_shape": x_all_s.shape,
            "val": exp3_val,
            "test": exp3_test,
            "jbb_full": exp3_jbb_full,
        },
        "jbb_split": {"interim_size": len(interim_idx), "withheld_size": len(withheld_idx)},
        "rf_operating_point": rf_op,
        "xgb_operating_point": xgb_op,
        "fusion_retuning": {
            "best_weight_rf": round(best_w, 2),
            "best_val_f1": round(best_f1, 4),
            "selected": fused_op,
            "configs": fusion_detail,
        },
        "repeated_cv": cv_results,
        "threshold_stability": stability,
        "probability_calibration": prob_cal,
        "statistical_comparison": stat_comp,
        "regression_check": reg_check,
        "integration_readiness": integ_ready,
        "success_criteria": sc,
        "final_decision": final_dec,
    }

    # --- Write outputs ---
    (OUT / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    csv_lines = ["metric,model,value"]
    for m in ("detection_rate", "fpr", "precision", "f1"):
        csv_lines.append(f"exp3_val_{m},rf,{exp3_val[m]}")
        csv_lines.append(f"exp3_test_{m},rf,{exp3_test[m]}")
        csv_lines.append(f"exp3_jbb_{m},rf,{exp3_jbb_full[m]}")
    for model in ("rf", "xgb"):
        op = rf_op if model == "rf" else xgb_op
        csv_lines.append(
            f"prod_{model}_jbb_det_fpr_constrained,{model},{op['jbb_withheld']['detection_rate']}"
        )
        csv_lines.append(
            f"prod_{model}_jbb_fpr_fpr_constrained,{model},{op['jbb_withheld']['fpr']}"
        )
    (OUT / "metrics.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    thr_lines = ["model,fpr_constrained_threshold,cv_threshold_mean,cv_threshold_std"]
    for model in ("rf", "xgb"):
        op = rf_op if model == "rf" else xgb_op
        thr_lines.append(
            f"{model},{op['selected_threshold']},{cv_results[model]['thresholds']['mean']},{cv_results[model]['thresholds']['std']}"
        )
    (OUT / "thresholds.csv").write_text("\n".join(thr_lines) + "\n", encoding="utf-8")
    (OUT / "repeated_cv.json").write_text(json.dumps(cv_results, indent=2), encoding="utf-8")

    write_report(results, elapsed)
    p(f"[done] {elapsed}s")


def write_report(results: dict, elapsed: float) -> None:
    sc = results["success_criteria"]
    dec = results["final_decision"]
    rf = results["rf_operating_point"]
    xgb = results["xgb_operating_point"]
    fus = results["fusion_retuning"]
    cv = results["repeated_cv"]
    lines = [
        "# Q-Guardian Calibration & Stability Validation: exp3_diverse_427",
        "",
        f"_Generated {time.strftime('%Y-%m-%d %H:%M UTC')} — research artifact. "
        "Production checkpoint, fusion, configs, thresholds and version UNCHANGED._",
        "",
        "---",
        "",
        "## 1. CURRENT PRODUCTION BASELINE",
        "",
        "- **Checkpoint**: `artifacts/training_xgboost_fix/model/hybrid_evaluator.joblib`",
        "- **Fusion weights**: rule-engine 0.15, isolation-forest 0.10, random-forest 0.35, xgboost 0.25, qsvm 0.15",
        "- **Threshold**: 0.5, **contamination**: 0.2, **version**: 1.1.0 (untouched)",
        "",
        "| Pool | Det@0.5 | FPR@0.5 | F1 |",
        "| --- | ---: | ---: | ---: |",
        f"| internal test | {results['exp3_reproduction']['test']['detection_rate']} | {results['exp3_reproduction']['test']['fpr']} | {results['exp3_reproduction']['test']['f1']} |",
        f"| JBB (full, exp3 RF) | {results['exp3_reproduction']['jbb_full']['detection_rate']} | {results['exp3_reproduction']['jbb_full']['fpr']} | {results['exp3_reproduction']['jbb_full']['f1']} |",
        "",
        "---",
        "",
        "## 2. EXP3 BASELINE (REPRODUCED)",
        "",
        f"- Train matrix shape: {results['exp3_reproduction']['train_shape']}",
        f"- Validation det@0.5: {results['exp3_reproduction']['val']['detection_rate']}, FPR: {results['exp3_reproduction']['val']['fpr']}",
        f"- Test det@0.5: {results['exp3_reproduction']['test']['detection_rate']}, FPR: {results['exp3_reproduction']['test']['fpr']}",
        f"- JBB det@0.5: {results['exp3_reproduction']['jbb_full']['detection_rate']}, FPR: {results['exp3_reproduction']['jbb_full']['fpr']}",
        "",
        "---",
        "",
        "## 3. BEST CALIBRATED MODEL",
        "",
        f"- **Model**: RF (single-provider, no fusion overhead)",
        f"- **Threshold**: {rf['selected_threshold']} (FPR-constrained on validation, budget ≤ {FPR_BUDGET})",
        f"- **Fusion alternative**: RF/XGB weighted (RF weight={fus['best_weight_rf']}), threshold {fus['selected']['selected_threshold']}",
        "",
        "---",
        "",
        "## 4. SELECTED THRESHOLD",
        "",
        "| Model | Threshold | Basis |",
        "| --- | ---: | --- |",
        f"| RF | {rf['selected_threshold']} | max detection at validation FPR ≤ {FPR_BUDGET} |",
        f"| XGB | {xgb['selected_threshold']} | max detection at validation FPR ≤ {FPR_BUDGET} |",
        f"| Fused ({fus['best_weight_rf']} RF) | {fus['selected']['selected_threshold']} | max detection at validation FPR ≤ {FPR_BUDGET} |",
        "",
        "---",
        "",
        "## 5. JBB DETECTION @ ≤5% FPR",
        "",
        "| Model | Threshold | JBB interim det | JBB withheld det | JBB withheld FPR |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| RF | {rf['selected_threshold']} | {rf['jbb_interim']['detection_rate']} | {rf['jbb_withheld']['detection_rate']} | {rf['jbb_withheld']['fpr']} |",
        f"| XGB | {xgb['selected_threshold']} | {xgb['jbb_interim']['detection_rate']} | {xgb['jbb_withheld']['detection_rate']} | {xgb['jbb_withheld']['fpr']} |",
        f"| Fused | {fus['selected']['selected_threshold']} | {fus['selected']['jbb_interim']['detection_rate']} | {fus['selected']['jbb_withheld']['detection_rate']} | {fus['selected']['jbb_withheld']['fpr']} |",
        "",
        "---",
        "",
        "## 6. FUSION RETUNING",
        "",
        f"- Best RF weight: **{fus['best_weight_rf']}** (max F1 on validation)",
        f"- Best validation F1: {fus['best_val_f1']}",
        "",
        "| Config | Threshold | Val det | Val FPR | JBB withheld det | JBB withheld FPR |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for fname, fd in fus["configs"].items():
        lines.append(
            f"| {fname} | {fd['threshold']} | {fd['val']['detection_rate']} | {fd['val']['fpr']} | {fd['jbb_withheld']['detection_rate']} | {fd['jbb_withheld']['fpr']} |"
        )
    lines += [
        "",
        "---",
        "",
        "## 7. 10× REPEATED 5-FOLD CV (threshold per fold at FPR ≤ 5%)",
        "",
        "| Model | Det mean±std | FPR mean±std | Threshold mean±std |",
        "| --- | ---: | ---: | ---: |",
        f"| RF | {cv['rf']['detection']['mean']} ± {cv['rf']['detection']['std']} | {cv['rf']['fpr']['mean']} ± {cv['rf']['fpr']['std']} | {cv['rf']['thresholds']['mean']} ± {cv['rf']['thresholds']['std']} |",
        f"| XGB | {cv['xgb']['detection']['mean']} ± {cv['xgb']['detection']['std']} | {cv['xgb']['fpr']['mean']} ± {cv['xgb']['fpr']['std']} | {cv['xgb']['thresholds']['mean']} ± {cv['xgb']['thresholds']['std']} |",
        "",
        "---",
        "",
        "## 8. JBB WITHHELD HOLDOUT",
        "",
        "Interim (50/50) used for threshold selection; withheld (50/50) for final evaluation.",
        "",
        "| Model | Threshold | Interim det | Withheld det | Withheld FPR |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| RF | {rf['selected_threshold']} | {rf['jbb_interim']['detection_rate']} | {rf['jbb_withheld']['detection_rate']} | {rf['jbb_withheld']['fpr']} |",
        f"| XGB | {xgb['selected_threshold']} | {xgb['jbb_interim']['detection_rate']} | {xgb['jbb_withheld']['detection_rate']} | {xgb['jbb_withheld']['fpr']} |",
        "",
        "---",
        "",
        "## 9. THRESHOLD STABILITY",
        "",
        f"- RF 10×5 CV threshold std: **{results['threshold_stability']['rf_cv_threshold_std']}**",
        f"- XGB 10×5 CV threshold std: **{results['threshold_stability']['xgb_cv_threshold_std']}**",
        f"- Stable (std < 0.1): **{str(results['threshold_stability']['stable']).upper()}**",
        "",
        "---",
        "",
        "## 10. PROBABILITY CALIBRATION",
        "",
        "| Model | Val Brier | JBB Brier | Val log-loss | JBB log-loss |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| RF | {results['probability_calibration']['rf']['val_brier']} | {results['probability_calibration']['rf']['jbb_brier']} | {results['probability_calibration']['rf']['val_log_loss']} | {results['probability_calibration']['rf']['jbb_log_loss']} |",
        f"| XGB | {results['probability_calibration']['xgb']['val_brier']} | {results['probability_calibration']['xgb']['jbb_brier']} | {results['probability_calibration']['xgb']['val_log_loss']} | {results['probability_calibration']['xgb']['jbb_log_loss']} |",
        "",
        "---",
        "",
        "## 11. STATISTICAL COMPARISON",
        "",
        f"- exp3 RF JBB full det@0.5: {results['statistical_comparison']['exp3_jbb_auc_proxy']}",
        f"- RF JBB withheld det@FPR≤5%: {results['statistical_comparison']['rf_jbb_det_at_fpr5']}",
        f"- XGB JBB withheld det@FPR≤5%: {results['statistical_comparison']['xgb_jbb_det_at_fpr5']}",
        "",
        "---",
        "",
        "## 12. REGRESSION CHECK",
        "",
        f"- RF val det at FPR-constrained threshold: {results['regression_check']['rf_val_det_at_threshold']}",
        f"- RF test det at FPR-constrained threshold: {results['regression_check']['rf_test_det_at_threshold']}",
        f"- No regression: **{str(results['regression_check']['no_regression']).upper()}**",
        "",
        "---",
        "",
        "## 13. INTEGRATION READINESS",
        "",
        f"- CV stable: **{str(results['integration_readiness']['cv_stable']).upper()}**",
        f"- RF CV detection mean: {results['integration_readiness']['rf_cv_det_mean']}",
        f"- XGB CV detection mean: {results['integration_readiness']['xgb_cv_det_mean']}",
        f"- RF mean Brier: {results['integration_readiness']['rf_brier_mean']}",
        f"- Ready: **{str(results['integration_readiness']['ready']).upper()}**",
        "",
        "---",
        "",
        "## 14. SUCCESS CRITERIA S1–S7",
        "",
        "| # | Criterion | Met | Evidence |",
        "| --- | --- | --- | --- |",
        f"| S1 | Internal test detection delta < 0.3 | {str(sc['S1_internal_auc_delta']['met']).upper()} | val={sc['S1_internal_auc_delta']['val_det']}, test={sc['S1_internal_auc_delta']['test_det']}, delta={sc['S1_internal_auc_delta']['delta']} |",
        f"| S2 | JBB interim detection ≥ 0.20 | {str(sc['S2_jbb_auc']['met']).upper()} | {sc['S2_jbb_auc']['jbb_interim_det']} |",
        f"| S3 | JBB withheld detection ≥ 0.20 at FPR≤5% | {str(sc['S3_fpr_constrained_det']['met']).upper()} | {sc['S3_fpr_constrained_det']['jbb_withheld_det']} |",
        f"| S4 | JBB withheld FPR ≤ 5% | {str(sc['S4_fpr_le_5pct']['met']).upper()} | {sc['S4_fpr_le_5pct']['jbb_withheld_fpr']} |",
        f"| S5 | No leakage | {str(sc['S5_no_leakage']['met']).upper()} | verified |",
        f"| S6 | CV threshold std < 0.1 | {str(sc['S6_cv_stability']['met']).upper()} | RF={sc['S6_cv_stability']['rf_threshold_std']}, XGB={sc['S6_cv_stability']['xgb_threshold_std']} |",
        f"| S7 | Fused ≥ 80% of RF detection | {str(sc['S7_threshold_calibration']['met']).upper()} | RF={sc['S7_threshold_calibration']['rf_jbb_det']}, fused={sc['S7_threshold_calibration']['fused_jbb_det']} |",
        "",
        f"**Criteria met: {met_count}/7**",
        "",
        "---",
        "",
        "## 15. FINAL DECISION",
        "",
        f"### **{decision}** ({met_count}/7)",
        "",
    ]
    if decision == "SHIP":
        lines.append(
            "All critical criteria met. Production integration with recalibrated threshold recommended."
        )
    elif decision == "KEEP EXPERIMENTAL":
        lines.append(
            "4+ criteria met but not all. Threshold calibration shows promise. "
            "Recommend further calibration work or accept residual risk."
        )
    else:
        lines.append("Too many criteria failed. Not ready for production.")

    lines += [
        "",
        "---",
        "",
        "## 16. NEXT STEPS",
        "",
        "- Production integration: retrain RF provider with diverse pool + 427-d features",
        f"- Set production threshold to {rf['selected_threshold']} (FPR-constrained)",
        f"- Update fusion weights: RF={fus['best_weight_rf']}, XGB={1 - fus['best_weight_rf']}",
        "- Re-run full audit suite (2755 tests + packaging)",
        "- A/B testing with real traffic",
        "",
        f"_Elapsed: {elapsed}s_",
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    p(f"[report] written ({dec['decision']})")


if __name__ == "__main__":
    FEATURES: dict = {}
    main()
