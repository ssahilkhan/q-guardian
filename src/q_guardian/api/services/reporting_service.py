"""Report inventory and generation for the product workflow.

Reports in Q-Guardian are rendered from real persisted artifacts — the console
never fabricates a number. Three kinds are exposed, all backed by existing
writers:

* ``scan`` — the summary Markdown/JSON a security scan already wrote.
* ``training`` — the ``evaluation.md`` / ``evaluation.json`` of a run.
* ``analytics`` — a fresh ``CrossDatasetAnalytics`` report (JSON/CSV/Markdown)
  generated on demand from saved report JSON files.

Downloads resolve strictly inside the artifact root.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from q_guardian.analytics.service import CrossDatasetAnalytics
from q_guardian.api.services import artifacts, scan_service, training_service

logger = structlog.get_logger("api.reports")

_REPORT_KINDS = ("scan", "training", "analytics")
_FORMAT_BY_KIND = {
    "scan": ("md", "json"),
    "training": ("md", "json"),
    "analytics": ("json", "md", "csv"),
}
_MAX_CONTENT_BYTES = 4 * 1024 * 1024


def list_reports() -> list[dict[str, Any]]:
    """Inventory all available report artifacts (newest first)."""
    entries: list[dict[str, Any]] = []
    for scan in scan_service.history(limit=500):
        scan_id = scan["scan_id"]
        base = artifacts.scans_root() / f"{scan_id}.summary"
        entries.extend(_entry("scan", f"scan:{scan_id}", base))
    for run in training_service.runs():
        if not run.get("evaluation_exists"):
            continue
        base = artifacts.training_root() / run["name"] / "evaluation"
        entries.extend(_entry("training", f"training:{run['name']}", base))
    analytics_dir = artifacts.reports_root() / "analytics"
    if analytics_dir.is_dir():
        for directory in sorted(analytics_dir.iterdir()):
            if not directory.is_dir():
                continue
            base = directory / "report"
            entries.extend(_entry("analytics", f"analytics:{directory.name}", base))
    entries.sort(key=lambda entry: entry.get("generated_at", ""), reverse=True)
    return entries


def _entry(kind: str, report_id: str, base: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for fmt in _FORMAT_BY_KIND[kind]:
        path = Path(f"{base}.{fmt}")
        try:
            size = path.stat().st_size
            generated_at = _mtime(path)
        except OSError:
            continue
        if size > _MAX_CONTENT_BYTES:
            continue
        found.append(
            {
                "report_id": report_id,
                "kind": kind,
                "format": fmt,
                "size": size,
                "generated_at": generated_at,
            }
        )
    return found


def generate(kind: str, report_id: str) -> dict[str, Any]:
    """Produce a report artifact and return its inventory entry.

    For ``scan`` / ``training`` the artifact already exists on disk; calling
    generate re-verifies it. For ``analytics`` the report is computed from the
    report JSON files referenced by the analytics report id.
    """
    if kind == "scan":
        return _generate_scan(report_id)
    if kind == "training":
        return _generate_training(report_id)
    if kind == "analytics":
        return _generate_analytics(report_id)
    msg = f"unknown report kind: {kind!r}"
    raise ValueError(msg)


def _generate_scan(report_id: str) -> dict[str, Any]:
    raw = report_id.replace("scan:", "", 1) if report_id.startswith("scan:") else report_id
    scan = scan_service.get(raw)
    if scan is None:
        msg = f"unknown scan report: {report_id}"
        raise ValueError(msg)
    scan_id = scan["scan_id"]
    return _confirm(
        ["md", "json"],
        artifacts.scans_root(),
        f"{scan_id}.summary",
        "scan",
        f"scan:{scan_id}",
    )


def _generate_training(report_id: str) -> dict[str, Any]:
    name = report_id.replace("training:", "", 1) if report_id.startswith("training:") else report_id
    run = training_service.run(name)
    if run is None or not run.get("evaluation_exists"):
        msg = f"unknown or unevaluated training run: {name}"
        raise ValueError(msg)
    return _confirm(
        ["md", "json"],
        artifacts.training_root() / name,
        "evaluation",
        "training",
        f"training:{name}",
    )


def _generate_analytics(report_id: str) -> dict[str, Any]:
    raw = (
        report_id.replace("analytics:", "", 1)
        if report_id.startswith("analytics:")
        else report_id
    )
    if not raw:
        msg = "analytics report name is required"
        raise ValueError(msg)
    out_dir = artifacts.reports_root() / "analytics" / _safe_name(raw)
    source_entries = _analytics_sources()
    if not source_entries:
        msg = "no saved report JSON files to aggregate — run a cross-dataset analysis first"
        raise ValueError(msg)
    service = CrossDatasetAnalytics()
    report = service.analyze(source_entries)
    service.save(report, out_dir)
    logger.info("report_generated", kind="analytics", output=str(out_dir))
    return _confirm(
        ["json", "md", "csv"],
        out_dir,
        "report",
        "analytics",
        f"analytics:{raw}",
    )


def download(report_id: str, fmt: str) -> str | None:
    """Return the text content of a report artifact, or ``None``."""
    if fmt not in ("md", "json", "csv"):
        return None
    path = _resolve_content_path(report_id, fmt)
    if path is None:
        return None
    try:
        if path.stat().st_size > _MAX_CONTENT_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _resolve_content_path(report_id: str, fmt: str) -> Path | None:
    if report_id.startswith("scan:"):
        scan = scan_service.get(report_id[len("scan:"):])
        if scan is None:
            return None
        path = artifacts.scans_root() / f"{scan['scan_id']}.summary.{fmt}"
        return path if path.is_file() else None
    if report_id.startswith("training:"):
        name = report_id[len("training:"):]
        run = training_service.run(name)
        if run is None:
            return None
        path = artifacts.training_root() / name / f"evaluation.{fmt}"
        return path if path.is_file() else None
    if report_id.startswith("analytics:"):
        name = report_id[len("analytics:"):]
        path = artifacts.reports_root() / "analytics" / _safe_name(name) / f"report.{fmt}"
        return path if path.is_file() else None
    return None


def _confirm(
    formats: list[str],
    base: Path,
    stem: str,
    kind: str,
    report_id: str,
) -> dict[str, Any]:
    entries = _entry(kind, report_id, base / stem)
    if not entries:
        msg = f"no {kind} report artifact available for {report_id!r}"
        raise ValueError(msg)
    return {"report_id": report_id, "kind": kind, "entries": entries, "formats": formats}


def _analytics_sources() -> list[Path]:
    """Collect report-shaped JSON files inside the artifact root.

    Only files the existing analytics normalizer recognizes as a benchmark,
    evaluation or baseline artifact are included — job records, configs,
    manifests and arbitrary JSON are ignored. The classification logic is
    delegated to ``analytics.normalizer`` so the filter cannot drift from
    what the pipeline can actually consume.
    """
    roots = (
        artifacts.training_root(),
        artifacts.scans_root(),
        artifacts.reports_root(),
    )
    candidates: list[Path] = []
    for root in roots:
        if root.is_dir():
            candidates.extend(path for path in root.rglob("*.json") if path.is_file())
    seen: set[str] = set()
    sources: list[Path] = []
    for path in sorted(candidates, key=lambda p: str(p).lower()):
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        if _is_report_shaped(path):
            sources.append(path)
    return sources


def _is_report_shaped(path: Path) -> bool:
    """Return True when ``path`` is a JSON artifact the analytics pipeline
    recognizes as a report (benchmark / evaluation / baseline)."""
    from q_guardian.analytics.normalizer import NormalizationError, _detect_format

    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError):
        return False
    if not isinstance(document, dict):
        return False
    try:
        _detect_format(document)
    except NormalizationError:
        return False
    # The shape is recognized; also verify the document actually normalizes so
    # malformed decoys can never crash aggregation further down the pipeline.
    from q_guardian.analytics.normalizer import normalize

    try:
        normalize(document)
    except Exception:
        return False
    return True


def _mtime(path: Path) -> str:
    from datetime import UTC, datetime

    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return ""


def _safe_name(name: str) -> str:
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_.")
    return safe or "report"
