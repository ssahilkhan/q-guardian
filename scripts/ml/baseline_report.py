"""Reproducible ML baseline report for the Q-Guardian hybrid pipeline.

Loads a trained ``HybridEvaluator`` checkpoint and evaluates it on the
frozen internal splits plus every available external evaluation pool,
writing machine-readable artifacts under ``reports/ml_baseline/``.

Protocol
--------
* Scores are computed once per pool; threshold-based metrics are derived
  from the continuous scores so sweeps cost nothing extra.
* Threshold selection evidence is reported for the VALIDATION split only.
  External pools are never used to select thresholds.
* Every run is written to ``runs/<utc_timestamp>_git<commit>/`` and then
  summarized at the top level so previous runs are preserved.

Usage::

    python -m scripts.ml.baseline_report [--checkpoint DIR] [--splits-dir DIR]
                                         [--out DIR]

Outputs::

    reports/ml_baseline/runs/<id>/baseline_metrics.json
    reports/ml_baseline/runs/<id>/dataset_manifest.json
    reports/ml_baseline/baseline_metrics.json        (copy of latest)
    reports/ml_baseline/dataset_manifest.json        (copy of latest)
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import structlog  # noqa: E402

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(30))

from q_guardian.evaluation.dataset import PromptBenchmarkDataset  # noqa: E402
from q_guardian.evaluation.metrics import detection_metrics  # noqa: E402
from q_guardian.evaluation.pipeline import HybridEvaluator  # noqa: E402

SEED = 42
DEFAULT_CHECKPOINT = ROOT / "artifacts" / "training_xgboost_fix" / "model"
DEFAULT_SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
DEFAULT_OUT = ROOT / "reports" / "ml_baseline"

# Pool name -> split file. ``external_eval`` is the held-out JBB set;
# it must never be used for training or threshold selection.
POOL_FILES = {
    "validation": "validation.jsonl",
    "test": "test.jsonl",
    "external_jbb": "external_eval.jsonl",
}

THRESHOLD_SWEEP = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    except Exception:
        return "unknown"


def load_pool(path: Path) -> PromptBenchmarkDataset:
    return PromptBenchmarkDataset.from_jsonl(path)


def score_pool(
    evaluator: HybridEvaluator,
    dataset: PromptBenchmarkDataset,
) -> tuple[dict[str, list[float]], dict[str, float]]:
    """Score a pool once; return ({provider: scores}, latency stats seconds)."""
    texts = dataset.texts()
    fusion = evaluator._build_fusion(include_providers=None)

    import asyncio

    async def _timed() -> tuple[list[dict[str, float]], list[float]]:
        latencies: list[float] = []
        rows: list[dict[str, float]] = []
        for text in texts:
            t0 = time.perf_counter()
            row = await evaluator._score_one(text, fusion)
            latencies.append(time.perf_counter() - t0)
            rows.append(row)
        return rows, latencies

    per_sample, latencies = asyncio.run(_timed())
    providers: dict[str, list[float]] = {}
    keys = {k for row in per_sample for k in row}
    for key in sorted(keys):
        providers[key] = [row.get(key, 0.0) for row in per_sample]
    lat_ms = [lat * 1000.0 for lat in latencies]
    latency_stats = {
        "p50_ms": round(statistics.median(lat_ms), 2),
        "p95_ms": round(sorted(lat_ms)[int(0.95 * (len(lat_ms) - 1))], 2),
        "mean_ms": round(statistics.fmean(lat_ms), 2),
        "n": len(lat_ms),
    }
    return providers, latency_stats


def summarize(
    labels: list[int],
    providers: dict[str, list[float]],
    threshold: float,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for provider, scores in providers.items():
        m = detection_metrics(labels, scores, threshold=threshold)
        out[provider] = {
            k: m[k]
            for k in (
                "accuracy",
                "precision",
                "recall",
                "f1_score",
                "specificity",
                "false_positive_rate",
                "false_negative_rate",
                "matthews_corrcoef",
                "roc_auc",
                "pr_auc",
                "expected_calibration_error",
                "brier_score",
                "true_positives",
                "false_positives",
                "false_negatives",
                "true_negatives",
            )
        }
        out[provider]["threshold"] = threshold
    return out


def sweep(
    labels: list[int],
    scores: list[float],
    thresholds: list[float],
) -> list[dict[str, Any]]:
    rows = []
    for t in thresholds:
        m = detection_metrics(labels, scores, threshold=t)
        rows.append(
            {
                "threshold": t,
                "precision": round(m["precision"], 4),
                "recall": round(m["recall"], 4),
                "f1": round(m["f1_score"], 4),
                "fpr": round(m["false_positive_rate"], 4),
                "fnr": round(m["false_negative_rate"], 4),
            }
        )
    return rows


def best_f1_threshold(rows: list[dict[str, Any]]) -> dict[str, Any]:
    best = max(rows, key=lambda r: (r["f1"], -r["threshold"]))
    return {"selected_by": "max_validation_f1", **best}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--splits-dir", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    commit = git_commit()
    run_id = f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_git{commit}"
    run_dir = args.out / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading checkpoint: {args.checkpoint}")
    evaluator = HybridEvaluator.load_state(args.checkpoint)
    params_path = args.checkpoint / "params.json"
    checkpoint_params = json.loads(params_path.read_text()) if params_path.exists() else {}

    manifest: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": commit,
        "seed": SEED,
        "checkpoint_dir": str(args.checkpoint.relative_to(ROOT)),
        "checkpoint_params": checkpoint_params,
        "providers_active": evaluator.provider_ids(),
        "feature_schema": {
            "handcrafted_dims": 43,
            "extractor": "PromptNormalizer->PromptFeatureExtractor->MLFeatureProvider",
            "semantic_embedding": bool(checkpoint_params.get("use_semantic_embedding", False)),
            "embedding_model": checkpoint_params.get("embedding_model_name"),
            "total_dims": 43 + (384 if checkpoint_params.get("use_semantic_embedding") else 0),
        },
        "pools": {},
    }

    baseline: dict[str, Any] = {
        "generated_at": manifest["generated_at"],
        "commit": commit,
        "checkpoint_dir": manifest["checkpoint_dir"],
        "feature_schema": manifest["feature_schema"],
        "providers_active": manifest["providers_active"],
        "default_threshold": 0.5,
        "pools": {},
    }

    for pool_name, split_file in POOL_FILES.items():
        path = args.splits_dir / split_file
        if not path.exists():
            print(f"[skip] missing split: {path}")
            continue
        ds = load_pool(path)
        labels = ds.labels()
        n_mal = sum(labels)
        print(f"[{pool_name}] n={len(ds)} malicious={n_mal} benign={len(ds) - n_mal} — scoring...")
        providers, latency = score_pool(evaluator, ds)

        baseline["pools"][pool_name] = {
            "split_file": split_file,
            "samples": len(ds),
            "malicious": n_mal,
            "benign": len(ds) - n_mal,
            "metrics_at_default": summarize(labels, providers, 0.5),
            "latency": latency,
        }
        manifest["pools"][pool_name] = {
            "split_file": split_file,
            "path": str(path.relative_to(ROOT)),
            "samples": len(ds),
            "malicious": n_mal,
            "benign": len(ds) - n_mal,
            "role": (
                "internal validation (threshold/calibration selection allowed)"
                if pool_name == "validation"
                else "internal test (evaluation only)"
                if pool_name == "test"
                else "EXTERNAL held-out JBB (never used for fitting/selection)"
            ),
        }
        # Sweep evidence: full grid on validation only (selection data);
        # other pools recorded for transparency, not selection.
        fusion_scores = providers.get("fusion", [])
        baseline["pools"][pool_name]["fusion_threshold_sweep"] = sweep(
            labels, fusion_scores, THRESHOLD_SWEEP
        )

    # Threshold-selection evidence from validation only.
    val_rows = baseline["pools"].get("validation", {}).get("fusion_threshold_sweep")
    if val_rows:
        baseline["operating_point"] = {
            **best_f1_threshold(val_rows),
            "note": (
                "Selected on internal validation ONLY. External pools were "
                "not consulted. Transfer of this threshold must be verified "
                "on each external deployment corpus."
            ),
        }

    (run_dir / "baseline_metrics.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    (run_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (args.out / "baseline_metrics.json").write_text(
        json.dumps(baseline, indent=2), encoding="utf-8"
    )
    (args.out / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"\nWrote: {run_dir / 'baseline_metrics.json'}")
    fusion_summary = {
        p: {
            "f1": round(m["metrics_at_default"]["fusion"]["f1_score"], 4),
            "recall": round(m["metrics_at_default"]["fusion"]["recall"], 4),
            "fpr": round(m["metrics_at_default"]["fusion"]["false_positive_rate"], 4),
            "roc_auc": round(m["metrics_at_default"]["fusion"]["roc_auc"], 4),
            "latency_p50_ms": m["latency"]["p50_ms"],
        }
        for p, m in baseline["pools"].items()
    }
    print(json.dumps(fusion_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
