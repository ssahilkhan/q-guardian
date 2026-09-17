"""Analytics aggregation for the product workflow.

Aggregates the on-disk product artifacts (datasets, prepared runs, training
runs, security scans) into a dashboard summary, and re-exposes the existing
cross-dataset analytics pipeline (``CrossDatasetAnalytics``) for comparing
multiple saved benchmark/evaluation reports. Everything is computed from real
persisted results; no numbers are synthesized.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from q_guardian.analytics.service import CrossDatasetAnalytics
from q_guardian.api.services import artifacts, dataset_service, scan_service, training_service

logger = structlog.get_logger("api.analytics")

_VERDICT_LEVELS = ("low_risk", "review", "high_risk", "unknown")


def summary() -> dict[str, Any]:
    """Return aggregated dashboard metrics over persisted artifacts."""
    catalog = dataset_service.catalog()
    prepared = dataset_service.prepared()
    runs = training_service.runs()
    scans = scan_service.history(limit=500)

    trained = sum(1 for run in runs if run.get("model", {}).get("exists"))
    verdicts = defaultdict(int)
    detection_rates: list[float] = []
    for scan in scans:
        level = (scan.get("verdict") or {}).get("level", "unknown")
        verdicts[level] += 1
        metrics = scan.get("metrics") or {}
        fusion = metrics.get("fusion") or {}
        rate = _scalar(fusion.get("recall") or fusion.get("detection_rate"))
        if rate is not None:
            detection_rates.append(rate)

    sample_total = 0
    malicious_total = 0
    benign_total = 0
    for entry in prepared:
        for stats in entry.get("pools", {}).values():
            sample_total += int(stats.get("samples", 0))
            malicious_total += int(stats.get("malicious", 0))
            benign_total += int(stats.get("benign", 0))

    timeline = _scan_timeline(scans)

    return {
        "datasets": {
            "catalog": len(catalog),
            "public": sum(1 for entry in catalog if not entry["access"]["requires_token"]),
            "gated": sum(1 for entry in catalog if entry["access"]["requires_token"]),
            "prepared": len(prepared),
        },
        "training": {
            "runs": len(runs),
            "trained_models": trained,
            "evaluated_runs": sum(1 for run in runs if run.get("evaluation_exists")),
        },
        "data": {
            "prepared_samples": sample_total,
            "prepared_malicious": malicious_total,
            "prepared_benign": benign_total,
        },
        "scans": {
            "total": len(scans),
            "by_verdict": {level: verdicts[level] for level in _VERDICT_LEVELS},
            "avg_detection_rate": (
                round(sum(detection_rates) / len(detection_rates), 4)
                if detection_rates
                else None
            ),
            "scans_with_metrics": len(detection_rates),
        },
        "timeline": timeline,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def cross(report_files: list[str], *, mode: str = "macro", strict: bool = True) -> dict[str, Any]:
    """Run the existing cross-dataset analytics over saved report files.

    Only files resolved inside the artifact root are accepted, so callers can
    reference artifacts (e.g. ``artifacts/training/<run>/benchmark/*.json`` or
    ``reports/*/*.json``) without opening up arbitrary file reads.

    Args:
        report_files: Paths (relative to the artifact root) of report JSONs.
        mode: Aggregation mode (macro / weighted / micro).
        strict: Whether to require full compatibility.

    Raises:
        ValueError: If a path escapes the artifact root or no reports parse.
    """
    paths = [_resolve_within_root(raw) for raw in report_files]
    if not paths:
        msg = "no report files to analyze"
        raise ValueError(msg)
    service = CrossDatasetAnalytics(aggregation_mode=mode, strict=strict)
    report = service.analyze(paths)
    return report.as_dict()


def _resolve_within_root(raw: str) -> Path:
    root = artifacts.artifacts_root()
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        msg = f"report path escapes the artifact root: {raw!r}"
        raise ValueError(msg) from exc
    if not candidate.is_file():
        msg = f"report file not found: {raw!r}"
        raise ValueError(msg)
    return candidate


def _scan_timeline(scans: list[dict[str, Any]], days: int = 14) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date()
    counts: dict[str, int] = defaultdict(int)
    for scan in scans:
        stamp = scan.get("finished_at") or scan.get("created_at")
        if not stamp:
            continue
        try:
            day = datetime.fromisoformat(stamp).astimezone(UTC).date()
        except ValueError:
            continue
        if (today - day).days < days:
            counts[day.isoformat()] += 1
    return [
        {
            "date": (today - timedelta(days=delta)).isoformat(),
            "scans": counts[(today - timedelta(days=delta)).isoformat()],
        }
        for delta in range(days - 1, -1, -1)
    ]


def _scalar(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("mean")
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    return None
