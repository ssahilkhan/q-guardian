"""Dataset catalog, access and preparation for the product workflow.

A thin read/write layer over the existing dataset subsystems:

* ``DatasetRegistry`` — the shipped catalog (source, license, column mapping).
* ``DatasetAuthResolver`` — access classification (public / gated / …).
* ``DatasetPreparationPipeline`` / ``DatasetDownloader`` — the canonical
  download -> normalize -> cap -> dedup -> split -> manifest pipeline.

Preparation is scheduled on the shared job runner because downloads can take
minutes. Hugging Face auth is intentionally server-side only: the worker uses
the ``HF_TOKEN`` environment variable and clients never supply a token.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.api.services import artifacts
from q_guardian.benchmark.download import DatasetDownloader
from q_guardian.benchmark.registry import DatasetRegistry
from q_guardian.ml.datasets.auth import (
    DatasetAuthResolver,
    create_auth_resolver,
)
from q_guardian.training.config import TrainingPipelineConfig
from q_guardian.training.prepare import DatasetPreparationPipeline

if TYPE_CHECKING:
    from pathlib import Path

    from q_guardian.api.services.job_runner import Job, JobContext

logger = structlog.get_logger("api.datasets")

_GROUPS = ("train", "validation", "test", "external_eval")


def _registry() -> DatasetRegistry:
    return DatasetRegistry.builtin()


def _resolver() -> DatasetAuthResolver:
    return create_auth_resolver(os.environ.get("HF_TOKEN"))


def _default_groups(dataset_id: str) -> list[str]:
    config = TrainingPipelineConfig()
    return [group for group in _GROUPS if dataset_id in getattr(config.datasets, group)]


def catalog() -> list[dict[str, Any]]:
    """Return the full dataset catalog with access status, oldest first."""
    resolver = _resolver()
    entries: list[dict[str, Any]] = []
    for spec in _registry().all():
        info = resolver.check_dataset_access(spec)
        entries.append(
            {
                "dataset_id": spec.dataset_id,
                "name": spec.name,
                "source": spec.source,
                "license": spec.license,
                "homepage": spec.homepage,
                "source_type": spec.source_type.value,
                "requires_token": spec.requires_token,
                "max_samples": spec.max_samples,
                "groups": _default_groups(spec.dataset_id),
                "access": {
                    "access_type": info.access_type.value,
                    "requires_token": info.requires_token,
                    "message": info.message,
                    "is_accessible": info.is_accessible,
                },
            }
        )
    return entries


def auth_status() -> dict[str, Any]:
    """Return the current dataset-authentication configuration (never the token)."""
    resolver = _resolver()
    is_valid, message = resolver.validate_token()
    return {
        "provider": "huggingface",
        "token_env_var": DatasetAuthResolver.HF_TOKEN_ENV_VAR,
        "token_configured": resolver.has_token,
        "token_format_valid": is_valid if resolver.has_token else None,
        "message": message,
    }


def get_dataset(dataset_id: str) -> dict[str, Any] | None:
    """Return a single catalog entry, or ``None`` when the id is unknown."""
    for entry in catalog():
        if entry["dataset_id"] == dataset_id:
            return entry
    return None


def access(dataset_id: str) -> dict[str, Any] | None:
    """Return the access classification for a dataset, or ``None``."""
    try:
        spec = _registry().get(dataset_id)
    except KeyError:
        return None
    info = _resolver().check_dataset_access(spec)
    return {
        "dataset_id": info.dataset_id,
        "access_type": info.access_type.value,
        "requires_token": info.requires_token,
        "message": info.message,
        "homepage": info.homepage,
        "provider": info.provider.value if info.provider else None,
    }


def prepared() -> list[dict[str, Any]]:
    """Inventory prepared datasets on disk (per-dataset dirs and training runs)."""
    entries: list[dict[str, Any]] = []
    for root, kind in ((artifacts.datasets_root(), "dataset"), (artifacts.training_root(), "run")):
        if not root.is_dir():
            continue
        for directory in sorted(root.iterdir()):
            if not directory.is_dir():
                continue
            manifest_path = directory / "dataset_manifest.json"
            if not manifest_path.is_file():
                continue
            entry = _read_prepared_entry(directory, kind)
            if entry is not None:
                entries.append(entry)
    entries.sort(key=lambda entry: entry["generated_at"], reverse=True)
    return entries


def _read_prepared_entry(directory: Path, kind: str) -> dict[str, Any] | None:
    """Summarize one prepared run directory from its manifest and splits."""
    try:
        manifest = json.loads((directory / "dataset_manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    pools = manifest.get("pools", {}) if isinstance(manifest, dict) else {}
    stats = {
        pool: {
            "samples": entry.get("samples", 0) if isinstance(entry, dict) else 0,
            "benign": entry.get("benign", 0) if isinstance(entry, dict) else 0,
            "malicious": entry.get("malicious", 0) if isinstance(entry, dict) else 0,
        }
        for pool, entry in pools.items()
        if isinstance(entry, dict)
    }
    try:
        modified = datetime.fromtimestamp(directory.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        modified = ""
    dataset_ids = _manifest_dataset_ids(manifest)
    label = directory.name
    entry_id = label
    if kind == "run":
        if dataset_ids:
            label = f"prepared run: {', '.join(sorted(dataset_ids))}"
        entry_id = f"run:{label}"
    return {
        "id": entry_id,
        "kind": kind,
        "directory": str(directory),
        "dataset_ids": dataset_ids,
        "pools": stats,
        "generated_at": modified,
    }


def _manifest_dataset_ids(manifest: dict[str, Any]) -> list[str]:
    if not isinstance(manifest, dict):
        return []
    groups = manifest.get("groups", {})
    if not isinstance(groups, dict):
        return []
    return sorted(
        {
            dataset_id
            for pool in groups.values()
            if isinstance(pool, list)
            for dataset_id in pool
        }
    )


def submit_prepare(dataset_id: str) -> Job:
    """Schedule dataset preparation (job kind ``dataset.prepare``)."""
    from q_guardian.api.services.job_runner import get_job_runner

    return get_job_runner().submit(
        kind="dataset.prepare",
        label=f"Prepare dataset '{dataset_id}'",
        output_dir=artifacts.datasets_root() / dataset_id,
        fn=lambda context: _prepare_dataset(context, dataset_id),
    )


def _prepare_dataset(context: JobContext, dataset_id: str) -> dict[str, Any]:
    registry = _registry()
    try:
        registry.get(dataset_id)
    except KeyError as exc:
        msg = f"unknown dataset id: {dataset_id}"
        raise ValueError(msg) from exc

    config = TrainingPipelineConfig()
    config.datasets.train = [dataset_id]
    config.datasets.validation = []
    config.datasets.test = []
    config.datasets.external_eval = []
    output_dir = context.output_dir or config.output_dir

    pipeline = DatasetPreparationPipeline(
        downloader=DatasetDownloader(token=os.environ.get("HF_TOKEN")),
        progress=lambda message: context.progress(message),
    )
    prepared = pipeline.prepare(config, output_dir, include_only={dataset_id})

    summary: dict[str, Any] = {
        "dataset_id": dataset_id,
        "directory": str(prepared.output_dir),
        "pools": {
            pool: {
                "samples": len(records),
                "benign": sum(1 for r in records if r.label == 0),
                "malicious": sum(1 for r in records if r.label == 1),
            }
            for pool, records in prepared.splits().items()
        },
        "leaked_removed": prepared.leakage_report.total_leaked,
    }
    entry = next(
        (
            item
            for item in prepared.manifest.datasets.values()
            if item.source == dataset_id
        ),
        None,
    )
    if entry is not None:
        summary["counts"] = {
            "requested": entry.requested,
            "loaded": entry.loaded,
            "capped": entry.capped,
            "deduplicated": entry.deduplicated,
            "final": entry.final,
        }
    context.progress(f"prepared {dataset_id}: ready for training")
    return summary
