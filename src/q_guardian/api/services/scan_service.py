"""Security scans over prepared data for the product workflow.

A "security scan" measures how well the detection pipeline performs on the
held-out evaluation pools of a prepared dataset or training run. It reuses the
framework's real measurement harnesses — never a new detector:

* ``cv`` — K-fold cross-validation via ``DetectionBenchmark`` over the eval
  pools (``test`` + ``external_eval``) of a prepared dataset or training run.
* ``model_eval`` — score a trained ``HybridEvaluator`` checkpoint (from a
  training run) over the same eval pools and report per-provider + fusion
  metrics.

Results are persisted as job records under ``artifacts/scans`` and surface a
verdict derived from the measured detection rate — no metric is fabricated.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.api.services import artifacts
from q_guardian.evaluation.benchmark import DetectionBenchmark
from q_guardian.evaluation.dataset import BenchmarkSample, PromptBenchmarkDataset
from q_guardian.evaluation.pipeline import HybridEvaluator
from q_guardian.training.artifacts import read_splits, write_json

if TYPE_CHECKING:
    from pathlib import Path

    from q_guardian.api.services.job_runner import Job, JobContext

logger = structlog.get_logger("api.scans")

SCAN_RUN_KIND = "scan.run"

_VERDICT_THRESHOLDS = (0.8, 0.5)


def history(limit: int = 50) -> list[dict[str, Any]]:
    """Return scan-run records (newest first), projecting a safe subset."""
    from q_guardian.api.services.job_runner import get_job_runner

    jobs = get_job_runner().list([SCAN_RUN_KIND])
    return [_project(job) for job in jobs[: int(limit)]]


def get(scan_id: str) -> dict[str, Any] | None:
    """Return one scan record, or ``None`` when unknown."""
    from q_guardian.api.services.job_runner import get_job_runner

    job = get_job_runner().get(scan_id)
    if job is None or job.kind != SCAN_RUN_KIND:
        return None
    return _project(job)


def submit_scan(
    *,
    kind: str,
    target: str,
    k: int = 3,
    seed: int = 42,
    threshold: float = 0.5,
    ablate: bool = False,
) -> Job:
    """Schedule a security scan over a prepared dataset or training run."""
    from q_guardian.api.services.job_runner import get_job_runner

    base_dir = _resolve_target_dir(target)
    if base_dir is None:
        msg = (
            f"unknown scan target: {target!r} — expected a dataset id prepared under "
            "artifacts/datasets or a training run under artifacts/training"
        )
        raise ValueError(msg)
    return get_job_runner().submit(
        kind=SCAN_RUN_KIND,
        label=f"{kind} scan of {target}",
        output_dir=artifacts.scans_root(),
        fn=lambda context: _run_scan(
            context,
            kind=kind,
            target=target,
            base_dir=base_dir,
            k=k,
            seed=seed,
            threshold=threshold,
            ablate=ablate,
        ),
    )


def _run_scan(
    context: JobContext,
    *,
    kind: str,
    target: str,
    base_dir: Path,
    k: int,
    seed: int,
    threshold: float,
    ablate: bool,
) -> dict[str, Any]:
    context.progress(f"loading evaluation pools from {base_dir.name}")
    dataset = _eval_dataset(base_dir)
    config: dict[str, Any] = {
        "kind": kind,
        "target": target,
        "k": k,
        "seed": seed,
        "threshold": threshold,
        "ablate": ablate,
    }
    if kind == "model_eval":
        run_dir = _resolve_run_dir(target)
        if run_dir is None:
            msg = f"model_eval requires a training run target, got {target!r}"
            raise ValueError(msg)
        model_dir = run_dir / "model"
        if not model_dir.is_dir():
            msg = f"run '{target}' has no model checkpoint; train it first"
            raise ValueError(msg)
        context.progress(f"loading fitted evaluator from {run_dir.name}")
        evaluator = HybridEvaluator.load_state(model_dir)
        config["model"] = {"run": target}
        context.progress(f"scoring {len(dataset)} samples")
        result = evaluator.evaluate(dataset, threshold=threshold, include_providers=None)
        metrics = {
            provider: _scalar_metrics(payload)
            for provider, payload in result.items()
            if provider != "scores"
        }
        sample_scores = result.get("scores") or []
    else:
        if k < 2:
            msg = "k must be at least 2 for cross-validation scans"
            raise ValueError(msg)
        quantum_kwargs = _quantum_kwargs(base_dir)
        context.progress(f"running {k}-fold cross-validation (ablate={ablate})")
        benchmark = DetectionBenchmark(evaluator_kwargs=quantum_kwargs)
        report = benchmark.run(dataset, k=k, seed=seed, threshold=threshold, ablate=ablate)
        context.progress("aggregating fold metrics")
        metrics = report["cross_validation"].get("metrics", {})
        config = {**config, "evaluator": report.get("config", {}).get("evaluator", {})}
        if report.get("cross_validation", {}).get("roc_auc_ranking"):
            config["roc_auc_ranking"] = report["cross_validation"]["roc_auc_ranking"]
        if ablate and report.get("ablation_summary"):
            config["ablation_summary"] = report["ablation_summary"]
        sample_scores = report.get("scores") or []
        context.progress("wrote benchmark report")

    verdict, reason = _verdict(metrics)
    summary: dict[str, Any] = {
        "scan_id": context.job_id,
        "kind": kind,
        "target": target,
        "config": config,
        "dataset": dataset.describe(),
        "metrics": metrics,
        "scores_summary": {
            "samples": len(sample_scores),
            "positives": sum(1 for entry in sample_scores if entry.get("label") == 1),
            "negatives": sum(1 for entry in sample_scores if entry.get("label") == 0),
        },
        "verdict": verdict,
        "verdict_reason": reason,
        "note": (
            "Verdict is derived from the measured fusion detection rate (recall). "
            "Metrics come from the framework detection pipeline only."
        ),
    }
    output_dir = context.output_dir
    if output_dir is not None:
        write_json(output_dir / f"{summary['scan_id']}.summary.json", summary)
        (output_dir / f"{summary['scan_id']}.summary.md").write_text(
            _to_markdown(summary), encoding="utf-8"
        )
    context.progress(f"scan complete — verdict {verdict['level']}")
    return summary


def _eval_dataset(base_dir: Path) -> PromptBenchmarkDataset:
    splits = read_splits(base_dir)
    records = list(splits.get("test", [])) + list(splits.get("external_eval", []))
    if not records:
        msg = (
            f"no labeled evaluation samples in {base_dir.name} "
            "(test or external_eval pools are empty); prepare a dataset that "
            "produces held-out eval data before scanning"
        )
        raise ValueError(msg)
    return PromptBenchmarkDataset(
        [BenchmarkSample(text=r.text, label=r.label, category=r.category) for r in records]
    )


def _resolve_target_dir(target: str) -> Path | None:
    dataset_dir = artifacts.datasets_root() / target
    if (dataset_dir / "dataset_manifest.json").is_file():
        return dataset_dir
    run_dir = artifacts.training_root() / target
    if (run_dir / "training_config.json").is_file():
        return run_dir
    return None


def _resolve_run_dir(target: str) -> Path | None:
    run_dir = artifacts.training_root() / target
    if (run_dir / "training_config.json").is_file():
        return run_dir
    return None


def _quantum_kwargs(base_dir: Path) -> dict[str, Any]:
    """Derive evaluator kwargs from the run config when available."""
    config_path = base_dir / "training_config.json"
    if not config_path.is_file():
        return {"quantum": False}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"quantum": False}
    model = config.get("model") or {}
    return {
        "quantum": bool(model.get("quantum", False)),
        "quantum_shots": int(model.get("quantum_shots") or 128),
        "quantum_feature_count": int(model.get("quantum_feature_count") or 5),
        "quantum_cap": model.get("quantum_cap"),
        "n_estimators": int(model.get("n_estimators") or 50),
        "contamination": float(model.get("contamination") or 0.2),
    }


def _scalar_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only scalar metrics from an evaluator.evaluate() provider block."""
    if not isinstance(payload, dict):
        return {}
    return {
        key: value
        for key, value in payload.items()
        if isinstance(value, (int, float)) and key != "support"
    }


def _verdict(metrics: dict[str, Any]) -> tuple[dict[str, str], str]:
    fusion = metrics.get("fusion") or {}
    detection_rate = _meanish(fusion.get("recall", fusion.get("detection_rate")))
    f1 = _meanish(fusion.get("f1_score", fusion.get("f1")))
    roc_auc = _meanish(fusion.get("roc_auc"))
    if detection_rate is None:
        return {"level": "unknown", "code": "no_metrics"}, "No fusion metrics were produced."
    high, review = _VERDICT_THRESHOLDS
    if detection_rate >= high:
        level, code = "low_risk", "low"
        conclusion = (
            f"Detection rate {detection_rate:.3f} meets the {high:.0%} threshold "
            f"for the selected evaluation pools."
        )
    elif detection_rate >= review:
        level, code = "review", "review"
        conclusion = (
            f"Detection rate {detection_rate:.3f} is below the {high:.0%} bar; "
            "review findings and consider retraining."
        )
    else:
        level, code = "high_risk", "high"
        conclusion = (
            f"Detection rate {detection_rate:.3f} failed the {review:.0%} bar "
            "on these evaluation pools."
        )
    extra = []
    if f1 is not None:
        extra.append(f"F1 {f1:.3f}")
    if roc_auc is not None:
        extra.append(f"ROC-AUC {roc_auc:.3f}")
    reason = conclusion + (" " + " · ".join(extra) if extra else "")
    return {"level": level, "code": code}, reason


def _meanish(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("mean")
    if not isinstance(value, (int, float)):
        return None
    return round(float(value), 6)


def _to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Q-Guardian Security Scan",
        "",
        f"- Scan: `{summary.get('scan_id')}`",
        f"- Type: {summary.get('kind')}",
        f"- Target: {summary.get('target')}",
        f"- Dataset: {summary['dataset'].get('total')} samples "
        f"({summary['dataset'].get('malicious')} threats / "
        f"{summary['dataset'].get('benign')} benign)",
        "",
        f"## Verdict — {summary['verdict'].get('level')}",
        "",
        summary.get("verdict_reason", ""),
        "",
        "## Provider metrics",
        "",
        "| Provider | Metric | Value |",
        "| --- | --- | --- |",
    ]
    for provider, entries in (summary.get("metrics") or {}).items():
        if not isinstance(entries, dict):
            continue
        for metric, value in sorted(entries.items()):
            lines.append(f"| {provider} | {metric} | {value} |")
    lines.append("")
    lines.append(f"> {summary.get('note', '')}")
    return "\n".join(lines) + "\n"


def _project(job: Any) -> dict[str, Any]:
    """Project a job record into the scan history shape."""
    result = job.result or {}
    return {
        "scan_id": job.id,
        "status": job.status,
        "kind": job.kind,
        "label": job.label,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error": job.error,
        "target": result.get("target"),
        "scan_type": result.get("kind"),
        "dataset": result.get("dataset"),
        "metrics": result.get("metrics"),
        "scores_summary": result.get("scores_summary"),
        "verdict": result.get("verdict"),
        "verdict_reason": result.get("verdict_reason"),
        "note": result.get("note"),
    }
