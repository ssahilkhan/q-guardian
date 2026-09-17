"""Training-run orchestration for the product workflow.

Reuses the existing training stack end to end — ``DatasetPreparationPipeline``
(download -> normalize -> cap -> dedup -> split) and ``TrainingPipeline`` /
``HybridEvaluator`` (fit the scikit-learn/quantum hybrid detector) — and
exposes the same artifacts the CLI writes. Long-running work is scheduled on
the shared job runner and persisted under ``artifacts/training``.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.api.services import artifacts
from q_guardian.benchmark.download import DatasetDownloader
from q_guardian.benchmark.registry import DatasetRegistry
from q_guardian.training.config import TrainingPipelineConfig
from q_guardian.training.prepare import DatasetPreparationPipeline
from q_guardian.training.train import TrainingPipeline

if TYPE_CHECKING:
    from q_guardian.api.services.job_runner import Job, JobContext

logger = structlog.get_logger("api.training")

_MODEL_DIR = "model"


def runs() -> list[dict[str, Any]]:
    """List completed+in-progress training runs (newest first)."""
    root = artifacts.training_root()
    if not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        config_path = directory / "training_config.json"
        if not config_path.is_file():
            continue
        entry = _run_summary(directory)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda entry: entry["created_at"], reverse=True)
    return entries


def _run_summary(directory: Path) -> dict[str, Any] | None:
    try:
        config = json.loads((directory / "training_config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = {}
    try:
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        metrics = {}
    try:
        created_at = datetime.fromtimestamp(directory.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        created_at = ""
    model_dir = directory / _MODEL_DIR
    return {
        "name": directory.name,
        "created_at": created_at,
        "train_sources": (
            list(config.get("datasets", {}).get("train", []) or [])
            if isinstance(config.get("datasets"), dict)
            else []
        ),
        "metrics": {
            "train_samples": metrics.get("train_samples"),
            "validation_samples": metrics.get("validation_samples"),
            "elapsed_seconds": metrics.get("elapsed_seconds"),
        },
        "model": {
            "exists": model_dir.is_dir(),
            "quantum": bool((config.get("model") or {}).get("quantum", False)),
            "n_estimators": (config.get("model") or {}).get("n_estimators"),
            "contamination": (config.get("model") or {}).get("contamination"),
        },
        "evaluation_exists": (directory / "evaluation.json").is_file(),
    }


def run(name: str) -> dict[str, Any] | None:
    """Return the full detail of one training run, or ``None``."""
    directory = _resolve_run_dir(name)
    if directory is None:
        return None
    try:
        config = json.loads((directory / "training_config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = {}
    try:
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        metrics = {}
    try:
        labels = json.loads((directory / "label_distribution.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        labels = {}
    evaluation = None
    evaluation_path = directory / "evaluation.json"
    if evaluation_path.is_file():
        try:
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            evaluation = None
    splits = _split_counts(directory)
    return {
        **_run_summary(directory),
        "config": config,
        "metrics": metrics,
        "label_distribution": labels,
        "splits": splits,
        "evaluation": evaluation,
        "evaluation_markdown": _read_bounded(directory / "evaluation.md"),
        "training_log": _read_bounded(directory / "training_log.txt", max_lines=80),
    }


def submit_run(
    *,
    dataset_ids: list[str] | None = None,
    name: str | None = None,
    **overrides: Any,
) -> Job:
    """Schedule a full prepare + train job for the given dataset ids."""
    from q_guardian.api.services.job_runner import get_job_runner

    config = _build_config(dataset_ids=dataset_ids, **overrides)
    run_id = _run_id(name)
    return get_job_runner().submit(
        kind="training.run",
        label=f"Train on {', '.join(config.datasets.train) or 'no sources'}",
        output_dir=artifacts.training_root() / run_id,
        fn=lambda context: _train_worker(context, config),
    )


def submit_evaluate(name: str) -> Job:
    """Schedule an evaluation of an existing trained model."""
    from q_guardian.api.services.job_runner import get_job_runner

    run_dir = _resolve_run_dir(name)
    if run_dir is None:
        msg = f"unknown training run: {name}"
        raise ValueError(msg)
    if not (run_dir / _MODEL_DIR).is_dir():
        msg = f"run '{name}' has no trained model checkpoint; run training first"
        raise ValueError(msg)
    return get_job_runner().submit(
        kind="training.evaluate",
        label=f"Evaluate run '{name}'",
        output_dir=run_dir,
        fn=lambda context: _evaluate_worker(context, run_dir),
    )


def _train_worker(context: JobContext, config: TrainingPipelineConfig) -> dict[str, Any]:
    run_dir = context.output_dir or config.output_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    pipeline = DatasetPreparationPipeline(
        downloader=DatasetDownloader(token=os.environ.get("HF_TOKEN")),
        progress=lambda message: context.progress(message),
    )
    context.progress("preparing datasets")
    prepared = pipeline.prepare(
        config,
        run_dir,
        include_only=set(config.datasets.train),
    )
    context.progress("training hybrid detector")
    trainer = TrainingPipeline()
    start = time.monotonic()
    run = trainer.train(config, prepared, max_samples_per_class=config.max_samples_per_class)
    elapsed = round(time.monotonic() - start, 3)
    context.progress(f"training completed in {run.elapsed_seconds}s")
    return {
        "run": run_dir.name,
        "directory": str(run_dir),
        "train_samples": run.train_samples,
        "validation_samples": run.validation_samples,
        "elapsed_seconds": elapsed,
        "checkpoint_dir": str(run.checkpoint_dir),
        "metrics_path": str(run.output_dir / "metrics.json"),
        "evaluation_available": (run_dir / "evaluation.json").is_file(),
    }


def _evaluate_worker(context: JobContext, run_dir: Path) -> dict[str, Any]:
    from q_guardian.cli import _prepared_from_disk
    from q_guardian.training.evaluate import EvaluationPipeline

    context.progress("loading run configuration")
    config_data = json.loads((run_dir / "training_config.json").read_text(encoding="utf-8"))
    config = TrainingPipelineConfig.model_validate(config_data)
    prepared = _prepared_from_disk(config, run_dir)
    context.progress("scoring internal and external evaluation pools")
    evaluator = EvaluationPipeline()
    report = evaluator.evaluate(config, prepared, checkpoint_dir=run_dir / _MODEL_DIR)
    summary = report.summary
    context.progress(f"evaluation completed over {len(report.matrix)} dataset(s)")
    return {
        "run": run_dir.name,
        "summary": summary,
        "report_path": str(run_dir / "evaluation.json"),
        "markdown_path": str(run_dir / "evaluation.md"),
    }


def _build_config(
    *,
    dataset_ids: list[str] | None,
    **overrides: Any,
) -> TrainingPipelineConfig:
    base = Path("configs/training.json")
    config = (
        TrainingPipelineConfig.from_file(base)
        if base.is_file()
        else TrainingPipelineConfig()
    )
    requested = [dataset_id.strip() for dataset_id in (dataset_ids or []) if dataset_id.strip()]
    if requested:
        known = {spec.dataset_id for spec in DatasetRegistry.builtin().all()}
        unknown = [dataset_id for dataset_id in requested if dataset_id not in known]
        if unknown:
            msg = f"unknown dataset id(s): {', '.join(unknown)}"
            raise ValueError(msg)
        config.datasets.train = requested
    for key in (
        "validation_ratio",
        "seed",
        "max_samples_per_class",
    ):
        if key in overrides and overrides[key] is not None:
            setattr(config, key, overrides[key])
    for key in (
        "quantum",
        "quantum_shots",
        "quantum_feature_count",
        "quantum_cap",
        "n_estimators",
        "contamination",
    ):
        if overrides.get(key) is not None:
            setattr(config.model, key, overrides[key])
    if overrides.get("threshold") is not None:
        config.eval.threshold = overrides["threshold"]
    if overrides.get("provider_weights") is not None:
        config.model.provider_weights = overrides["provider_weights"]
    if overrides.get("hf_token"):
        from pydantic import SecretStr

        config.hf_token = SecretStr(str(overrides["hf_token"]))
    return config


def _run_id(name: str | None) -> str:
    if name and name.strip():
        safe = "".join(ch for ch in name.strip() if ch.isalnum() or ch in "-_")
        if safe:
            return safe
    return f"run-{int(time.time())}"


def _resolve_run_dir(name: str) -> Path | None:
    root = artifacts.training_root()
    directory = root / name
    if directory.is_dir() and (directory / "training_config.json").is_file():
        return directory
    return None


def _split_counts(directory: Path) -> dict[str, int]:
    from q_guardian.training.artifacts import read_splits

    try:
        splits = read_splits(directory)
    except (OSError, json.JSONDecodeError):
        return {}
    return {pool: len(records) for pool, records in splits.items()}


def _read_bounded(path: Path, max_lines: int = 200) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[-max_lines:]) + f"\n… (truncated, {len(lines)} total lines)"
    return text
