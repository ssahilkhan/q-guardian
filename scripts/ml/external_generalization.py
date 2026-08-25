"""External generalization evaluation using cached features directly.

Loads the arm_d joblib checkpoint, extracts raw models + scaler,
scores using pre-computed cached features (x43 + xemb).
No sentence-transformers/torch needed at inference time.
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
OUT_DIR = ROOT / "artifacts" / "experiments" / "external_generalization"
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
        "anomaly": state["anomaly"],  # IsolationForestDetector
        "rf": state["rf"],  # RandomForestThreatClassifier
        "xgb": state["xgb"],  # XGBoostThreatClassifier
        "qsvm": state.get("qsvm"),  # None (quantum=False)
    }


def get_provider_scores(components, x: np.ndarray) -> dict[str, list[float]]:
    """Get scores from each provider using cached features."""
    scaler = components["scaler"]
    x_scaled = scaler.transform(x)

    scores = {}

    # Rule engine: need to compute rule scores separately
    # For now, skip rule engine (requires PromptNormalizer + RuleEngine)
    # We'll score classical models only

    # Isolation Forest: decision_function (higher = more normal, so negate)
    anomaly = components["anomaly"]
    if anomaly and anomaly._model is not None:
        # anomaly.detect() returns anomaly score; we need raw decision_function
        # The model has decision_function method
        if_decision = -anomaly._model.decision_function(x_scaled)  # higher = more anomaly
        # Normalize to [0,1] roughly via sigmoid-like scaling
        from sklearn.preprocessing import MinMaxScaler

        scores["isolation-forest"] = (
            MinMaxScaler().fit_transform(if_decision.reshape(-1, 1)).flatten().tolist()
        )

    # RandomForest: predict_proba[:, 1]
    rf = components["rf"]
    if rf and rf._model is not None:
        rf_proba = rf._model.predict_proba(x_scaled)[:, 1]
        scores["random-forest"] = rf_proba.tolist()

    # XGBoost: predict_proba[:, 1]
    xgb = components["xgb"]
    if xgb and xgb._model is not None:
        xgb_proba = xgb._model.predict_proba(np.asarray(x_scaled, dtype=np.float32))[:, 1]
        scores["xgboost"] = xgb_proba.tolist()

    # Fusion: weighted average of available providers
    # Use same weights as arm_d params
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


def metrics_at_threshold(y_true: list[int], scores: list[float], t: float) -> dict:
    from q_guardian.evaluation.metrics import detection_metrics

    return detection_metrics(y_true, scores, threshold=t)


def main() -> int:
    print("Loading arm_d components from checkpoint...")
    components = load_arm_d_components()
    print(f"Params: use_semantic_embedding={components['params']['use_semantic_embedding']}")
    print(
        "Models: "
        f"anomaly={components['anomaly'] is not None}, "
        f"rf={components['rf'] is not None}, "
        f"xgb={components['xgb'] is not None}"
    )

    # Load internal test split (cached)
    print("Loading test split...")
    test_cache = load_cache("test")
    test_labels = load_labels("test")  # 116 samples
    x_test = np.hstack([test_cache["x43"], test_cache["xemb"]])

    # Load JBB external eval (cached)
    print("Loading JBB external eval...")
    jbb_cache = load_cache("jbb")
    jbb_labels = load_labels("external_eval")  # 200 samples
    x_jbb = np.hstack([jbb_cache["x43"], jbb_cache["xemb"]])

    # Get per-provider scores + fusion
    print("Scoring test split...")
    test_scores = get_provider_scores(components, x_test)

    print("Scoring JBB external...")
    jbb_scores = get_provider_scores(components, x_jbb)

    # Evaluation at multiple thresholds
    thresholds = [0.50, 0.20, 0.15, 0.10]
    results = {}

    for pool_name, pool_scores, pool_labels in [
        ("test", test_scores, test_labels),
        ("jbb", jbb_scores, jbb_labels),
    ]:
        results[pool_name] = {}
        for provider in pool_scores:
            results[pool_name][provider] = {}
            for t in thresholds:
                m = metrics_at_threshold(pool_labels, pool_scores[provider], t)
                results[pool_name][provider][f"t_{t:.2f}"] = {
                    "f1": round(m["f1_score"], 4),
                    "precision": round(m["precision"], 4),
                    "recall": round(m["recall"], 4),
                    "fpr": round(m["false_positive_rate"], 4),
                    "roc_auc": round(m["roc_auc"], 4),
                    "pr_auc": round(m["pr_auc"], 4),
                }

    # Macro/worst-case across pools
    macro_results = {}
    for provider in test_scores:
        macro_results[provider] = {}
        for t in thresholds:
            f1s = [
                results[p][provider][f"t_{t:.2f}"]["f1"]
                for p in ("test", "jbb")
                if provider in results[p]
            ]
            macro_results[provider][f"t_{t:.2f}"] = {
                "macro_f1": round(np.mean(f1s), 4) if f1s else None,
                "worst_f1": round(min(f1s), 4) if f1s else None,
            }

    # Save
    out = {
        "evaluator": "arm_d",
        "feature_contract": "extended-427",
        "pools": results,
        "macro_worst": macro_results,
    }
    (OUT_DIR / "external_generalization.json").write_text(json.dumps(out, indent=2))

    # Print summary table
    print("\n=== EXTERNAL GENERALIZATION SUMMARY (fusion scores) ===")
    for pool in ("test", "jbb"):
        print(f"\n{pool.upper()} (n={len(eval(f'{pool}_labels'))})")
        for t in thresholds:
            tkey = f"t_{t:.2f}"
            if "fusion" in results[pool]:
                m = results[pool]["fusion"][tkey]
                print(
                    f"  t={t:.2f}: F1={m['f1']:.3f} "
                    f"P={m['precision']:.3f} R={m['recall']:.3f} "
                    f"FPR={m['fpr']:.3f} ROC-AUC={m['roc_auc']:.3f}"
                )

    print("\n=== MACRO / WORST-CASE (fusion) ===")
    for t in thresholds:
        tkey = f"t_{t:.2f}"
        m = macro_results.get("fusion", {}).get(tkey, {})
        if m:
            print(f"  t={t:.2f}: macro_F1={m.get('macro_f1')} worst_F1={m.get('worst_f1')}")

    print(f"\nSaved to {OUT_DIR / 'external_generalization.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
