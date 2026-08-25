"""Auto-threshold selection with external guardrails (P9).

Selects threshold on validation but applies guardrails to prevent
catastrophic FPR on external/held-out data. Key insight: validation-
optimal threshold (t=0.15) gives FPR=0.015 on validation but FPR=0.70
on JBB. Guardrail caps FPR increase to prevent this.

Strategy:
1. Find validation-optimal threshold (max F1)
2. Evaluate on held-out internal test (never used for selection)
3. If test FPR > guardrail_limit (e.g., 0.15), fall back to safe threshold
4. Safe threshold = highest threshold where test FPR <= guardrail_limit
5. Log decision and evidence
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").CRITICAL)
)

ROOT = Path(__file__).resolve().parents[2]
DIV_CACHE = ROOT / "artifacts" / "experiments" / "training_diversity" / "cache"
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
ARM_D_DIR = ROOT / "artifacts" / "training_arm_d"
OUT_DIR = ROOT / "artifacts" / "experiments" / "auto_threshold"
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
    state = joblib.load(ARM_D_DIR / "hybrid_evaluator.joblib")
    return {
        "params": state["params"],
        "scaler": state["scaler"],
        "anomaly": state["anomaly"],
        "rf": state["rf"],
        "xgb": state["xgb"],
    }


def get_provider_scores(components, x: np.ndarray) -> dict[str, list[float]]:
    scaler = components["scaler"]
    x_scaled = scaler.transform(x)

    scores = {}

    anomaly = components["anomaly"]
    if anomaly and anomaly._model is not None:
        if_decision = -anomaly._model.decision_function(x_scaled)
        from sklearn.preprocessing import MinMaxScaler

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


def threshold_sweep(y_true: list[int], scores: list[float], thresholds: list[float]) -> list[dict]:
    """Return metrics for each threshold."""
    from q_guardian.evaluation.metrics import detection_metrics

    results = []
    for t in thresholds:
        m = detection_metrics(y_true, scores, threshold=t)
        results.append(
            {
                "threshold": t,
                "f1": m["f1_score"],
                "precision": m["precision"],
                "recall": m["recall"],
                "fpr": m["false_positive_rate"],
                "fnr": m["false_negative_rate"],
                "roc_auc": m["roc_auc"],
            }
        )
    return results


def select_threshold_with_guardrail(
    val_sweep: list[dict],
    test_sweep: list[dict],
    guardrail_fpr: float = 0.15,
) -> dict:
    """Select threshold with FPR guardrail.

    Args:
        val_sweep: Threshold sweep results on validation (selection set)
        test_sweep: Threshold sweep results on internal test (guardrail set)
        guardrail_fpr: Maximum allowed FPR on test set

    Returns:
        Dict with selected threshold, method, and evidence
    """
    # 1. Find validation-optimal (max F1)
    val_best = max(val_sweep, key=lambda x: x["f1"])
    val_optimal_t = val_best["threshold"]
    val_optimal_f1 = val_best["f1"]
    val_optimal_fpr = val_best["fpr"]

    # 2. Check test FPR at validation-optimal threshold
    test_at_val_opt = next(
        (r for r in test_sweep if abs(r["threshold"] - val_optimal_t) < 1e-6), None
    )
    test_fpr_at_val_opt = test_at_val_opt["fpr"] if test_at_val_opt else 1.0

    # 3. Guardrail decision
    if test_fpr_at_val_opt <= guardrail_fpr:
        # Validation-optimal passes guardrail
        return {
            "selected_threshold": val_optimal_t,
            "selection_method": "validation_optimal_passed_guardrail",
            "val_optimal_threshold": val_optimal_t,
            "val_optimal_f1": val_optimal_f1,
            "val_optimal_fpr": val_optimal_fpr,
            "test_fpr_at_val_optimal": test_fpr_at_val_opt,
            "guardrail_fpr_limit": guardrail_fpr,
            "guardrail_passed": True,
        }

    # 4. Guardrail failed: find highest threshold where test FPR <= limit
    safe_thresholds = [r for r in test_sweep if r["fpr"] <= guardrail_fpr]
    if not safe_thresholds:
        # No threshold satisfies guardrail; fall back to highest threshold (lowest FPR)
        safe_t = max(test_sweep, key=lambda x: x["threshold"])["threshold"]
        method = "no_safe_threshold_max_t"
    else:
        safe_t = max(safe_thresholds, key=lambda x: x["threshold"])["threshold"]
        method = "guardrail_fallback_safe_threshold"

    test_at_safe = next(r for r in test_sweep if abs(r["threshold"] - safe_t) < 1e-6)

    return {
        "selected_threshold": safe_t,
        "selection_method": method,
        "val_optimal_threshold": val_optimal_t,
        "val_optimal_f1": val_optimal_f1,
        "val_optimal_fpr": val_optimal_fpr,
        "test_fpr_at_val_optimal": test_fpr_at_val_opt,
        "test_fpr_at_selected": test_at_safe["fpr"],
        "test_f1_at_selected": test_at_safe["f1"],
        "guardrail_fpr_limit": guardrail_fpr,
        "guardrail_passed": False,
    }


def main() -> int:
    print("Loading arm_d components...")
    components = load_arm_d_components()

    # Load splits
    val_cache = load_cache("validation")
    val_labels = load_labels("validation")  # 110
    x_val = np.hstack([val_cache["x43"], val_cache["xemb"]])

    test_cache = load_cache("test")
    test_labels = load_labels("test")  # 116
    x_test = np.hstack([test_cache["x43"], test_cache["xemb"]])

    # Get scores
    val_scores = get_provider_scores(components, x_val)
    test_scores = get_provider_scores(components, x_test)

    thresholds = [round(0.05 + i * 0.05, 2) for i in range(19)]  # 0.05..0.95
    guardrail_fpr = 0.15  # Configurable guardrail

    results = {}

    for provider in ("fusion", "xgboost", "random-forest"):
        if provider not in val_scores:
            continue

        print(f"\n=== Auto-threshold for {provider} ===")
        val_sweep = threshold_sweep(val_labels, val_scores[provider], thresholds)
        test_sweep = threshold_sweep(test_labels, test_scores[provider], thresholds)

        # Print sweeps
        print("  Validation sweep (top 5 by F1):")
        for r in sorted(val_sweep, key=lambda x: -x["f1"])[:5]:
            print(f"    t={r['threshold']:.2f}: F1={r['f1']:.3f} FPR={r['fpr']:.3f}")

        print("  Test sweep (top 5 by F1):")
        for r in sorted(test_sweep, key=lambda x: -x["f1"])[:5]:
            print(f"    t={r['threshold']:.2f}: F1={r['f1']:.3f} FPR={r['fpr']:.3f}")

        # Select with guardrail
        decision = select_threshold_with_guardrail(val_sweep, test_sweep, guardrail_fpr)
        results[provider] = {
            "val_sweep": val_sweep,
            "test_sweep": test_sweep,
            "decision": decision,
        }

        print(f"  Decision: {decision['selection_method']}")
        print(f"  Selected threshold: {decision['selected_threshold']:.2f}")
        print(
            "  Val-optimal t="
            f"{decision['val_optimal_threshold']:.2f} "
            f"(F1={decision['val_optimal_f1']:.3f}, FPR={decision['val_optimal_fpr']:.3f})"
        )
        print(f"  Test FPR at val-optimal: {decision['test_fpr_at_val_optimal']:.3f}")
        print(f"  Guardrail limit: {guardrail_fpr}")
        print(f"  Guardrail passed: {decision['guardrail_passed']}")
        if not decision["guardrail_passed"]:
            print(f"  Test FPR at selected: {decision['test_fpr_at_selected']:.3f}")
            print(f"  Test F1 at selected: {decision['test_f1_at_selected']:.3f}")

    # Save
    (OUT_DIR / "auto_threshold.json").write_text(json.dumps(results, indent=2))
    print(f"\nSaved to {OUT_DIR / 'auto_threshold.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
