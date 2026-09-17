"""Minimal background job store for long-running product operations.

Training runs, dataset preparation and security scans are CPU-bound and can
take well beyond a single HTTP request. The framework has no existing
asynchronous job infrastructure, so this module provides the smallest safe
mechanism compatible with the current architecture:

* Jobs run in the asyncio thread-pool executor (never blocking the event loop).
* Job records live in a bounded, thread-safe in-memory store.
* Every finished job is persisted as ``<job_id>.job.json`` inside its output
  directory, so completed work is readable after a server restart (disk-backed,
  MongoDB optional). Running jobs are intentionally not recovered — their
  partial artifacts remain on disk and the user can start a new run.
* Progress messages stream into the job record for the UI to poll.

No detection, training or dataset logic lives here — the runner only executes
injected callables.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.api.services import artifacts

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

logger = structlog.get_logger("api.jobs")

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_FAILED = "failed"

MAX_PROGRESS_LINES = 500
MAX_LIVE_JOBS = 200

# Where each job kind persists its ``<job_id>.job.json`` record.
_ROOT_BY_KIND: dict[str, Callable[[], Path]] = {
    "dataset.prepare": artifacts.datasets_root,
    "training.run": artifacts.training_root,
    "training.evaluate": artifacts.training_root,
    "scan.run": artifacts.scans_root,
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Job:
    """A single tracked background operation."""

    __slots__ = (
        "created_at",
        "error",
        "finished_at",
        "id",
        "kind",
        "label",
        "output_dir",
        "progress",
        "result",
        "started_at",
        "status",
    )

    def __init__(
        self,
        *,
        kind: str,
        label: str,
        job_id: str | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self.id = job_id or uuid.uuid4().hex[:12]
        self.kind = kind
        self.label = label
        self.status = JOB_STATUS_QUEUED
        self.created_at = _utc_now()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.progress: list[str] = []
        self.output_dir = str(output_dir) if output_dir else None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize the job (for the API and the on-disk record)."""
        return {
            "job_id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress": self.progress[-MAX_PROGRESS_LINES:],
            "output_dir": self.output_dir,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Restore a job from a persisted record."""
        job = cls(
            kind=str(data.get("kind", "")),
            label=str(data.get("label", "")),
            job_id=str(data.get("job_id", "")),
            output_dir=data.get("output_dir"),
        )
        job.status = str(data.get("status", JOB_STATUS_QUEUED))
        job.created_at = str(data.get("created_at", ""))
        job.started_at = data.get("started_at")
        job.finished_at = data.get("finished_at")
        job.error = data.get("error")
        job.result = data.get("result")
        job.progress = [str(line) for line in (data.get("progress") or [])]
        return job


class JobRunner:
    """Tracks and executes background jobs in the asyncio executor."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()

    def submit(
        self,
        *,
        kind: str,
        label: str,
        fn: Callable[[JobContext], dict[str, Any]],
        output_dir: str | Path | None = None,
    ) -> Job:
        """Queue ``fn`` and start it on the executor immediately.

        Args:
            kind: Job kind (drives where the record is persisted).
            label: Human-readable label shown in the console.
            fn: The worker callable; receives a ``JobContext`` and returns a
                JSON-serializable dict result.
            output_dir: Directory where ``<job_id>.job.json`` is written on
                completion (defaults to the kind's artifact root).

        Raises:
            RuntimeError: If called outside a running asyncio loop.
        """
        root = _ROOT_BY_KIND.get(kind)
        if output_dir is None and root is not None:
            output_dir = root()
        job = Job(kind=kind, label=label, output_dir=output_dir)
        with self._lock:
            self._prune_locked()
            self._jobs[job.id] = job
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            with self._lock:
                job.status = JOB_STATUS_FAILED
                job.error = "no running asyncio event loop"
                self._jobs.pop(job.id, None)
            msg = f"asyncio event loop required to start job {job.id}"
            raise RuntimeError(msg) from exc
        loop.run_in_executor(None, self._execute, job, fn)
        logger.info("job_submitted", job_id=job.id, kind=kind)
        return job

    def get(self, job_id: str) -> Job | None:
        """Return a live job, falling back to on-disk persisted records."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job
        for root_factory in (_ROOT_BY_KIND[item] for item in _ROOT_BY_KIND):
            record = self._load_record(root_factory(), job_id)
            if record is not None:
                return record
        return None

    def list(self, kinds: Iterable[str] | None = None) -> list[Job]:
        """Return live plus recovered jobs, newest first, optionally filtered."""
        requested = set(kinds) if kinds is not None else set(_ROOT_BY_KIND)
        seen: dict[str, Job] = {}

        def _merge(job: Job) -> None:
            if job.kind in requested:
                seen[job.id] = job

        with self._lock:
            for job in self._jobs.values():
                _merge(job)
        for kind in requested:
            root = _ROOT_BY_KIND.get(kind)
            if root is None:
                continue
            for record in self._iter_records(root()):
                _merge(record)
        def _finished_at(job: Job) -> str:
            return job.finished_at or job.created_at

        return sorted(seen.values(), key=_finished_at, reverse=True)

    @staticmethod
    def _iter_records(root: Path) -> list[Job]:
        if not root.is_dir():
            return []
        records: list[Job] = []
        for path in sorted(root.glob("*.job.json")):
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and data.get("job_id"):
                records.append(Job.from_dict(data))
        return records

    @staticmethod
    def _load_record(root: Path, job_id: str) -> Job | None:
        path = root / f"{job_id}.job.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(data, dict) and data.get("job_id") == job_id:
            return Job.from_dict(data)
        return None

    def _execute(
        self,
        job: Job,
        fn: Callable[[JobContext], dict[str, Any]],
    ) -> None:
        context = JobContext(job=job, lock=self._lock)
        with self._lock:
            job.status = JOB_STATUS_RUNNING
            job.started_at = _utc_now()
        try:
            result = fn(context)
            with self._lock:
                job.status = JOB_STATUS_SUCCEEDED
                job.result = result if isinstance(result, dict) else {"value": result}
        except Exception as exc:
            logger.exception("job_failed", job_id=job.id, kind=job.kind)
            with self._lock:
                job.status = JOB_STATUS_FAILED
                job.error = str(exc)
        finally:
            with self._lock:
                job.finished_at = _utc_now()
            self._persist(job)

    @staticmethod
    def _persist(job: Job) -> None:
        if not job.output_dir:
            return
        output = Path(job.output_dir)
        try:
            output.mkdir(parents=True, exist_ok=True)
            record = job.as_dict()
            (output / f"{job.id}.job.json").write_text(
                json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("job_persist_failed", job_id=job.id, error=str(exc))

    def _prune_locked(self) -> None:
        if len(self._jobs) <= MAX_LIVE_JOBS:
            return
        finished = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in {JOB_STATUS_SUCCEEDED, JOB_STATUS_FAILED}
        ]
        for job_id in finished[: len(self._jobs) - MAX_LIVE_JOBS]:
            self._jobs.pop(job_id, None)


class JobContext:
    """Handle a worker receives to report progress."""

    __slots__ = ("_job", "_lock")

    def __init__(self, job: Job, lock: threading.RLock) -> None:
        self._job = job
        self._lock = lock

    @property
    def job_id(self) -> str:
        """The unique id of the running job."""
        return self._job.id

    def progress(self, message: str) -> None:
        """Append a progress line to the job record."""
        with self._lock:
            self._job.progress.append(str(message))
            if len(self._job.progress) > MAX_PROGRESS_LINES:
                del self._job.progress[:-MAX_PROGRESS_LINES]

    @property
    def output_dir(self) -> Path | None:
        """Directory the job should write its artifacts into."""
        return Path(self._job.output_dir) if self._job.output_dir else None


_runner: JobRunner | None = None
_runner_lock = threading.Lock()


def get_job_runner() -> JobRunner:
    """Return the shared process-wide job runner."""
    global _runner
    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = JobRunner()
    return _runner
