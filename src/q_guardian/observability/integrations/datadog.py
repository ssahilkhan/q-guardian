"""Datadog integration adapter for Q-Guardian Observability."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.observability.enums import AlertSeverity, AlertState, HealthStatus
from q_guardian.observability.exceptions import ExporterError

if TYPE_CHECKING:
    from q_guardian.observability.data import Alert, HealthReport, Metric

logger = structlog.get_logger("observability.integrations.datadog")


class DatadogIntegration:
    """Adapter that formats Q-Guardian data for Datadog metrics and events."""

    def __init__(self, api_key: str = "", app_key: str = "", site: str = "datadoghq.com") -> None:
        self.api_key = api_key
        self.app_key = app_key
        self.site = site
        self.name: str = "datadog"
        self._series_api_url = f"https://api.{site}/api/v2/series"
        self._events_api_url = f"https://api.{site}/api/v1/events"
        self._service_check_url = f"https://api.{site}/api/v1/check_run"
        logger.info(
            "datadog_integration_initialized", site=site, has_keys=bool(api_key and app_key)
        )

    def format_metrics_for_datadog(self, metrics: list[Metric]) -> list[dict[str, Any]]:
        if not metrics:
            raise ExporterError(message="No metrics provided for Datadog formatting")

        series: list[dict[str, Any]] = []
        for metric in metrics:
            points: list[list[float | int]] = []
            for point in metric.points:
                ts = int(point.timestamp.timestamp())
                points.append([ts, point.value])

            if not points:
                default_ts = int(datetime.now(UTC).timestamp())
                default_val = metric.latest_value()
                if default_val is not None:
                    points = [[default_ts, default_val]]

            series_entry: dict[str, Any] = {
                "metric": f"qguardian.{metric.name}",
                "type": self._map_metric_type(metric.metric_type.value),
                "points": points,
                "tags": [f"metric_id:{metric.metric_id}"],
                "unit": metric.unit.value,
                "metadata": {
                    "metric_description": metric.description,
                    "metric_type_original": metric.metric_type.value,
                },
            }

            for key, val in metric.labels.items():
                series_entry["tags"].append(f"{key}:{val}")

            series.append(series_entry)

        logger.info("datadog_metrics_formatted", series_count=len(series))
        return series

    def format_alert_for_datadog(self, alert: Alert) -> dict[str, Any]:
        severity_priority: dict[AlertSeverity, int] = {
            AlertSeverity.INFO: 1,
            AlertSeverity.LOW: 2,
            AlertSeverity.MEDIUM: 3,
            AlertSeverity.HIGH: 4,
            AlertSeverity.CRITICAL: 5,
        }

        alert_type_map: dict[AlertState, str] = {
            AlertState.PENDING: "warning",
            AlertState.FIRING: "error",
            AlertState.ACKNOWLEDGED: "warning",
            AlertState.SUPPRESSED: "info",
            AlertState.RESOLVED: "success",
            AlertState.ESCALATED: "error",
        }

        tags: list[str] = [
            f"alert_id:{alert.alert_id}",
            f"rule_id:{alert.rule_id}",
            f"severity:{alert.severity.value}",
            f"state:{alert.state.value}",
        ]
        for key, val in alert.labels.items():
            tags.append(f"{key}:{val}")

        event_payload: dict[str, Any] = {
            "title": f"[Q-Guardian] {alert.rule_name}",
            "text": alert.message
            or f"Alert {alert.rule_name} triggered with severity {alert.severity.value}",
            "alert_type": alert_type_map.get(alert.state, "warning"),
            "date_happened": int(alert.created_at.timestamp()),
            "priority": str(severity_priority.get(alert.severity, 3)),
            "tags": tags,
            "aggregation_key": f"qguardian_{alert.rule_name}",
            "source_type_name": "q-guardian",
            "host": "q-guardian-framework",
            "related_event_id": alert.alert_id,
            "hostname": "q-guardian",
            "msg_title": f"Q-Guardian Alert: {alert.rule_name}",
            "msg_text": alert.message,
        }

        if alert.resolved_at:
            event_payload["date_happened"] = int(alert.resolved_at.timestamp())
            event_payload["alert_type"] = "success"
            event_payload["is_priority"] = False

        return event_payload

    def create_metric_payload(
        self, name: str, points: list[tuple[int, float]], tags: list[str] | None = None
    ) -> dict[str, Any]:
        base_tags: list[str] = ["source:q-guardian"]
        if tags:
            base_tags.extend(tags)

        return {
            "series": [
                {
                    "metric": f"qguardian.{name}",
                    "type": "gauge",
                    "points": [[ts, val] for ts, val in points],
                    "tags": base_tags,
                    "unit": "none",
                }
            ]
        }

    def create_event_payload(
        self,
        title: str,
        text: str,
        alert_type: str = "info",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        base_tags: list[str] = ["source:q-guardian"]
        if tags:
            base_tags.extend(tags)

        valid_alert_types = {"info", "warning", "error", "success"}
        if alert_type not in valid_alert_types:
            alert_type = "info"

        return {
            "title": title,
            "text": text,
            "alert_type": alert_type,
            "date_happened": int(datetime.now(UTC).timestamp()),
            "tags": base_tags,
            "source_type_name": "q-guardian",
            "host": "q-guardian-framework",
            "priority": "normal",
        }

    def format_health_for_datadog(self, health: HealthReport) -> dict[str, Any]:
        status_service_check: dict[HealthStatus, str] = {
            HealthStatus.HEALTHY: "ok",
            HealthStatus.DEGRADED: "warning",
            HealthStatus.UNHEALTHY: "critical",
            HealthStatus.UNKNOWN: "unknown",
            HealthStatus.MAINTENANCE: "ok",
        }

        check_name = "q_guardian.health"
        overall_status = status_service_check.get(health.overall_status, "unknown")

        messages: list[str] = [
            f"Overall: {health.overall_status.value} (score: {health.overall_score:.2f})",
            f"Uptime: {health.framework_uptime_seconds:.0f}s",
            f"Warnings: {health.active_warnings}",
            f"Failures: {health.active_failures}",
        ]

        for comp in health.components:
            comp_status = status_service_check.get(comp.status, "unknown")
            messages.append(f"  {comp.component}: {comp_status} ({comp.health_score:.2f})")

        tags = [
            f"status:{health.overall_status.value}",
            f"score:{health.overall_score:.2f}",
        ]

        return {
            "check": check_name,
            "status": overall_status,
            "message": "\n".join(messages),
            "tags": tags,
            "timestamp": int(health.timestamp.timestamp()),
            "host_name": "q-guardian-framework",
            "interval": 60,
        }

    def create_service_check(
        self,
        name: str,
        status: str,
        message: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        valid_statuses = {"ok", "warning", "critical", "unknown"}
        if status not in valid_statuses:
            status = "unknown"

        base_tags: list[str] = ["source:q-guardian"]
        if tags:
            base_tags.extend(tags)

        return {
            "check": f"q_guardian.{name}",
            "status": status,
            "message": message,
            "tags": base_tags,
            "timestamp": int(datetime.now(UTC).timestamp()),
            "host_name": "q-guardian-framework",
            "interval": 60,
        }

    @staticmethod
    def _map_metric_type(metric_type: str) -> str:
        type_map: dict[str, str] = {
            "counter": "count",
            "gauge": "gauge",
            "histogram": "distribution",
            "timer": "gauge",
        }
        return type_map.get(metric_type, "gauge")
