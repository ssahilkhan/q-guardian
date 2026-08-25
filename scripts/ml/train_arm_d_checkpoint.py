"""Train arm_d models from cached features and save HybridEvaluator checkpoint.

Reproduces the arm_d training-diversity experiment deterministically:
- Uses cached x43 (43-dim) + xemb (384-dim) = 427-dim features
- Same hyperparams and seed as original training-diversity run
- Saves HybridEvaluator with rule + IF + RF + XGB to artifacts/training_arm_d/
- Feature contract metadata stamped on each model for self-documenting load

Usage:
    python -m scripts.ml.train_arm_d_checkpoint
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").CRITICAL)
)

ROOT = Path(__file__).resolve().parents[2]
DIV_CACHE = ROOT / "artifacts" / "experiments" / "training_diversity" / "cache"
ARM_D_JSONL = ROOT / "experiments" / "training_diversity" / "train_sets" / "arm_d.jsonl"
OUT_DIR = ROOT / "artifacts" / "training_arm_d"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Same params as training-diversity experiment
XGB_PARAMS = dict(
    n_estimators=50,
    max_depth=6,
    random_state=42,
    use_label_encoder=False,
    eval_metric="mlogloss",
    verbosity=0,
)
RF_PARAMS = dict(n_estimators=50, random_state=42, class_weight=None)
IF_PARAMS = dict(n_estimators=200, contamination=0.1, random_state=42)

# HybridEvaluator params matching arm_d training
HE_PARAMS = {
    "quantum": False,
    "quantum_shots": 128,
    "quantum_feature_count": 5,
    "quantum_cap": None,
    "n_estimators": 50,
    "rf_n_estimators": 50,
    "xgb_n_estimators": 50,
    "contamination": 0.1,
    "provider_weights": {
        "rule-engine": 0.15,
        "isolation-forest": 0.10,
        "random-forest": 0.35,
        "xgboost": 0.25,
        "qsvm": 0.15,
    },
    "random_state": 42,
    "use_semantic_embedding": True,
    "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
}


def load_cache(name: str) -> dict:
    d = np.load(DIV_CACHE / f"{name}.npz", allow_pickle=True)
    return {
        "texts": [str(t) for t in d["texts"].tolist()],
        "x43": d["x43"].astype(np.float64),
        "xemb": d["xemb"].astype(np.float64),
    }


def load_arm_d_labels() -> list[int]:
    rows = []
    with open(ARM_D_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return [r["label"] for r in rows]


def main() -> int:
    print("Loading arm_d cache...")
    arm_d_cache = load_cache("arm_d")
    y = load_arm_d_labels()
    X43 = arm_d_cache["x43"]
    Xemb = arm_d_cache["xemb"]
    X = np.hstack([X43, Xemb]).astype(np.float64)  # 427-dim

    print(f"arm_d: {len(y)} samples, {X.shape[1]} features (43+384)")
    print(f"Labels: malicious={sum(y)}, benign={len(y) - sum(y)}")

    # Fit scaler (HybridEvaluator uses StandardScaler)
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    scaler.fit(X)
    X_scaled = scaler.transform(X).tolist()

    # Train IsolationForestDetector (uses IsolationForest internally)
    print("Training IsolationForestDetector...")
    from q_guardian.ml.models.anomaly import IsolationForestDetector

    anomaly = IsolationForestDetector(
        n_estimators=IF_PARAMS["n_estimators"],
        contamination=IF_PARAMS["contamination"],
    )
    anomaly.train(X_scaled)
    # Stamp metadata
    anomaly.metadata.metadata["feature_contract"] = "extended-427"
    anomaly.metadata.metadata["training_arm"] = "arm_d"
    anomaly.metadata.metadata["trained_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Train RandomForestThreatClassifier
    print("Training RandomForestThreatClassifier...")
    from q_guardian.ml.models.classifier import RandomForestThreatClassifier

    rf = RandomForestThreatClassifier(n_estimators=RF_PARAMS["n_estimators"])
    rf.train(X_scaled, y)
    rf.metadata.metadata["feature_contract"] = "extended-427"
    rf.metadata.metadata["training_arm"] = "arm_d"
    rf.metadata.metadata["trained_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Train XGBoostThreatClassifier
    print("Training XGBoostThreatClassifier...")
    from q_guardian.ml.models.classifier import XGBoostThreatClassifier

    xgb_clf = XGBoostThreatClassifier(n_estimators=XGB_PARAMS["n_estimators"])
    if xgb_clf.is_available:
        xgb_clf.train(np.asarray(X_scaled, dtype=np.float32), np.asarray(y, dtype=np.int32))
        xgb_clf.metadata.metadata["feature_contract"] = "extended-427"
        xgb_clf.metadata.metadata["training_arm"] = "arm_d"
        xgb_clf.metadata.metadata["trained_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    else:
        xgb_clf = None
        print("  XGBoost unavailable, skipping")

    # Build HybridEvaluator with arm_d params and inject trained components
    from q_guardian.evaluation.pipeline import HybridEvaluator

    evaluator = HybridEvaluator(**HE_PARAMS)
    evaluator.scaler = scaler
    evaluator.anomaly = anomaly
    evaluator.rf = rf
    evaluator.xgb = xgb_clf
    evaluator.qsvm = None  # quantum=False

    # Build providers (wraps the trained components)
    evaluator._setup_providers()

    # Save checkpoint
    evaluator.save_state(str(OUT_DIR))
    print(f"Saved HybridEvaluator checkpoint to {OUT_DIR}")

    # Quick self-test: load and score a few samples
    print("Self-test: loading checkpoint and scoring arm_d...")
    evaluator2 = HybridEvaluator.load_state(str(OUT_DIR))
    scores = []
    for i in range(min(10, len(X))):
        # _score_one takes (text, fusion), not the raw vector
        # Instead, use score_texts which calls _score_one internally
        pass
    # Just test score_texts on first 10 texts
    test_texts = arm_d_cache["texts"][:10]
    scores = evaluator2.score_texts(test_texts)
    print(f"Sample fusion scores: {[round(s, 4) for s in scores]}")

    # Verify feature contract on loaded models
    for pid in ("isolation-forest", "random-forest", "xgboost"):
        provider = evaluator2._providers.get(pid)
        if provider and hasattr(provider[0], "model") and hasattr(provider[0].model, "metadata"):
            print(f"  {pid}: feature_contract={provider[0].model.metadata.get('feature_contract')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
