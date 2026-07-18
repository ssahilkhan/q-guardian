"""ObservabilityStorage — persistence for observability data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from q_guardian.observability.data import Alert, AlertEvent, Metric, Trace
from q_guardian.observability.exceptions import StorageError

logger = structlog.get_logger("observability.storage")


class ObservabilityStorage:
    """File-based persistence for observability module data.

    Directory layout:
      storage_root/
        metrics/
        traces/
        alerts/
        alert_events/
        health/
        analytics/
    """

    def __init__(self, storage_root: str | Path | None = None) -> None:
        if storage_root is None:
            storage_root = Path("observability_storage")
        self._root = Path(storage_root)
        self._root.mkdir(parents=True, exist_ok=True)
        for subdir in ("metrics", "traces", "alerts", "alert_events", "health", "analytics"):
            (self._root / subdir).mkdir(exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def save_metric(self, metric: Metric) -> Path:
        path = self._root / "metrics" / f"{metric.metric_id}.json"
        data = metric.model_dump(mode="json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return path

    def load_metric(self, metric_id: str) -> dict[str, Any]:
        path = self._root / "metrics" / f"{metric_id}.json"
        if not path.exists():
            raise StorageError(f"Metric not found: {metric_id}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_metrics(self) -> list[str]:
        return [f.stem for f in (self._root / "metrics").glob("*.json")]

    def save_trace(self, trace: Trace) -> Path:
        path = self._root / "traces" / f"{trace.trace_id}.json"
        data = trace.model_dump(mode="json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return path

    def load_trace(self, trace_id: str) -> dict[str, Any]:
        path = self._root / "traces" / f"{trace_id}.json"
        if not path.exists():
            raise StorageError(f"Trace not found: {trace_id}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_traces(self) -> list[str]:
        return [f.stem for f in (self._root / "traces").glob("*.json")]

    def save_alert(self, alert: Alert) -> Path:
        path = self._root / "alerts" / f"{alert.alert_id}.json"
        data = alert.model_dump(mode="json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return path

    def load_alert(self, alert_id: str) -> dict[str, Any]:
        path = self._root / "alerts" / f"{alert_id}.json"
        if not path.exists():
            raise StorageError(f"Alert not found: {alert_id}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_alerts(self) -> list[str]:
        return [f.stem for f in (self._root / "alerts").glob("*.json")]

    def save_alert_event(self, event: AlertEvent) -> Path:
        path = self._root / "alert_events" / f"{event.event_id}.json"
        data = event.model_dump(mode="json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return path

    def list_alert_events(self) -> list[str]:
        return [f.stem for f in (self._root / "alert_events").glob("*.json")]

    def save_health_report(self, report: dict[str, Any]) -> Path:
        report_id = report.get("report_id", "latest")
        path = self._root / "health" / f"{report_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        return path

    def save_analytics_report(self, report: dict[str, Any]) -> Path:
        report_id = report.get("report_id", "latest")
        path = self._root / "analytics" / f"{report_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        return path

    def delete_metric(self, metric_id: str) -> bool:
        path = self._root / "metrics" / f"{metric_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def delete_trace(self, trace_id: str) -> bool:
        path = self._root / "traces" / f"{trace_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def delete_alert(self, alert_id: str) -> bool:
        path = self._root / "alerts" / f"{alert_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def get_storage_stats(self) -> dict[str, Any]:
        counts = {}
        for subdir in ("metrics", "traces", "alerts", "alert_events", "health", "analytics"):
            counts[subdir] = len(list((self._root / subdir).glob("*.json")))
        total_size = sum(
            f.stat().st_size for f in self._root.rglob("*.json") if f.is_file()
        )
        return {
            "storage_root": str(self._root),
            "counts": counts,
            "total_size_bytes": total_size,
        }
