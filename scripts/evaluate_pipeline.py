"""Evaluate detection quality of the hybrid Q-Guardian pipeline.

Runs K-fold cross-validation (with optional provider ablation) on the
curated benchmark dataset (or a user-supplied JSONL dataset) and writes a
JSON report, a Markdown report, and a per-sample CSV score table.

The pipeline measured is the real one: normalizer -> feature extractor ->
rule engine -> isolation forest -> random forest -> quantum QSVM ->
weighted-voting hybrid fusion, wired through the framework's own provider
adapters.

Usage:
    python scripts/evaluate_pipeline.py
    python scripts/evaluate_pipeline.py --dataset data/benchmark_prompts.jsonl
    python scripts/evaluate_pipeline.py --k 5 --no-quantum --no-ablate
    python scripts/evaluate_pipeline.py --output docs/output/evaluation

Options:
    --dataset PATH        JSONL dataset (rows: text, label[, category]);
                          default: built-in curated benchmark corpus
    --k N                 number of CV folds (default 5)
    --seed N              fold seed (default 42)
    --threshold F         decision threshold for binary metrics (default 0.5)
    --no-quantum          skip the quantum QSVM provider (classical only)
    --quantum-shots N     simulator shots per kernel evaluation (default 128)
    --quantum-feature-count N   qubits / leading features used by the QSVM
                          (default 5)
    --quantum-cap N       cap QSVM training samples (kernel matrix is O(n^2))
    --no-ablate           skip the provider ablation phase
    --output DIR          where to write report.json / report.md / scores.csv
                          (default: docs/output/evaluation)
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(30),
    processors=[
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q_guardian.evaluation import (  # noqa: E402
    DetectionBenchmark,
    PromptBenchmarkDataset,
    to_markdown,
    write_json,
)
from q_guardian.evaluation.pipeline import ALL_PROVIDERS  # noqa: E402

DEFAULT_OUTPUT_DIR = ROOT / "docs" / "output" / "evaluation"


def _progress(msg: str) -> None:
    print(f"  {msg}")


def _write_scores(scores: list[dict], path: Path) -> None:
    """Write per-sample threat scores to CSV."""
    fieldnames = ["label", "text", "fusion", *ALL_PROVIDERS]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in scores:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=None,
                        help="path to JSONL dataset (default: built-in corpus)")
    parser.add_argument("--k", type=int, default=5, help="number of CV folds")
    parser.add_argument("--seed", type=int, default=42, help="fold seed")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="decision threshold (default 0.5)")
    parser.add_argument("--no-quantum", action="store_true",
                        help="skip the quantum QSVM provider")
    parser.add_argument("--quantum-shots", type=int, default=128,
                        help="simulator shots per kernel evaluation")
    parser.add_argument("--quantum-feature-count", type=int, default=5,
                        help="number of features/qubits used by the QSVM")
    parser.add_argument("--quantum-cap", type=int, default=None,
                        help="cap QSVM training samples (kernel is O(n^2))")
    parser.add_argument("--no-ablate", action="store_true",
                        help="skip provider ablation")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR),
                        help="output directory for reports")
    args = parser.parse_args()

    if args.dataset:
        dataset_path = Path(args.dataset)
        if not dataset_path.exists():
            raise SystemExit(f"Dataset not found: {dataset_path}")
        dataset = PromptBenchmarkDataset.from_jsonl(dataset_path)
        dataset_name = str(dataset_path)
    else:
        dataset = PromptBenchmarkDataset.builtin()
        dataset_name = "builtin"

    print(f"Dataset ({dataset_name}): {len(dataset)} samples "
          f"({dataset.positives()} threats / {dataset.negatives()} benign)")

    evaluator_kwargs = {
        "quantum": not args.no_quantum,
        "quantum_shots": args.quantum_shots,
        "quantum_feature_count": args.quantum_feature_count,
        "quantum_cap": args.quantum_cap,
    }

    benchmark = DetectionBenchmark(evaluator_kwargs=evaluator_kwargs)
    print(f"Running {args.k}-fold cross-validation "
          f"{'(with quantum)' if not args.no_quantum else '(classical only)'}...")
    t0 = time.monotonic()
    report = benchmark.run(
        dataset,
        k=args.k,
        seed=args.seed,
        threshold=args.threshold,
        ablate=not args.no_ablate,
        progress=_progress,
    )
    elapsed = time.monotonic() - t0
    report["config"]["dataset"] = dataset_name
    report["config"]["elapsed_seconds"] = round(elapsed, 2)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    md_path = output_dir / "report.md"
    scores_path = output_dir / "scores.csv"
    _write_scores(report.pop("scores", []) or [], scores_path)
    report["scores"] = None  # per-sample scores live in scores.csv
    write_json(report, json_path)
    md_path.write_text(to_markdown(report), encoding="utf-8")
    print(f"  Reports written to {output_dir}")

    # Summarize the headline numbers.
    cv = report["cross_validation"]
    fusion = cv["metrics"].get("fusion", {})
    print("\n" + "=" * 64)
    print("HYBRID FUSION (mean over folds)")
    for key in ("roc_auc", "pr_auc", "f1_score", "accuracy",
                "expected_calibration_error", "brier_score"):
        m = fusion.get(key)
        if m:
            print(f"  {key:<26} {m['mean']:.4f} ± {m['std']:.4f}")
    ranking = cv.get("roc_auc_ranking", [])
    if ranking:
        print("\nPROVIDER ROC-AUC RANKING")
        for row in ranking:
            print(f"  {row['provider']:<22} {row['mean_roc_auc']:.4f}")
    summary = report.get("ablation_summary")
    if summary:
        print("\nABLATION")
        print(f"  most valuable provider: {summary['most_valuable_provider']} "
              f"(delta {summary['most_valuable_delta']:.4f} ROC-AUC)")
        print(f"  recommendation: {summary['recommendation']}")
    print(f"\nTotal benchmark time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
