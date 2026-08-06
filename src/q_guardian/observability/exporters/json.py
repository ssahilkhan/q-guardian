from __future__ import annotations

import json as _json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.observability.enums import ExporterType
from q_guardian.observability.exceptions import ExporterError
from q_guardian.utils.uuid_utils import generate_uuid

if TYPE_CHECKING:
    from q_guardian.observability.data import Metric

logger = structlog.get_logger("observability.exporters.json")

_EXPORT_VERSION = "1.0.0"


class JsonExporter:
    name: str = "json"
    exporter_type: ExporterType = ExporterType.JSON

    def __init__(self, indent: int = 2, include_metadata: bool = True) -> None:
        self._indent = indent
        self._include_metadata = include_metadata
        self._logger = logger.bind(exporter=self.name)

    def export_metrics(self, metrics: list[Metric]) -> str:
        try:
            data: dict[str, Any] = {
                "metrics": [
                    {
                        "metric_id": m.metric_id,
                        "name": m.name,
                        "metric_type": m.metric_type.value,
                        "unit": m.unit.value,
                        "description": m.description,
                        "labels": m.labels,
                        "points": [
                            {
                                "timestamp": p.timestamp.isoformat(),
                                "value": p.value,
                                "labels": p.labels,
                            }
                            for p in m.points
                        ],
                    }
                    for m in metrics
                ]
            }
            if self._include_metadata:
                data = self._add_metadata(data)
            result = _json.dumps(data, indent=self._indent, default=str)
            self._logger.debug(
                "json_metrics_exported",
                metric_count=len(metrics),
                size=len(result),
            )
            return result
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("json_metrics_export_failed", error=str(exc))
            raise ExporterError(
                message=f"JSON metrics export failed: {exc}",
                details={"metric_count": len(metrics)},
            ) from exc

    def export_trace(self, trace: dict[str, Any]) -> str:
        try:
            data: dict[str, Any] = {"trace": trace}
            if self._include_metadata:
                data = self._add_metadata(data)
            result = _json.dumps(data, indent=self._indent, default=str)
            self._logger.debug(
                "json_trace_exported",
                trace_id=trace.get("trace_id", "unknown"),
                size=len(result),
            )
            return result
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("json_trace_export_failed", error=str(exc))
            raise ExporterError(
                message=f"JSON trace export failed: {exc}",
                details={"trace_id": trace.get("trace_id")},
            ) from exc

    def export_alerts(self, alerts: list[dict[str, Any]]) -> str:
        try:
            data: dict[str, Any] = {"alerts": alerts}
            if self._include_metadata:
                data = self._add_metadata(data)
            result = _json.dumps(data, indent=self._indent, default=str)
            self._logger.debug(
                "json_alerts_exported",
                alert_count=len(alerts),
                size=len(result),
            )
            return result
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("json_alerts_export_failed", error=str(exc))
            raise ExporterError(
                message=f"JSON alerts export failed: {exc}",
                details={"alert_count": len(alerts)},
            ) from exc

    def export_health(self, health: dict[str, Any]) -> str:
        try:
            data: dict[str, Any] = {"health": health}
            if self._include_metadata:
                data = self._add_metadata(data)
            result = _json.dumps(data, indent=self._indent, default=str)
            self._logger.debug(
                "json_health_exported",
                size=len(result),
            )
            return result
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("json_health_export_failed", error=str(exc))
            raise ExporterError(
                message=f"JSON health export failed: {exc}",
            ) from exc

    def export_all(self, data: dict[str, Any]) -> str:
        try:
            payload = data.copy()
            if self._include_metadata:
                payload = self._add_metadata(payload)
            result = _json.dumps(payload, indent=self._indent, default=str)
            self._logger.debug(
                "json_all_exported",
                size=len(result),
                keys=list(data.keys()),
            )
            return result
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("json_all_export_failed", error=str(exc))
            raise ExporterError(
                message=f"JSON export failed: {exc}",
            ) from exc

    def _add_metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        enriched = data.copy()
        enriched["_metadata"] = {
            "exported_at": datetime.now(UTC).isoformat(),
            "exporter": self.name,
            "version": _EXPORT_VERSION,
            "export_id": generate_uuid(),
        }
        return enriched
