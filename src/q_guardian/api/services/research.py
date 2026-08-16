"""Research artifact reader for the console UI.

Reads existing Q-Guardian research artifacts (JSONL datasets, trained model
storage, evaluation reports, benchmark suites, load-test results) so the
console can display real, on-disk data without re-running any analysis and
without exposing arbitrary filesystem access.

Every read is bounded: only well-known directories and filename patterns are
consulted and every file is capped by size. Binary model files are listed by
name/size/timestamp only — their contents are never deserialized.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_DATASET_BYTES = 100 * 1024 * 1024

_BENCHMARK_SUMMARY_KEYS = (
    "name",
    "iterations",
    "min_us",
    "avg_us",
    "p50_us",
    "p95_us",
    "p99_us",
    "max_us",
    "ops_per_sec",
)

_LOADTEST_SUMMARY_KEYS = (
    "scenario_name",
    "total_requests",
    "successful",
    "failed",
    "error_rate",
    "avg_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
    "peak_latency_ms",
    "throughput_rps",
    "duration_seconds",
    "memory_peak_mb",
    "memory_avg_mb",
)


def project_root() -> Path:
    """Resolve the directory that owns the research artifacts.

    Prefers the process working directory when it looks like the project root
    (so the server picks up artifacts written by scripts run from the repo),
    then falls back to the source-tree location of this package.
    """
    override = os.environ.get("QGUARDIAN_ARTIFACTS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    cwd = Path.cwd().resolve()
    if (cwd / "src" / "q_guardian").is_dir():
        return cwd
    return Path(__file__).resolve().parents[4]


def research_snapshot() -> dict[str, Any]:
    """Return a structured, read-only snapshot of research artifacts.

    Each top-level key maps to a page in the console Research section:
    datasets, model_artifacts, evaluation, benchmarks and loadtests.
    """
    root = project_root()
    return {
        "datasets": _read_datasets(root / "data"),
        "model_artifacts": _read_model_artifacts(root / "models" / "ml"),
        "evaluation": _read_evaluation(root / "docs" / "output" / "evaluation"),
        "benchmarks": _read_benchmarks(root / "scripts" / "benchmarks"),
        "loadtests": _read_loadtests(root / "scripts" / "loadtest" / "results"),
    }


def _count_lines(path: Path) -> int | None:
    """Count lines in a text file without loading it fully."""
    try:
        count = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in handle:
                count += 1
        return count
    except OSError:
        return None


def _first_line_keys(path: Path) -> list[str]:
    """Return the JSON keys of the first record, or an empty list."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            line = handle.readline()
        record = json.loads(line)
        if isinstance(record, dict):
            return sorted(record.keys())
        return []
    except (OSError, json.JSONDecodeError):
        return []


def _read_datasets(directory: Path) -> list[dict[str, Any]]:
    """Inventory JSONL datasets under ``data/``."""
    if not directory.is_dir():
        return []
    datasets: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.jsonl")):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > _MAX_DATASET_BYTES:
            datasets.append(
                {
                    "name": path.name,
                    "size": size,
                    "rows": None,
                    "fields": [],
                    "note": "file too large to inspect",
                }
            )
            continue
        datasets.append(
            {
                "name": path.name,
                "size": size,
                "rows": _count_lines(path),
                "fields": _first_line_keys(path),
                "note": None,
            }
        )
    return datasets


def _read_model_artifacts(directory: Path) -> list[dict[str, Any]]:
    """List trained model artifacts on disk without deserializing them."""
    if not directory.is_dir():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        artifacts.append(
            {
                "name": str(path.relative_to(directory)),
                "kind": path.suffix.lstrip(".") or "file",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
            }
        )
    return artifacts


def _read_evaluation(directory: Path) -> dict[str, Any]:
    """Read the evaluation report written by ``scripts/evaluate_pipeline.py``."""
    base: dict[str, Any] = {
        "present": False,
        "note": (
            "No evaluation report found (docs/output/evaluation/report.json). "
            "Run `python scripts/evaluate_pipeline.py` to generate one."
        ),
        "generated_at": None,
        "report": None,
        "scores_csv": False,
        "report_md": False,
    }
    report_path = directory / "report.json"
    if not report_path.is_file():
        return base
    try:
        stat = report_path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
    except OSError:
        return {**base, "note": "Evaluation report could not be read."}
    attached = {
        "scores_csv": (directory / "scores.csv").is_file(),
        "report_md": (directory / "report.md").is_file(),
    }
    if stat.st_size > _MAX_JSON_BYTES:
        return {
            "present": True,
            "note": "Evaluation report is too large to display.",
            "generated_at": modified,
            "report": None,
            **attached,
        }
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "present": True,
            "note": "Evaluation report could not be parsed as JSON.",
            "generated_at": modified,
            "report": None,
            **attached,
        }
    return {
        "present": True,
        "note": None,
        "generated_at": modified,
        "report": report,
        **attached,
    }


def _read_benchmarks(directory: Path) -> dict[str, Any]:
    """Read saved ``BenchmarkSuite`` JSON files from ``scripts/benchmarks/``."""
    if not directory.is_dir():
        return {"present": False, "suites": [], "note": None}
    suites: list[dict[str, Any]] = []
    skipped: list[str] = []
    for path in sorted(directory.glob("results_*.json")):
        try:
            if path.stat().st_size > _MAX_JSON_BYTES:
                skipped.append(path.name)
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped.append(path.name)
            continue
        rows = [
            {key: row.get(key) for key in _BENCHMARK_SUMMARY_KEYS}
            for row in data.get("results", [])
        ]
        suites.append({"file": path.name, "suite": data.get("suite", ""), "results": rows})
    note = None
    if skipped:
        note = f"Skipped unreadable files: {', '.join(sorted(skipped))}"
    return {"present": bool(suites), "suites": suites, "note": note}


def _read_loadtests(directory: Path) -> list[dict[str, Any]]:
    """Read load-test result JSON files from ``scripts/loadtest/results/``."""
    if not directory.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            if path.stat().st_size > _MAX_JSON_BYTES:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entry: dict[str, Any] = {"file": path.name}
        entry.update({key: data.get(key) for key in _LOADTEST_SUMMARY_KEYS})
        results.append(entry)
    return results
