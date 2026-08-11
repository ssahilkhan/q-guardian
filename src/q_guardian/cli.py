"""Q-Guardian command-line interface.

Exposes the dataset-preparation, training and evaluation pipeline plus the
existing benchmark runner as subcommands::

    q-guardian dataset prepare   --config configs/training.json --output-dir runs/01
    q-guardian dataset validate  --config configs/training.json
    q-guardian model train       --config configs/training.json --output-dir runs/01
    q-guardian model evaluate    --config configs/training.json --output-dir runs/01
    q-guardian benchmark         --config configs/training.json --k 3

Hugging Face authentication uses the ``HF_TOKEN`` environment variable by
default; ``--hf-token`` overrides it. Tokens are never printed and never
persisted into config artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

from q_guardian.benchmark.registry import DatasetRegistry
from q_guardian.benchmark.run import BenchmarkRunner
from q_guardian.training.config import TrainingPipelineConfig
from q_guardian.training.evaluate import EvaluationPipeline
from q_guardian.training.normalize import DatasetRecordPreprocessor
from q_guardian.training.prepare import DatasetPreparationPipeline, PreparedDatasets
from q_guardian.training.train import TrainingPipeline

DEFAULT_CONFIG = Path("configs/training.json")

_LABEL_SUMMARY = {0: "benign", 1: "malicious"}


def _load_config(args: argparse.Namespace) -> TrainingPipelineConfig:
    """Load config from a JSON file (or defaults) and apply CLI overrides."""
    if args.config is not None:
        config = TrainingPipelineConfig.from_file(args.config)
    else:
        config = TrainingPipelineConfig()
    if getattr(args, "seed", None) is not None:
        config.seed = args.seed
    if getattr(args, "output_dir", None) is not None:
        config.output_dir = Path(args.output_dir)
    if getattr(args, "max_samples", None) is not None:
        config.max_samples_per_class = args.max_samples
    if getattr(args, "epochs", None) is not None:
        config.model.epochs = args.epochs
    if getattr(args, "batch_size", None) is not None:
        config.model.batch_size = args.batch_size
    if getattr(args, "learning_rate", None) is not None:
        config.model.learning_rate = args.learning_rate
    if getattr(args, "hf_token", None) is not None:
        config.hf_token = args.hf_token
    return config


def _resolve_token(config: TrainingPipelineConfig) -> str | None:
    """Return the HF token, preferring env var, then config, never printing."""
    env_token = os.environ.get("HF_TOKEN")
    if env_token:
        return env_token
    if config.hf_token is not None:
        return config.hf_token.get_secret_value()
    return None


def _print_counts(counts: Any) -> None:
    print(
        f"  {counts['source']:<30} requested={counts['requested']:<6} "
        f"filtered={counts['filtered']:<4} loaded={counts['loaded']:<6} "
        f"capped={counts['capped']:<4} dedup={counts['deduplicated']:<4} "
        f"leaked={counts['leaked']:<4} final={counts['final']}"
    )


def _cmd_dataset_prepare(args: argparse.Namespace) -> int:
    config = _load_config(args)
    from q_guardian.benchmark.download import DatasetDownloader

    pipeline = DatasetPreparationPipeline(
        downloader=DatasetDownloader(token=_resolve_token(config)),
    )
    include_only: set[str] | None = None
    if getattr(args, "datasets", None):
        include_only = {dataset.strip() for dataset in args.datasets if dataset.strip()}
    t0 = time.monotonic()
    prepared = pipeline.prepare(
        config,
        config.output_dir,
        include_only=include_only,
    )
    elapsed = time.monotonic() - t0
    print(f"\nDataset manifest: {prepared.output_dir / 'dataset_manifest.json'}")
    print(f"Leakage report  : {prepared.output_dir / 'leakage_report.json'}")
    print("\nPer-dataset counts:")
    for dataset_id in config.datasets.all_ids():
        counts = prepared.manifest.datasets.get(dataset_id)
        if counts is None:
            continue
        _print_counts(counts)
    print("\nPools:")
    for name, stats in prepared.manifest.pools.items():
        print(
            f"  {name:<13} samples={stats['samples']:<6} "
            f"benign={stats['benign']:<6} malicious={stats['malicious']}"
        )
    print(f"\nLeaked samples removed: {prepared.leakage_report.total_leaked}")
    print(f"Prepared in {elapsed:.1f}s")
    return 0


def _cmd_dataset_validate(args: argparse.Namespace) -> int:
    config = _load_config(args)
    from q_guardian.benchmark.download import DatasetDownloader, DatasetError
    from q_guardian.benchmark.validate import DatasetValidator

    token = _resolve_token(config)
    downloader = DatasetDownloader(token=token)
    preprocessor = DatasetRecordPreprocessor()
    validator = DatasetValidator()
    registry = DatasetRegistry.builtin()
    required = set(config.datasets.train) | set(config.datasets.validation)

    exit_code = 0
    print("Validating configured datasets (no artifacts written):")
    for dataset_id in config.datasets.all_ids():
        spec = registry.get(dataset_id)
        try:
            split_paths = downloader.download(spec)
        except DatasetError as exc:
            status = "REQUIRED" if dataset_id in required else "optional"
            print(f"  {dataset_id:<32} UNAVAILABLE ({status}): {exc}")
            if dataset_id in required:
                exit_code = 1
            continue
        validation = validator.validate(spec, split_paths)
        records, filtered = preprocessor.preprocess(spec, split_paths)
        print(
            f"  {dataset_id:<32} rows={validation.total} valid_rows={validation.valid_rows} "
            f"records={len(records)} filtered={filtered} "
            f"labels={json.dumps(validation.labels)} "
            f"issues={len(validation.issues)}"
        )
        for issue in validation.issues[:5]:
            print(f"      issue: {issue}")
    return exit_code


def _cmd_model_train(args: argparse.Namespace) -> int:
    config = _load_config(args)
    from q_guardian.benchmark.download import DatasetDownloader

    run_dir = config.output_dir
    if not (run_dir / "splits" / "train.jsonl").exists():
        pipeline = DatasetPreparationPipeline(
            downloader=DatasetDownloader(token=_resolve_token(config))
        )
        print("No prepared splits found; running dataset preparation first...")
        prepared = pipeline.prepare(config, run_dir)
    else:
        prepared = _prepared_from_disk(config, run_dir)

    trainer = TrainingPipeline()
    run = trainer.train(config, prepared, max_samples_per_class=config.max_samples_per_class)
    print(
        f"\nTrained {len(prepared.train)} train / {len(prepared.validation)} validation samples "
        f"in {run.elapsed_seconds}s"
    )
    print(f"Checkpoint: {run.checkpoint_dir}")
    print(f"Metrics   : {run.output_dir / 'metrics.json'}")
    print(f"Log       : {run.training_log_path}")
    return 0


def _prepared_from_disk(config: TrainingPipelineConfig, run_dir: Path) -> PreparedDatasets:
    """Rehydrate a ``PreparedDatasets`` from the artifacts on disk."""
    from q_guardian.training.artifacts import read_splits
    from q_guardian.training.dedup import LeakageReport
    from q_guardian.training.manifest import DatasetManifest

    splits = read_splits(run_dir)
    pools: dict[str, dict[str, int]] = {}
    for name, records in splits.items():
        benign = sum(1 for record in records if record.label == 0)
        pools[name] = {
            "samples": len(records),
            "benign": benign,
            "malicious": len(records) - benign,
        }
    manifest = DatasetManifest(
        seed=config.seed,
        generated_at="",
        groups={
            "train": list(config.datasets.train),
            "validation": list(config.datasets.validation),
            "test": list(config.datasets.test),
            "external_eval": list(config.datasets.external_eval),
        },
        datasets={},
        pools=pools,
    )
    return PreparedDatasets(
        config=config,
        train=splits.get("train", []),
        validation=splits.get("validation", []),
        test=splits.get("test", []),
        external_eval=splits.get("external_eval", []),
        manifest=manifest,
        leakage_report=LeakageReport(train_count=len(splits.get("train", []))),
        output_dir=Path(run_dir),
    )


def _cmd_model_evaluate(args: argparse.Namespace) -> int:
    config = _load_config(args)
    if getattr(args, "threshold", None) is not None:
        config.eval.threshold = args.threshold
    run_dir = config.output_dir
    checkpoint_dir = run_dir / "model"
    if not checkpoint_dir.exists():
        print(f"No checkpoint found at {checkpoint_dir}. Run `model train` first.", file=sys.stderr)
        return 1

    prepared = _prepared_from_disk(config, run_dir)
    evaluator = EvaluationPipeline()
    report = evaluator.evaluate(config, prepared, checkpoint_dir=checkpoint_dir)
    print(f"\nEvaluation report: {run_dir / 'evaluation.md'}")
    print(report.to_markdown())
    return 0


def _cmd_benchmark(args: argparse.Namespace) -> int:
    config = _load_config(args)
    from q_guardian.benchmark.download import DatasetDownloader

    registry = DatasetRegistry.builtin()
    dataset_ids = (
        [d.strip() for d in args.datasets if d.strip()]
        if getattr(args, "datasets", None)
        else registry.public_ids()
    )
    threshold = (
        args.threshold if getattr(args, "threshold", None) is not None else config.eval.threshold
    )
    runner = BenchmarkRunner(
        registry=registry,
        downloader=DatasetDownloader(token=_resolve_token(config)),
        benchmark_kwargs={
            "quantum": not args.no_quantum,
            "quantum_shots": config.model.quantum_shots,
            "quantum_feature_count": config.model.quantum_feature_count,
            "quantum_cap": config.model.quantum_cap,
            "n_estimators": config.model.n_estimators,
            "contamination": config.model.contamination,
        },
    )
    reports = runner.run_all(
        dataset_ids,
        k=args.k,
        seed=config.seed,
        threshold=threshold,
        ablate=not args.no_ablate,
        progress=lambda msg: print(f"  {msg}"),
    )
    output_dir = (
        Path(args.output) if getattr(args, "output", None) else config.output_dir / "benchmark"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    from q_guardian.evaluation.report import to_markdown, write_json

    for dataset_id, report in reports.items():
        write_json(report.as_dict(), output_dir / f"{dataset_id}.json")
        (output_dir / f"{dataset_id}.md").write_text(
            to_markdown(report.as_dict()["benchmark"]), encoding="utf-8"
        )
        fusion = report.provider_metrics().get("fusion", {})
        auc = fusion.get("roc_auc", {})
        print(f"  {dataset_id:<32} fusion ROC-AUC={auc.get('mean', 0.0):.4f} (k={args.k})")
    print(f"\nBenchmark reports written to {output_dir}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="q-guardian",
        description="Q-Guardian dataset preparation, training and evaluation CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", default=None, help="pipeline config JSON file")
        p.add_argument("--seed", type=int, default=None, help="deterministic seed")
        p.add_argument(
            "--max-samples", type=int, default=None, help="max training samples kept per class"
        )
        p.add_argument("--output-dir", default=None, help="run/output directory")
        p.add_argument(
            "--hf-token", default=None, help="Hugging Face token (prefer the HF_TOKEN env var)"
        )

    p_prepare = sub.add_parser("dataset", help="dataset preparation/validation")
    prepare_sub = p_prepare.add_subparsers(dest="dataset_command", required=True)
    p_prepare_cmd = prepare_sub.add_parser("prepare", help="download+normalize+split")
    _add_common(p_prepare_cmd)
    p_prepare_cmd.add_argument(
        "--datasets", nargs="*", default=None, help="restrict processing to these dataset ids"
    )
    p_prepare_cmd.set_defaults(func=_cmd_dataset_prepare)
    p_validate_cmd = prepare_sub.add_parser("validate", help="check configured datasets")
    _add_common(p_validate_cmd)
    p_validate_cmd.set_defaults(func=_cmd_dataset_validate)

    p_train = sub.add_parser("model", help="train/evaluate the detection model")
    train_sub = p_train.add_subparsers(dest="model_command", required=True)
    p_train_cmd = train_sub.add_parser("train", help="train the hybrid detector")
    _add_common(p_train_cmd)
    p_train_cmd.add_argument(
        "--epochs",
        type=int,
        default=None,
        help="recorded for CLI parity (not applied to sklearn/hybrid)",
    )
    p_train_cmd.add_argument(
        "--batch-size", type=int, default=None, help="recorded for CLI parity (not applied)"
    )
    p_train_cmd.add_argument(
        "--learning-rate", type=float, default=None, help="recorded for CLI parity (not applied)"
    )
    p_train_cmd.set_defaults(func=_cmd_model_train)
    p_eval_cmd = train_sub.add_parser("evaluate", help="evaluate a trained detector")
    _add_common(p_eval_cmd)
    p_eval_cmd.add_argument(
        "--threshold", type=float, default=None, help="decision threshold for binary metrics"
    )
    p_eval_cmd.set_defaults(func=_cmd_model_evaluate)

    p_bench = sub.add_parser("benchmark", help="run the existing benchmark runner")
    p_bench.add_argument("--config", default=None, help="pipeline config JSON file")
    p_bench.add_argument("--seed", type=int, default=None, help="fold seed")
    p_bench.add_argument(
        "--datasets", nargs="*", default=None, help="dataset ids to benchmark (default: all public)"
    )
    p_bench.add_argument("--k", type=int, default=3, help="number of CV folds")
    p_bench.add_argument("--threshold", type=float, default=None, help="decision threshold")
    p_bench.add_argument("--no-quantum", action="store_true", help="skip the quantum QSVM provider")
    p_bench.add_argument("--no-ablate", action="store_true", help="skip provider ablation")
    p_bench.add_argument("--output", default=None, help="output directory for reports")
    p_bench.set_defaults(func=_cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Return value is used as the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return cast("int", args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
