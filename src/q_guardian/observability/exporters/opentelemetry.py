from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.observability.enums import ExporterType
from q_guardian.observability.exceptions import ExporterError
from q_guardian.utils.uuid_utils import generate_uuid

if TYPE_CHECKING:
    from q_guardian.observability.data import Metric

logger = structlog.get_logger("observability.exporters.opentelemetry")

_EXPORT_VERSION = "1.0.0"
_OTLP_SCHEMA_URL = "https://opentelemetry.io/schemas/1.21.0"


class OpenTelemetryExporter:
    name: str = "opentelemetry"
    exporter_type: ExporterType = ExporterType.OPENTELEMETRY

    def __init__(
        self,
        service_name: str = "q-guardian",
        endpoint: str | None = None,
    ) -> None:
        self._service_name = service_name
        self._endpoint = endpoint
        self._logger = logger.bind(
            exporter=self.name,
            service_name=service_name,
        )

    def export_metrics(self, metrics: list[Metric]) -> dict[str, Any]:
        try:
            resource = self._create_resource()
            now_ns = int(datetime.now(UTC).timestamp() * 1e9)
            metric_data: list[dict[str, Any]] = []
            for metric in metrics:
                points = metric.points
                if not points:
                    latest = metric.latest_value()
                    if latest is not None:
                        point = self._create_metric_point(
                            metric_name=metric.name,
                            value=latest,
                            metric_type=metric.metric_type.value,
                            labels=metric.labels or None,
                        )
                        point["timeUnixNano"] = str(now_ns)
                        metric_data.append(
                            self._create_metric(
                                metric.name,
                                metric.description,
                                metric.metric_type.value,
                                [point],
                            )
                        )
                else:
                    otlp_points = []
                    for p in points:
                        merged = {**metric.labels, **p.labels} if p.labels else metric.labels
                        pt = self._create_metric_point(
                            metric_name=metric.name,
                            value=p.value,
                            metric_type=metric.metric_type.value,
                            labels=merged or None,
                        )
                        pt["timeUnixNano"] = str(int(p.timestamp.timestamp() * 1e9))
                        otlp_points.append(pt)
                    metric_data.append(
                        self._create_metric(
                            metric.name,
                            metric.description,
                            metric.metric_type.value,
                            otlp_points,
                        )
                    )
            payload: dict[str, Any] = {
                "resourceMetrics": [
                    {
                        "resource": resource,
                        "scopeMetrics": [
                            {
                                "scope": {
                                    "name": "q-guardian-observability",
                                    "version": _EXPORT_VERSION,
                                },
                                "metrics": metric_data,
                            }
                        ],
                    }
                ],
                "schemaUrl": _OTLP_SCHEMA_URL,
            }
            self._logger.debug(
                "opentelemetry_metrics_exported",
                metric_count=len(metrics),
            )
            return payload
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("opentelemetry_metrics_export_failed", error=str(exc))
            raise ExporterError(
                message=f"OpenTelemetry metrics export failed: {exc}",
                details={"metric_count": len(metrics)},
            ) from exc

    def export_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        try:
            resource = self._create_resource()
            trace_id = trace.get("trace_id", generate_uuid())
            spans = trace.get("spans", [])
            otlp_spans: list[dict[str, Any]] = []
            for span_data in spans:
                otlp_span: dict[str, Any] = {
                    "traceId": trace_id.replace("-", ""),
                    "spanId": span_data.get("span_id", generate_uuid()).replace("-", ""),
                    "name": span_data.get("name", "unknown"),
                    "kind": self._map_span_kind(span_data.get("kind", "internal")),
                    "startTimeUnixNano": str(
                        int(
                            datetime.fromisoformat(
                                span_data.get(
                                    "start_time",
                                    datetime.now(UTC).isoformat(),
                                )
                            ).timestamp()
                            * 1e9
                        )
                    ),
                    "status": {
                        "code": span_data.get("status", {}).get("code", 1),
                        "message": span_data.get("status", {}).get("message", ""),
                    },
                    "attributes": self._flatten_attributes(span_data.get("attributes", {})),
                    "events": [],
                }
                if span_data.get("end_time"):
                    otlp_span["endTimeUnixNano"] = str(
                        int(datetime.fromisoformat(span_data["end_time"]).timestamp() * 1e9)
                    )
                if span_data.get("parent_span_id"):
                    otlp_span["parentSpanId"] = span_data["parent_span_id"].replace("-", "")
                for event in span_data.get("events", []):
                    otlp_span["events"].append(
                        {
                            "name": event.get("name", ""),
                            "timeUnixNano": str(
                                int(
                                    datetime.fromisoformat(
                                        event.get(
                                            "timestamp",
                                            datetime.now(UTC).isoformat(),
                                        )
                                    ).timestamp()
                                    * 1e9
                                )
                            ),
                            "attributes": self._flatten_attributes(event.get("attributes", {})),
                        }
                    )
                otlp_spans.append(otlp_span)
            payload: dict[str, Any] = {
                "resourceSpans": [
                    {
                        "resource": resource,
                        "scopeSpans": [
                            {
                                "scope": {
                                    "name": "q-guardian-observability",
                                    "version": _EXPORT_VERSION,
                                },
                                "spans": otlp_spans,
                            }
                        ],
                    }
                ],
                "schemaUrl": _OTLP_SCHEMA_URL,
            }
            self._logger.debug(
                "opentelemetry_trace_exported",
                trace_id=trace_id,
                span_count=len(otlp_spans),
            )
            return payload
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error(
                "opentelemetry_trace_export_failed",
                error=str(exc),
                trace_id=trace.get("trace_id", "unknown"),
            )
            raise ExporterError(
                message=f"OpenTelemetry trace export failed: {exc}",
                details={"trace_id": trace.get("trace_id")},
            ) from exc

    def export_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        try:
            now_ns = str(int(datetime.now(UTC).timestamp() * 1e9))
            alert_id = alert.get("alert_id", generate_uuid())
            severity_map = {
                "info": 5,
                "low": 8,
                "medium": 10,
                "high": 13,
                "critical": 21,
            }
            severity_number = severity_map.get(alert.get("severity", "medium"), 10)
            event: dict[str, Any] = {
                "name": f"alert.{alert.get('state', 'unknown')}",
                "timeUnixNano": now_ns,
                "attributes": [
                    {"key": "alert.alert_id", "value": {"stringValue": alert_id}},
                    {"key": "alert.rule_id", "value": {"stringValue": alert.get("rule_id", "")}},
                    {
                        "key": "alert.rule_name",
                        "value": {"stringValue": alert.get("rule_name", "")},
                    },
                    {"key": "alert.state", "value": {"stringValue": alert.get("state", "unknown")}},
                    {
                        "key": "alert.severity",
                        "value": {"stringValue": alert.get("severity", "medium")},
                    },
                    {"key": "alert.severity_number", "value": {"intValue": str(severity_number)}},
                    {"key": "alert.message", "value": {"stringValue": alert.get("message", "")}},
                    {
                        "key": "alert.alert_type",
                        "value": {"stringValue": alert.get("alert_type", "threshold")},
                    },
                ],
            }
            if alert.get("labels"):
                for k, v in alert["labels"].items():
                    event["attributes"].append(
                        {
                            "key": f"alert.label.{k}",
                            "value": {"stringValue": v},
                        }
                    )
            if alert.get("annotations"):
                for k, v in alert["annotations"].items():
                    event["attributes"].append(
                        {
                            "key": f"alert.annotation.{k}",
                            "value": {"stringValue": v},
                        }
                    )
            payload: dict[str, Any] = {
                "resourceLogs": [
                    {
                        "resource": self._create_resource(),
                        "scopeLogs": [
                            {
                                "scope": {
                                    "name": "q-guardian-alerts",
                                    "version": _EXPORT_VERSION,
                                },
                                "logRecords": [
                                    {
                                        "timeUnixNano": now_ns,
                                        "severityNumber": severity_number,
                                        "severityText": alert.get("severity", "medium").upper(),
                                        "body": {"stringValue": alert.get("message", "")},
                                        "attributes": event["attributes"],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "schemaUrl": _OTLP_SCHEMA_URL,
            }
            self._logger.debug(
                "opentelemetry_alert_exported",
                alert_id=alert_id,
                state=alert.get("state", "unknown"),
            )
            return payload
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error(
                "opentelemetry_alert_export_failed",
                error=str(exc),
                alert_id=alert.get("alert_id", "unknown"),
            )
            raise ExporterError(
                message=f"OpenTelemetry alert export failed: {exc}",
                details={"alert_id": alert.get("alert_id")},
            ) from exc

    def _create_resource(self) -> dict[str, Any]:
        return {
            "attributes": [
                {
                    "key": "service.name",
                    "value": {"stringValue": self._service_name},
                },
                {
                    "key": "service.version",
                    "value": {"stringValue": _EXPORT_VERSION},
                },
                {
                    "key": "telemetry.sdk.name",
                    "value": {"stringValue": "q-guardian"},
                },
                {
                    "key": "telemetry.sdk.language",
                    "value": {"stringValue": "python"},
                },
                {
                    "key": "export.timestamp",
                    "value": {"stringValue": datetime.now(UTC).isoformat()},
                },
            ]
        }

    def _create_metric_point(
        self,
        metric_name: str,
        value: float,
        metric_type: str,
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        otlp_labels = [
            {"key": "metric.name", "value": {"stringValue": metric_name}},
        ]
        if labels:
            for k, v in labels.items():
                otlp_labels.append(
                    {
                        "key": k,
                        "value": {"stringValue": v},
                    }
                )
        point: dict[str, Any] = {}
        if metric_type == "counter":
            point = {
                "attributes": otlp_labels,
                "asDouble": value,
                "startTimeUnixNano": str(int(datetime.now(UTC).timestamp() * 1e9)),
            }
        elif metric_type == "gauge":
            point = {
                "attributes": otlp_labels,
                "asDouble": value,
                "timeUnixNano": str(int(datetime.now(UTC).timestamp() * 1e9)),
            }
        elif metric_type == "histogram":
            point = {
                "attributes": otlp_labels,
                "count": 1,
                "sum": value,
                "bucketCounts": ["0", "1"],
                "explicitBounds": [value],
                "timeUnixNano": str(int(datetime.now(UTC).timestamp() * 1e9)),
            }
        else:
            point = {
                "attributes": otlp_labels,
                "asDouble": value,
                "timeUnixNano": str(int(datetime.now(UTC).timestamp() * 1e9)),
            }
        return point

    def _create_metric(
        self,
        name: str,
        description: str,
        metric_type: str,
        data_points: list[dict[str, Any]],
    ) -> dict[str, Any]:
        otlp_type_map = {
            "counter": "sum",
            "gauge": "gauge",
            "histogram": "histogram",
            "timer": "histogram",
        }
        otlp_type = otlp_type_map.get(metric_type, "gauge")
        metric: dict[str, Any] = {
            "name": name,
            "description": description,
        }
        if otlp_type == "sum":
            metric["sum"] = {
                "dataPoints": data_points,
                "aggregationTemporality": 2,
                "isMonotonic": True,
            }
        elif otlp_type == "histogram":
            metric["histogram"] = {
                "dataPoints": data_points,
                "aggregationTemporality": 2,
            }
        else:
            metric["gauge"] = {
                "dataPoints": data_points,
            }
        return metric

    def _map_span_kind(self, kind: str) -> int:
        kind_map = {
            "internal": 0,
            "server": 1,
            "client": 2,
            "producer": 3,
            "consumer": 4,
        }
        return kind_map.get(kind.lower(), 0)

    def _flatten_attributes(self, attrs: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for k, v in attrs.items():
            if isinstance(v, str):
                result.append({"key": k, "value": {"stringValue": v}})
            elif isinstance(v, bool):
                result.append({"key": k, "value": {"boolValue": v}})
            elif isinstance(v, int):
                result.append({"key": k, "value": {"intValue": str(v)}})
            elif isinstance(v, float):
                result.append({"key": k, "value": {"doubleValue": v}})
            else:
                result.append({"key": k, "value": {"stringValue": str(v)}})
        return result
