"""Calibration verification for arm_d checkpoint.

Reproduces threshold sweep on validation, applies Platt/isotonic calibration,
evaluates on internal test + JBB external. Documents that calibration
does NOT transfer to JBB honestly.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import structlog
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import MinMaxScaler

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").CRITICAL)
)

ROOT = Path(__file__).resolve().parents[2]
DIV_CACHE = ROOT / "artifacts" / "experiments" / "training_diversity" / "cache"
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
ARM_D_DIR = ROOT / "artifacts" / "training_arm_d"
OUT_DIR = ROOT / "artifacts" / "experiments" / "calibration_verification"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_cache(name: str) -> dict:
    d = np.load(DIV_CACHE / f"{name}.npz", allow_pickle=True)
    return {
        "texts": [str(t) for t in d["texts"].tolist()],
        "x43": d["x43"].astype(np.float64),
        "xemb": d["xemb"].astype(np.float64),
    }


def load_labels(split_name: str) -> list[int]:
    rows = []
    with open(SPLITS / f"{split_name}.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return [r["label"] for r in rows]


def load_arm_d_components():
    """Load raw models + scaler from joblib checkpoint."""
    state = joblib.load(ARM_D_DIR / "hybrid_evaluator.joblib")
    return {
        "params": state["params"],
        "scaler": state["scaler"],
        "anomaly": state["anomaly"],
        "rf": state["rf"],
        "xgb": state["xgb"],
    }


def get_provider_scores(components, x: np.ndarray) -> dict[str, list[float]]:
    """Get scores from each provider using cached features."""
    scaler = components["scaler"]
    x_scaled = scaler.transform(x)

    scores = {}

    anomaly = components["anomaly"]
    if anomaly and anomaly._model is not None:
        if_decision = -anomaly._model.decision_function(x_scaled)
        scores["isolation-forest"] = (
            MinMaxScaler().fit_transform(if_decision.reshape(-1, 1)).flatten().tolist()
        )

    rf = components["rf"]
    if rf and rf._model is not None:
        rf_proba = rf._model.predict_proba(x_scaled)[:, 1]
        scores["random-forest"] = rf_proba.tolist()

    xgb = components["xgb"]
    if xgb and xgb._model is not None:
        xgb_proba = xgb._model.predict_proba(np.asarray(x_scaled, dtype=np.float32))[:, 1]
        scores["xgboost"] = xgb_proba.tolist()

    # Fusion: weighted average
    weights = components["params"]["provider_weights"]
    available = {k: v for k, v in weights.items() if k in scores}
    if available:
        total_w = sum(available.values())
        norm_weights = {k: v / total_w for k, v in available.items()}
        fusion_scores = np.zeros(len(x))
        for provider, w in norm_weights.items():
            fusion_scores += w * np.array(scores[provider])
        scores["fusion"] = fusion_scores.tolist()

    return scores


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
            # Platt scaling: logistic regression on scores
            lr = LogisticRegression(max_iter=1000, random_state=42)
            lr.fit(s_tr, y_tr)
            oof_val = lr.predict_proba(s_val)[:, 1]
        elif method == "isotonic":
            cal = IsotonicRegression(out_of_bounds="clip")
            cal.fit(s_tr.flatten(), y_tr)
            oof_val = cal.predict(s_val.flatten())
        else:
            raise ValueError(method)
        for i, vi in enumerate(val_idx):
            oof[vi] = oof_val[i]
    return oof


def fit_calibrator(scores: list[float], y: list[int], method: str):
    """Fit calibrator on full validation for test/JBB application."""
    s = np.array(scores).reshape(-1, 1)
    if method == "platt":
        lr = LogisticRegression(max_iter=1000, random_state=42)
        lr.fit(s, y)
        return lr
    if method == "isotonic":
        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(s.flatten(), y)
        return cal
    raise ValueError(method)


def apply_calibrator(cal, scores: list[float]) -> list[float]:
    s = np.array(scores).reshape(-1, 1)
    if hasattr(cal, "predict_proba"):
        return cal.predict_proba(s)[:, 1].tolist()
    return cal.predict(s.flatten()).tolist()


def metrics_at_threshold(y_true: list[int], scores: list[float], t: float) -> dict:
    from q_guardian.evaluation.metrics import detection_metrics

    return detection_metrics(y_true, scores, threshold=t)


def main() -> int:
    print("Loading arm_d components...")
    components = load_arm_d_components()

    # Load all splits
    val_cache = load_cache("validation")
    val_labels = load_labels("validation")  # 110 samples
    x_val = np.hstack([val_cache["x43"], val_cache["xemb"]])

    test_cache = load_cache("test")
    test_labels = load_labels("test")  # 116
    x_test = np.hstack([test_cache["x43"], test_cache["xemb"]])

    jbb_cache = load_cache("jbb")
    jbb_labels = load_labels("external_eval")  # 200
    x_jbb = np.hstack([jbb_cache["x43"], jbb_cache["xemb"]])

    print(
        "Validation: "
        f"{len(val_labels)} (mal={sum(val_labels)}, "
        f"ben={len(val_labels) - sum(val_labels)})"
    )
    print(
        "Test: "
        f"{len(test_labels)} (mal={sum(test_labels)}, "
        f"ben={len(test_labels) - sum(test_labels)})"
    )
    print(
        f"JBB: {len(jbb_labels)} (mal={sum(jbb_labels)}, ben={len(jbb_labels) - sum(jbb_labels)})"
    )

    # Get raw scores on all splits
    val_scores = get_provider_scores(components, x_val)
    test_scores = get_provider_scores(components, x_test)
    jbb_scores = get_provider_scores(components, x_jbb)

    # Focus on XGB and fusion (main models)
    providers_to_eval = ["xgboost", "fusion"]
    thresholds = [round(0.10 + i * 0.05, 2) for i in range(17)]  # 0.10..0.90

    results = {}

    for provider in providers_to_eval:
        results[provider] = {}
        val_s = val_scores[provider]
        test_s = test_scores[provider]
        jbb_s = jbb_scores[provider]

        # Raw threshold sweep on validation
        raw_sweep = {}
        for t in thresholds:
            m = metrics_at_threshold(val_labels, val_s, t)
            raw_sweep[f"t_{t:.2f}"] = {
                "precision": round(m["precision"], 4),
                "recall": round(m["recall"], 4),
                "f1": round(m["f1_score"], 4),
                "fpr": round(m["false_positive_rate"], 4),
                "fnr": round(m["false_negative_rate"], 4),
            }
        results[provider]["raw_sweep_val"] = raw_sweep

        # Calibration
        # Platt
        platt_oof = oof_calibrate(val_s, val_labels, "platt")
        platt_cal = fit_calibrator(val_s, val_labels, "platt")
        platt_test = apply_calibrator(platt_cal, test_s)
        platt_jbb = apply_calibrator(platt_cal, jbb_s)

        # Isotonic
        iso_oof = oof_calibrate(val_s, val_labels, "isotonic")
        iso_cal = fit_calibrator(val_s, val_labels, "isotonic")
        iso_test = apply_calibrator(iso_cal, test_s)
        iso_jbb = apply_calibrator(iso_cal, jbb_s)

        # Evaluate calibrated scores at threshold 0.5 and validation-optimal
        for name, test_cal, jbb_cal, val_oof in [
            ("raw", test_s, jbb_s, val_s),
            ("platt", platt_test, platt_jbb, platt_oof),
            ("isotonic", iso_test, iso_jbb, iso_oof),
        ]:
            results[provider][name] = {}

            # Validation OOF metrics
            for t in [0.50, 0.15, 0.20, 0.25]:
                m = metrics_at_threshold(val_labels, val_oof, t)
                results[provider][name][f"val_oof_t_{t:.2f}"] = {
                    "f1": round(m["f1_score"], 4),
                    "precision": round(m["precision"], 4),
                    "recall": round(m["recall"], 4),
                    "fpr": round(m["false_positive_rate"], 4),
                    "roc_auc": round(m["roc_auc"], 4),
                }

            # Test metrics at 0.5
            m = metrics_at_threshold(test_labels, test_cal, 0.50)
            results[provider][name]["test_t_0.50"] = {
                "f1": round(m["f1_score"], 4),
                "precision": round(m["precision"], 4),
                "recall": round(m["recall"], 4),
                "fpr": round(m["false_positive_rate"], 4),
                "roc_auc": round(m["roc_auc"], 4),
            }

            # JBB metrics at 0.5
            m = metrics_at_threshold(jbb_labels, jbb_cal, 0.50)
            results[provider][name]["jbb_t_0.50"] = {
                "f1": round(m["f1_score"], 4),
                "precision": round(m["precision"], 4),
                "recall": round(m["recall"], 4),
                "fpr": round(m["false_positive_rate"], 4),
                "roc_auc": round(m["roc_auc"], 4),
            }

        # Find validation-optimal threshold (max F1 on raw val)
        best_t = max(thresholds, key=lambda t: raw_sweep[f"t_{t:.2f}"]["f1"])
        results[provider]["val_optimal_threshold"] = best_t
        # Evaluate calibrated scores at this threshold on test/JBB
        for cal_name, test_cal2, jbb_cal2 in [
            ("raw", test_s, jbb_s),
            ("platt", platt_test, platt_jbb),
            ("isotonic", iso_test, iso_jbb),
        ]:
            m_test = metrics_at_threshold(test_labels, test_cal2, best_t)
            m_jbb = metrics_at_threshold(jbb_labels, jbb_cal2, best_t)
            results[provider][cal_name][f"val_opt_t_{best_t:.2f}_test"] = {
                "f1": round(m_test["f1_score"], 4),
                "precision": round(m_test["precision"], 4),
                "recall": round(m_test["recall"], 4),
                "fpr": round(m_test["false_positive_rate"], 4),
            }
            results[provider][cal_name][f"val_opt_t_{best_t:.2f}_jbb"] = {
                "f1": round(m_jbb["f1_score"], 4),
                "precision": round(m_jbb["precision"], 4),
                "recall": round(m_jbb["recall"], 4),
                "fpr": round(m_jbb["false_positive_rate"], 4),
            }

    # Save
    (OUT_DIR / "calibration_verification.json").write_text(json.dumps(results, indent=2))

    # Print summary
    print("\n=== VALIDATION THRESHOLD SWEEP (Raw XGB) ===")
    for t in thresholds:
        m = raw_sweep[f"t_{t:.2f}"]
        print(
            f"  t={t:.2f}: P={m['precision']:.3f} "
            f"R={m['recall']:.3f} F1={m['f1']:.3f} FPR={m['fpr']:.3f}"
        )

    print("\n=== CALIBRATION COMPARISON (XGB, JBB at t=0.50) ===")
    for name in ("raw", "platt", "isotonic"):
        m = results["xgboost"][name]["jbb_t_0.50"]
        print(
            f"  {name:8s}: F1={m['f1']:.3f} "
            f"P={m['precision']:.3f} R={m['recall']:.3f} "
            f"FPR={m['fpr']:.3f} AUC={m['roc_auc']:.3f}"
        )

    print("\n=== VALIDATION-OPTIMAL THRESHOLD TRANSFER TO JBB (XGB) ===")
    best_t = results["xgboost"]["val_optimal_threshold"]
    print(f"  Validation-optimal t={best_t:.2f}")
    for name in ("raw", "platt", "isotonic"):
        m = results["xgboost"][name][f"val_opt_t_{best_t:.2f}_jbb"]
        print(f"  {name:8s}: JBB F1={m['f1']:.3f} R={m['recall']:.3f} FPR={m['fpr']:.3f}")

    print(f"\nSaved to {OUT_DIR / 'calibration_verification.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
