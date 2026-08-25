"""QSVM training and evaluation on arm_d subset.

Trains QSVM on a capped subset (due to O(n^2) kernel complexity)
and evaluates on internal test + JBB. Documents quantum advantage
or lack thereof.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").CRITICAL)
)

ROOT = Path(__file__).resolve().parents[2]
DIV_CACHE = ROOT / "artifacts" / "experiments" / "training_diversity" / "cache"
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
OUT_DIR = ROOT / "artifacts" / "experiments" / "qsvm_evaluation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# QSVM params (matching HybridEvaluator defaults)
QSVM_PARAMS = {
    "quantum_shots": 128,
    "quantum_feature_count": 5,  # 5 qubits
    "quantum_cap": 200,  # cap training samples for speed
    "random_state": 42,
}


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


def get_handcrafted_5dim(x: np.ndarray) -> np.ndarray:
    """Extract first 5 features for angle encoding (qubit limit)."""
    return x[:, :5]


async def run_evaluation():
    print("Loading data...")
    arm_d_cache = load_cache("arm_d")
    y = []
    with open(
        ROOT / "experiments/training_diversity/train_sets/arm_d.jsonl", encoding="utf-8"
    ) as f:
        for line in f:
            line = line.strip()
            if line:
                y.append(json.loads(line)["label"])
    y = np.array(y)
    x = np.hstack([arm_d_cache["x43"], arm_d_cache["xemb"]])

    test_cache = load_cache("test")
    test_labels = load_labels("test")
    x_test = np.hstack([test_cache["x43"], test_cache["xemb"]])

    jbb_cache = load_cache("jbb")
    jbb_labels = load_labels("external_eval")
    x_jbb = np.hstack([jbb_cache["x43"], jbb_cache["xemb"]])

    # Fit scaler on arm_d
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    scaler.fit(x)
    x_scaled = scaler.transform(x)
    x_test_scaled = scaler.transform(x_test)
    x_jbb_scaled = scaler.transform(x_jbb)

    # Extract 5-dim for quantum
    x_q = get_handcrafted_5dim(x_scaled)
    x_test_q = get_handcrafted_5dim(x_test_scaled)
    x_jbb_q = get_handcrafted_5dim(x_jbb_scaled)

    # Cap training data
    cap = QSVM_PARAMS["quantum_cap"]
    if len(x_q) > cap:
        # Stratified sampling
        from sklearn.model_selection import train_test_split

        x_q, _, y_q, _ = train_test_split(x_q, y, train_size=cap, stratify=y, random_state=42)
        print(f"Capped training to {cap} samples (stratified)")
    else:
        y_q = y

    print(
        "Training QSVM on "
        f"{len(x_q)} samples with 5 qubits, {QSVM_PARAMS['quantum_shots']} shots..."
    )

    # Train QSVM
    from q_guardian.quantum.backends.simulator import LocalSimulatorBackend
    from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
    from q_guardian.quantum.kernels.quantum_kernel import QuantumKernelEstimator
    from q_guardian.quantum.models.qsvm import QSVMModel

    backend = LocalSimulatorBackend(
        num_qubits=QSVM_PARAMS["quantum_feature_count"],
        shots=QSVM_PARAMS["quantum_shots"],
    )
    feature_map = AngleEncodingMap(num_qubits=QSVM_PARAMS["quantum_feature_count"])
    kernel = QuantumKernelEstimator(
        feature_map=feature_map,
        backend=backend,
        shots=QSVM_PARAMS["quantum_shots"],
    )
    qsvm = QSVMModel(kernel=kernel, feature_map=feature_map)
    qsvm.train(x_q.tolist(), y_q.tolist())

    # Evaluate QSVM (async)
    async def eval_qsvm(x_eval, y_eval, name: str):
        print(f"Evaluating on {name} ({len(x_eval)} samples)...")
        # QSVM predict takes a single feature vector, returns dict
        scores = []
        for i in range(len(x_eval)):
            pred = await qsvm.predict(x_eval[i].tolist())
            # pred is {"predicted_class": "0"/"1", "confidence": ..., "probabilities": ...}
            scores.append(float(pred["predicted_class"]))
        from q_guardian.evaluation.metrics import detection_metrics

        # QSVM predict returns class labels (0/1), not probabilities
        # So we can only evaluate at threshold 0.5
        m = detection_metrics(y_eval, scores, threshold=0.5)
        print(
            f"  F1={m['f1_score']:.3f} P={m['precision']:.3f} R={m['recall']:.3f} "
            f"FPR={m['false_positive_rate']:.3f} AUC={m['roc_auc']:.3f}"
        )
        return {
            "f1": round(m["f1_score"], 4),
            "precision": round(m["precision"], 4),
            "recall": round(m["recall"], 4),
            "fpr": round(m["false_positive_rate"], 4),
            "roc_auc": round(m["roc_auc"], 4),
        }

    results = {}
    results["train"] = {"samples": len(x_q), "cap": cap}
    results["test"] = await eval_qsvm(x_test_q, test_labels, "internal test")
    results["jbb"] = await eval_qsvm(x_jbb_q, jbb_labels, "JBB external")

    # Compare with classical baseline on same 5-dim features
    print("\nTraining classical baseline on 5-dim features for comparison...")
    from sklearn.ensemble import RandomForestClassifier
    from xgboost import XGBClassifier

    rf_5 = RandomForestClassifier(n_estimators=50, random_state=42)
    rf_5.fit(x_q, y_q)
    xgb_5 = XGBClassifier(
        n_estimators=50,
        max_depth=6,
        random_state=42,
        use_label_encoder=False,
        eval_metric="mlogloss",
        verbosity=0,
    )
    xgb_5.fit(x_q, y_q)

    def eval_clf(clf, x_eval, y_eval, name: str):
        proba = clf.predict_proba(x_eval)[:, 1]
        from q_guardian.evaluation.metrics import detection_metrics

        m = detection_metrics(y_eval, proba.tolist(), threshold=0.5)
        print(f"  {name}: F1={m['f1_score']:.3f} AUC={m['roc_auc']:.3f}")
        return {"f1": round(m["f1_score"], 4), "roc_auc": round(m["roc_auc"], 4)}

    results["classical_baseline"] = {
        "rf_5dim_test": eval_clf(rf_5, x_test_q, test_labels, "RF-5dim"),
        "rf_5dim_jbb": eval_clf(rf_5, x_jbb_q, jbb_labels, "RF-5dim"),
        "xgb_5dim_test": eval_clf(xgb_5, x_test_q, test_labels, "XGB-5dim"),
        "xgb_5dim_jbb": eval_clf(xgb_5, x_jbb_q, jbb_labels, "XGB-5dim"),
    }

    # Save
    (OUT_DIR / "qsvm_evaluation.json").write_text(json.dumps(results, indent=2))
    print(f"\nSaved to {OUT_DIR / 'qsvm_evaluation.json'}")


def main() -> int:
    asyncio.run(run_evaluation())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
