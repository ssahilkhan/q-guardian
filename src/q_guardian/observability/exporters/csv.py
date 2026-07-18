from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

import structlog

from q_guardian.observability.data import Metric
from q_guardian.observability.enums import ExporterType
from q_guardian.observability.exceptions import ExporterError
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("observability.exporters.csv")

_EXPORT_VERSION = "1.0.0"


class CsvExporter:
    name: str = "csv"
    exporter_type: ExporterType = ExporterType.CSV

    def __init__(self, delimiter: str = ",") -> None:
        self._delimiter = delimiter
        self._logger = logger.bind(exporter=self.name)

    def export_metrics(self, metrics: list[Metric]) -> str:
        try:
            headers, rows = self._metrics_to_rows(metrics)
            output = io.StringIO()
            writer = csv.writer(output, delimiter=self._delimiter)
            writer.writerow(headers)
            writer.writerows(rows)
            result = output.getvalue()
            self._logger.debug(
                "csv_metrics_exported",
                metric_count=len(metrics),
                row_count=len(rows),
                size=len(result),
            )
            return result
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("csv_metrics_export_failed", error=str(exc))
            raise ExporterError(
                message=f"CSV metrics export failed: {exc}",
                details={"metric_count": len(metrics)},
            ) from exc

    def export_alerts(self, alerts: list[dict[str, Any]]) -> str:
        try:
            headers, rows = self._alerts_to_rows(alerts)
            output = io.StringIO()
            writer = csv.writer(output, delimiter=self._delimiter)
            writer.writerow(headers)
            writer.writerows(rows)
            result = output.getvalue()
            self._logger.debug(
                "csv_alerts_exported",
                alert_count=len(alerts),
                row_count=len(rows),
                size=len(result),
            )
            return result
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("csv_alerts_export_failed", error=str(exc))
            raise ExporterError(
                message=f"CSV alerts export failed: {exc}",
                details={"alert_count": len(alerts)},
            ) from exc

    def export_traces(self, traces: list[dict[str, Any]]) -> str:
        try:
            headers = [
                "trace_id",
                "correlation_id",
                "status",
                "start_time",
                "end_time",
                "duration_ms",
                "span_count",
                "labels",
            ]
            rows: list[list[str]] = []
            for trace in traces:
                duration = trace.get("duration_ms")
                rows.append([
                    trace.get("trace_id", ""),
                    trace.get("correlation_id", ""),
                    trace.get("status", ""),
                    trace.get("start_time", ""),
                    trace.get("end_time", ""),
                    str(duration) if duration is not None else "",
                    str(trace.get("span_count", 0)),
                    _json_dumps(trace.get("labels", {})),
                ])
            output = io.StringIO()
            writer = csv.writer(output, delimiter=self._delimiter)
            writer.writerow(headers)
            writer.writerows(rows)
            result = output.getvalue()
            self._logger.debug(
                "csv_traces_exported",
                trace_count=len(traces),
                row_count=len(rows),
                size=len(result),
            )
            return result
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("csv_traces_export_failed", error=str(exc))
            raise ExporterError(
                message=f"CSV traces export failed: {exc}",
                details={"trace_count": len(traces)},
            ) from exc

    def _metrics_to_rows(
        self, metrics: list[Metric]
    ) -> tuple[list[str], list[list[str]]]:
        headers = [
            "metric_id",
            "name",
            "metric_type",
            "unit",
            "description",
            "timestamp",
            "value",
            "labels",
        ]
        rows: list[list[str]] = []
        for metric in metrics:
            if metric.points:
                for point in metric.points:
                    merged = {**metric.labels, **point.labels} if point.labels else metric.labels
                    rows.append([
                        metric.metric_id,
                        metric.name,
                        metric.metric_type.value,
                        metric.unit.value,
                        metric.description,
                        point.timestamp.isoformat(),
                        str(point.value),
                        _json_dumps(merged),
                    ])
            else:
                latest = metric.latest_value()
                rows.append([
                    metric.metric_id,
                    metric.name,
                    metric.metric_type.value,
                    metric.unit.value,
                    metric.description,
                    datetime.now(UTC).isoformat(),
                    str(latest) if latest is not None else "",
                    _json_dumps(metric.labels),
                ])
        return headers, rows

    def _alerts_to_rows(
        self, alerts: list[dict[str, Any]]
    ) -> tuple[list[str], list[list[str]]]:
        headers = [
            "alert_id",
            "rule_id",
            "rule_name",
            "state",
            "severity",
            "alert_type",
            "message",
            "created_at",
            "updated_at",
            "resolved_at",
            "evaluation_value",
            "escalation_level",
            "labels",
            "annotations",
        ]
        rows: list[list[str]] = []
        for alert in alerts:
            rows.append([
                alert.get("alert_id", ""),
                alert.get("rule_id", ""),
                alert.get("rule_name", ""),
                alert.get("state", ""),
                alert.get("severity", ""),
                alert.get("alert_type", ""),
                alert.get("message", ""),
                alert.get("created_at", ""),
                alert.get("updated_at", ""),
                alert.get("resolved_at", "") or "",
                str(alert.get("evaluation_value", "")) if alert.get("evaluation_value") is not None else "",
                str(alert.get("escalation_level", 0)),
                _json_dumps(alert.get("labels", {})),
                _json_dumps(alert.get("annotations", {})),
            ])
        return headers, rows


def _json_dumps(data: Any) -> str:
    import json
    return json.dumps(data, default=str)
