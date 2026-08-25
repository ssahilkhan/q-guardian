"""Capture the PRODUCTION baseline record for the generalization experiment.

Loads the existing trained HybridEvaluator checkpoint (artifacts/training_xgboost_fix/model),
which is the strongest available production model (fusion incl. XGBoost provider), and
evaluates every control split pool at the production threshold 0.5. This preserves a
reference baseline that later experiment conditions are compared against.

Read-only: never modifies the checkpoint, splits, configs, or version. Output:
artifacts/training/generalization_experiment/baseline.json
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import structlog

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

from q_guardian.evaluation.dataset import BenchmarkSample, PromptBenchmarkDataset
from q_guardian.evaluation.pipeline import HybridEvaluator

ROOT = Path(__file__).resolve().parent.parent.parent
RUN = ROOT / "artifacts" / "training_xgboost_fix"
OUT = ROOT / "artifacts" / "training" / "generalization_experiment"

PROVIDERS = ("fusion", "rule-engine", "isolation-forest", "random-forest", "xgboost", "qsvm")


def load_split(name: str) -> PromptBenchmarkDataset:
    rows = []
    with open(RUN / "splits" / f"{name}.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append(
                BenchmarkSample(text=r["text"], label=r["label"], category=r.get("category", ""))
            )
    return PromptBenchmarkDataset(rows)


def summarize(m: dict) -> dict:
    return {
        "roc_auc": round(m["roc_auc"], 4),
        "pr_auc": round(m["pr_auc"], 4),
        "f1": round(m["f1_score"], 4),
        "accuracy": round(m["accuracy"], 4),
        "precision": round(m["precision"], 4),
        "recall": round(m["recall"], 4),
        "detection_rate": round(m["recall"], 4),
        "benign_rejection_rate": round(m["specificity"], 4),
        "fpr": round(m["false_positive_rate"], 4),
        "fnr": round(m["false_negative_rate"], 4),
    }


def main() -> None:
    evaluator = HybridEvaluator.load_state(RUN / "model")
    params = json.loads((RUN / "model" / "params.json").read_text(encoding="utf-8"))
    training_cfg = json.loads((ROOT / "configs" / "training.json").read_text(encoding="utf-8"))

    pools = {
        "train": load_split("train"),
        "validation": load_split("validation"),
        "test": load_split("test"),
        "jbb_external_eval": load_split("external_eval"),
    }

    record: dict = {
        "model": {
            "type": "HybridEvaluator (production checkpoint)",
            "checkpoint_dir": RUN.as_posix(),
            "providers": evaluator.provider_ids(),
            "quantum": evaluator.quantum,
            "params": params,
            "training_config": training_cfg,
        },
        "evaluation": {
            "threshold": 0.5,
            "method": "HybridEvaluator.evaluate(ds, threshold=0.5); fusion + per-provider metrics",
            "provenance": "production model from artifacts/training_xgboost_fix (strongest baseline; fusion incl. XGBoost provider)",
            "captured_utc": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "splits": {
            name: {
                "samples": len(ds),
                "malicious": ds.positives(),
                "benign": ds.negatives(),
            }
            for name, ds in pools.items()
        },
        "metrics": {},
    }

    for name, ds in pools.items():
        result = evaluator.evaluate(ds, threshold=0.5)
        record["metrics"][name] = {}
        for pid in PROVIDERS:
            if pid not in result:
                continue
            record["metrics"][name][pid] = summarize(result[pid])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "baseline.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    print("baseline captured:")
    for name, m in record["metrics"].items():
        f = m.get("fusion", {})
        rf = m.get("random-forest", {})
        print(
            f"  {name:<18} fusion roc_auc={f.get('roc_auc', float('nan')):.4f} "
            f"f1={f.get('f1', float('nan')):.4f} det={f.get('detection_rate', float('nan')):.4f} "
            f"fpr={f.get('fpr', float('nan')):.4f} | rf roc_auc={rf.get('roc_auc', float('nan')):.4f}"
        )


if __name__ == "__main__":
    main()
