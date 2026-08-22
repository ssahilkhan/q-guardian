"""Train the production arm_d diverse checkpoint (TASK: diverse retraining).

Trains the project's own ``HybridEvaluator`` stack (normalizer -> handcrafted
features -> semantic embedding -> StandardScaler -> IsolationForest ->
RandomForest -> XGBoost -> weighted fusion) on the arm_d diverse training set
(6269 samples: 4006 malicious / 2263 benign), then evaluates every classical
provider on validation / internal test / JBB external pools.

Frozen configuration (training-diversity experiment, plus validation-selected
Random-Forest estimator count):
- representation : 43 handcrafted + 384 all-MiniLM-L6-v2 embedding (427)
- Random Forest  : n_estimators=200 (validation-selected), random_state=42,
                   class_weight=None
- XGBoost        : n_estimators=50, max_depth=6, random_state=42
- scaling        : StandardScaler fitted on arm_d only
- threshold      : 0.5 (never tuned on JBB)

JBB (external_eval) is NEVER used for training, scaling, or model selection.

Outputs under artifacts/training_arm_d/:
    training_config.json   frozen hyperparameters + data provenance
    metadata.json          run metadata (git commit, timestamp, counts, seed)
    evaluation.json        per-pool / per-provider detection metrics
    model/                 hybrid_evaluator.joblib + params.json checkpoint
    verification.json      reload-from-disk re-evaluation results

Usage:
    python experiments/training_diversity/08_train_arm_d_checkpoint.py
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").CRITICAL)
)

from q_guardian.evaluation.metrics import detection_metrics
from q_guardian.evaluation.pipeline import HybridEvaluator

ROOT = Path(__file__).resolve().parent.parent.parent
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
ARM_D = ROOT / "experiments" / "training_diversity" / "train_sets" / "arm_d.jsonl"
OUT = ROOT / "artifacts" / "training_arm_d"

EVAL_POOLS = ("validation", "test", "jbb")
POOL_FILES = {
    "validation": SPLITS / "validation.jsonl",
    "test": SPLITS / "test.jsonl",
    "jbb": SPLITS / "external_eval.jsonl",
}

# Random-Forest estimator count selected by the controlled validation-only
# tuning run (09_tune_arm_d_rf.py -> artifacts/experiments/training_diversity/
# rf_tuning_results.json). XGBoost keeps its frozen configuration.
RF_N_ESTIMATORS = 200

TRAINING_CONFIG = {
    "representation": {
        "handcrafted_features": 43,
        "semantic_embedding": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_dim": 384,
        "total_features": 427,
        "scaling": "StandardScaler fitted on arm_d training data only",
    },
    "random_forest": {
        "n_estimators": RF_N_ESTIMATORS,
        "max_depth": None,
        "min_samples_split": 2,
        "min_samples_leaf": 1,
        "max_features": "sqrt",
        "class_weight": None,
        "random_state": 42,
        "tuning_provenance": (
            "n_estimators selected by validation-only grid "
            "(09_tune_arm_d_rf.py); JBB never used for selection"
        ),
    },
    "xgboost": {
        "n_estimators": 50,
        "max_depth": 6,
        "learning_rate": 0.3,
        "subsample": 1.0,
        "colsample_bytree": 1.0,
        "min_child_weight": 1,
        "gamma": 0,
        "reg_alpha": 0,
        "reg_lambda": 1,
        "scale_pos_weight": 1,
        "random_state": 42,
        "eval_metric": "mlogloss",
    },
    "isolation_forest": {"n_estimators": 50, "contamination": 0.2},
    "quantum": False,
    "fusion_weights": dict(HybridEvaluator().provider_weights),
    "threshold": 0.5,
    "seed": 42,
}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def pool_metrics(y_true: list[int], scores: list[float], threshold: float) -> dict:
    m = detection_metrics(y_true, scores, threshold=threshold)
    return {
        "samples": len(y_true),
        "positives": sum(y_true),
        "negatives": len(y_true) - sum(y_true),
        "roc_auc": round(m["roc_auc"], 4),
        "pr_auc": round(m["pr_auc"], 4),
        "accuracy": round(m["accuracy"], 4),
        "precision": round(m["precision"], 4),
        "recall": round(m["recall"], 4),
        "f1": round(m["f1_score"], 4),
        "fpr": round(m["false_positive_rate"], 4),
        "fnr": round(m["false_negative_rate"], 4),
        "confusion_matrix": {
            "tp": m["true_positives"],
            "fp": m["false_positives"],
            "tn": m["true_negatives"],
            "fn": m["false_negatives"],
        },
        "ece": round(m["expected_calibration_error"], 4),
        "brier": round(m["brier_score"], 4),
    }


def git_commit() -> str | None:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except Exception:
        return None


def main() -> None:
    t0 = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ data
    train_rows = load_jsonl(ARM_D)
    texts = [r["text"] for r in train_rows]
    labels = [int(r["label"]) for r in train_rows]
    assert len(texts) == len(labels), "arm_d text/label mismatch"
    print(f"[data] arm_d: {len(texts)} samples "
          f"({sum(labels)} malicious / {len(labels) - sum(labels)} benign)")

    pools = {name: load_jsonl(path) for name, path in POOL_FILES.items()}

    # --------------------------------------------------------------- training
    evaluator = HybridEvaluator(
        quantum=False,
        n_estimators=50,
        rf_n_estimators=RF_N_ESTIMATORS,
        use_semantic_embedding=True,
        random_state=42,
    )
    print("[train] fitting HybridEvaluator on arm_d (semantic features) ...")
    evaluator.fit(texts, labels)
    print(f"[train] fitted in {time.monotonic() - t0:.1f}s "
          f"(scaler dims={len(evaluator.scaler.mean_)})")

    # ------------------------------------------------------------- evaluation
    PROVIDER_ORDER = ("random-forest", "xgboost", "isolation-forest", "rule-engine", "fusion")
    evaluation: dict[str, dict] = {}
    for name, rows in pools.items():
        y = [int(r["label"]) for r in rows]
        result = evaluator.evaluate(_as_dataset(rows), threshold=0.5)
        evaluation[name] = {
            provider: pool_metrics(y, [m[provider] for m in result["scores"]], 0.5)
            for provider in PROVIDER_ORDER
            if provider in result
        }
        print(f"[eval] {name}: " + " | ".join(
            f"{p} auc={v['roc_auc']:.4f}" for p, v in evaluation[name].items()
        ))

    # ------------------------------------------------------------ persist all
    (OUT / "training_config.json").write_text(
        json.dumps({"training_data": "experiments/training_diversity/train_sets/arm_d.jsonl",
                    **TRAINING_CONFIG}, indent=2),
        encoding="utf-8",
    )

    assert evaluator.rf is not None and evaluator.xgb is not None, (
        "classical providers missing after fit (is xgboost installed?)"
    )
    xgb_model = evaluator.xgb._model
    rf_model = evaluator.rf._model
    source_counts = {
        src: sum(1 for r in train_rows if r.get("source") == src)
        for src in (
            "deepset-prompt-injections",
            "dolly-benign",
            "trustair-jailbreaks",
            "jailbreakv",
            "harmful-behaviors",
        )
    }
    metadata = {
        "run": "training_arm_d",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "model_type": (
            "HybridEvaluator (rule-engine + isolation-forest + "
            "random-forest + xgboost fusion)"
        ),
        "dataset": {
            "name": "arm_d (diverse)",
            "path": "experiments/training_diversity/train_sets/arm_d.jsonl",
            "samples": len(texts),
            "malicious": sum(labels),
            "benign": len(labels) - sum(labels),
            "sources": source_counts,
        },
        "feature_version": "handcrafted-43+minilm384@all-MiniLM-L6-v2",
        "n_features": len(evaluator.scaler.mean_),
        "random_seed": 42,
        "calibration": "none",
        "threshold": 0.5,
        "hyperparameters": TRAINING_CONFIG,
        "trained_models": {
            "xgboost": {"n_estimators": int(xgb_model.n_estimators)},
            "random_forest": {
                "n_estimators": int(rf_model.n_estimators),
                "tuning_provenance": (
                    "artifacts/experiments/training_diversity/rf_tuning_results.json "
                    "(validation-only selection)"
                ),
            },
        },
    }
    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (OUT / "evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")

    ckpt_dir = evaluator.save_state(OUT / "model")
    print(f"[save] checkpoint written to {ckpt_dir}")

    # ----------------------------------------------------- reload verification
    print("[verify] reloading checkpoint from disk ...")
    reloaded = HybridEvaluator.load_state(OUT / "model")
    verification: dict[str, dict] = {
        "checkpoint_dir": str(OUT / "model"),
        "params": json.loads((OUT / "model" / "params.json").read_text(encoding="utf-8")),
        "pools": {},
    }
    all_match = True
    for name in ("validation", "test", "jbb"):
        rows = pools[name]
        y = [int(r["label"]) for r in rows]
        result = reloaded.evaluate(_as_dataset(rows), threshold=0.5)
        verification["pools"][name] = {}
        for provider in ("random-forest", "xgboost"):
            s_prov = [row[provider] for row in result["scores"]]
            m_re = pool_metrics(y, s_prov, 0.5)
            match = m_re["roc_auc"] == evaluation[name][provider]["roc_auc"]
            all_match = all_match and match
            verification["pools"][name][provider] = {
                "roc_auc_reloaded": m_re["roc_auc"],
                "pr_auc_reloaded": m_re["pr_auc"],
                "f1_reloaded": m_re["f1"],
                "roc_auc_trained": evaluation[name][provider]["roc_auc"],
                "match": match,
            }
        fused_auc = pool_metrics(y, reloaded.score_texts([r["text"] for r in rows]), 0.5)
        verification["pools"][name]["fusion_score_texts_roc_auc"] = fused_auc["roc_auc"]
    verification["all_match"] = all_match
    (OUT / "verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    print(f"[verify] reload AUC match: {'OK' if all_match else 'MISMATCH'}")
    print(f"[done] total {time.monotonic() - t0:.1f}s")


def _as_dataset(rows: list[dict]):
    from q_guardian.evaluation.dataset import BenchmarkSample, PromptBenchmarkDataset

    return PromptBenchmarkDataset(
        [
            BenchmarkSample(
                text=r["text"],
                label=int(r["label"]),
                category=str(r.get("category") or "benign"),
            )
            for r in rows
        ]
    )


if __name__ == "__main__":
    main()
