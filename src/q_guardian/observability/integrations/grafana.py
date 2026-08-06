"""Grafana integration adapter for Q-Guardian Observability."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.observability.enums import AlertSeverity, AlertState, HealthStatus
from q_guardian.observability.exceptions import ExporterError
from q_guardian.utils.uuid_utils import generate_uuid

if TYPE_CHECKING:
    from q_guardian.observability.data import Alert, HealthReport, Metric

logger = structlog.get_logger("observability.integrations.grafana")


class GrafanaIntegration:
    """Adapter that formats Q-Guardian data for Grafana dashboards and alerting."""

    def __init__(self, api_url: str = "", api_key: str = "") -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.name: str = "grafana"
        self._datasource_uid: str = "q-guardian-prometheus"
        logger.info("grafana_integration_initialized", api_url=api_url, has_key=bool(api_key))

    def format_metrics_for_dashboard(self, metrics: list[Metric]) -> dict[str, Any]:
        if not metrics:
            raise ExporterError(message="No metrics provided for Grafana dashboard formatting")

        targets = []
        for metric in metrics:
            target: dict[str, Any] = {
                "refId": metric.name[:2].upper(),
                "expr": f'{metric.name}{{job="q-guardian"}}',
                "legendFormat": metric.name,
                "datasource": {
                    "type": "prometheus",
                    "uid": self._datasource_uid,
                },
                "range": True,
                "instant": False,
                "format": "time_series",
            }
            targets.append(target)

        return {
            "targets": targets,
            "metric_count": len(metrics),
            "metric_names": [m.name for m in metrics],
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def format_alert_for_grafana(self, alert: Alert) -> dict[str, Any]:
        severity_map: dict[AlertSeverity, str] = {
            AlertSeverity.INFO: "info",
            AlertSeverity.LOW: "info",
            AlertSeverity.MEDIUM: "warning",
            AlertSeverity.HIGH: "critical",
            AlertSeverity.CRITICAL: "critical",
        }

        state_map: dict[AlertState, str] = {
            AlertState.PENDING: "alerting",
            AlertState.FIRING: "alerting",
            AlertState.ACKNOWLEDGED: "alerting",
            AlertState.SUPPRESSED: "suppressed",
            AlertState.RESOLVED: "ok",
            AlertState.ESCALATED: "alerting",
        }

        annotations: dict[str, str] = {
            "summary": alert.message or f"Alert {alert.rule_name}",
            "description": (
                f"Alert {alert.rule_name} is in state {alert.state.value} "
                f"with severity {alert.severity.value}"
            ),
        }
        annotations.update(alert.annotations)

        labels: dict[str, str] = {
            "alert_id": alert.alert_id,
            "rule_id": alert.rule_id,
            "rule_name": alert.rule_name,
            "severity": alert.severity.value,
            "state": alert.state.value,
        }
        labels.update(alert.labels)

        return {
            "alertName": f"qguardian_{alert.rule_name}",
            "state": state_map.get(alert.state, "alerting"),
            "severity": severity_map.get(alert.severity, "warning"),
            "message": alert.message,
            "labels": labels,
            "annotations": annotations,
            "startsAt": alert.created_at.isoformat(),
            "endsAt": alert.resolved_at.isoformat()
            if alert.resolved_at
            else "0001-01-01T00:00:00Z",
            "generatorURL": f"{self.api_url}/alerting/list",
            "fingerprint": alert.alert_id[:8],
        }

    def create_dashboard_model(self, title: str, metrics: list[Metric]) -> dict[str, Any]:
        if not metrics:
            raise ExporterError(message="No metrics provided for Grafana dashboard model")

        panels: list[dict[str, Any]] = []
        for idx, metric in enumerate(metrics):
            graph_type = "timeseries"
            if metric.points:
                values = [p.value for p in metric.points]
                if len(set(values)) == 1:
                    graph_type = "stat"

            panel: dict[str, Any] = {
                "id": idx + 1,
                "type": graph_type,
                "title": metric.name,
                "description": metric.description or f"Metric: {metric.name}",
                "datasource": {
                    "type": "prometheus",
                    "uid": self._datasource_uid,
                },
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "palette-classic"},
                        "unit": metric.unit.value,
                        "custom": {
                            "lineWidth": 1,
                            "fillOpacity": 20,
                            "pointSize": 5,
                            "showPoints": "auto",
                            "spanNulls": False,
                            "drawStyle": "line",
                            "gradientMode": "none",
                            "axisBorderShow": False,
                            "axisCenteredZero": False,
                            "axisColorMode": "text",
                            "axisLabel": metric.name,
                            "scaleDistribution": {"type": "linear"},
                        },
                    },
                    "overrides": [],
                },
                "options": {
                    "tooltip": {"mode": "single", "sort": "none"},
                    "legend": {"displayMode": "list", "placement": "bottom"},
                },
                "targets": [
                    {
                        "refId": "A",
                        "expr": f'{metric.name}{{job="q-guardian"}}',
                        "legendFormat": metric.name,
                        "datasource": {
                            "type": "prometheus",
                            "uid": self._datasource_uid,
                        },
                        "range": True,
                        "instant": False,
                    }
                ],
                "gridPos": {
                    "h": 8,
                    "w": 12,
                    "x": (idx % 2) * 12,
                    "y": (idx // 2) * 8,
                },
            }
            panels.append(panel)

        row_panels = []
        for idx in range(0, len(panels), 2):
            row_panel: dict[str, Any] = {
                "id": len(panels) + (idx // 2) + 1,
                "type": "row",
                "title": f"Metrics Row {(idx // 2) + 1}",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": idx * 4},
                "collapsed": False,
                "panels": [],
            }
            row_panels.append(row_panel)

        all_panels = row_panels + panels

        dashboard: dict[str, Any] = {
            "id": None,
            "uid": generate_uuid()[:8],
            "title": title,
            "description": f"Q-Guardian observability dashboard: {title}",
            "tags": ["q-guardian", "observability"],
            "timezone": "utc",
            "editable": True,
            "fiscalYearStartMonth": 0,
            "graphTooltip": 1,
            "refresh": "30s",
            "schemaVersion": 39,
            "templating": {"list": []},
            "time": {"from": "now-1h", "to": "now"},
            "timepicker": {},
            "version": 1,
            "panels": all_panels,
        }

        logger.info(
            "grafana_dashboard_created",
            title=title,
            panel_count=len(panels),
            metric_count=len(metrics),
        )
        return dashboard

    def format_health_for_grafana(self, health: HealthReport) -> dict[str, Any]:
        status_annotation_map: dict[HealthStatus, str] = {
            HealthStatus.HEALTHY: "Q-Guardian Health: All systems operational",
            HealthStatus.DEGRADED: "Q-Guardian Health: System degraded",
            HealthStatus.UNHEALTHY: "Q-Guardian Health: System unhealthy",
            HealthStatus.UNKNOWN: "Q-Guardian Health: Status unknown",
            HealthStatus.MAINTENANCE: "Q-Guardian Health: Under maintenance",
        }

        component_details: list[str] = []
        for comp in health.components:
            detail = f"  - {comp.component}: {comp.status.value} (score: {comp.health_score:.2f})"
            if comp.warnings:
                detail += f" [warnings: {len(comp.warnings)}]"
            if comp.failures:
                detail += f" [failures: {len(comp.failures)}]"
            component_details.append(detail)

        tags = ["q-guardian", "health"]
        tags.append(f"status:{health.overall_status.value}")

        return {
            "annotation": {
                "name": "Q-Guardian Health",
                "enabled": True,
                "datasource": {
                    "type": "prometheus",
                    "uid": self._datasource_uid,
                },
                "iconColor": self._status_to_color(health.overall_status),
                "icon": "Heart",
                "hideLinks": False,
            },
            "time": int(health.timestamp.timestamp() * 1000),
            "timeEnd": int(health.timestamp.timestamp() * 1000) + 1,
            "title": status_annotation_map.get(health.overall_status, "Q-Guardian Health Update"),
            "tags": tags,
            "text": (
                f"Overall Status: {health.overall_status.value}\n"
                f"Score: {health.overall_score:.2f}\n"
                f"Uptime: {health.framework_uptime_seconds:.0f}s\n"
                f"Active Warnings: {health.active_warnings}\n"
                f"Active Failures: {health.active_failures}\n"
                f"\nComponents:\n" + "\n".join(component_details)
            ),
        }

    def create_annotation(self, text: str, tags: list[str] | None = None) -> dict[str, Any]:
        annotation_tags = ["q-guardian"]
        if tags:
            annotation_tags.extend(tags)

        return {
            "annotation": {
                "name": "Q-Guardian",
                "enabled": True,
                "datasource": {
                    "type": "prometheus",
                    "uid": self._datasource_uid,
                },
                "iconColor": "#7EB26D",
                "icon": "Info",
                "hideLinks": False,
            },
            "time": int(datetime.now(UTC).timestamp() * 1000),
            "timeEnd": int(datetime.now(UTC).timestamp() * 1000) + 1,
            "title": "Q-Guardian Annotation",
            "tags": annotation_tags,
            "text": text,
        }

    def get_datasource_config(self) -> dict[str, Any]:
        return {
            "name": "Q-Guardian Prometheus",
            "type": "prometheus",
            "uid": self._datasource_uid,
            "access": "proxy",
            "url": self.api_url or "http://localhost:9090",
            "jsonData": {
                "timeInterval": "15s",
                "httpMethod": "POST",
                "exemplarTraceIdDestinations": [
                    {
                        "name": "traceID",
                        "datasourceUid": "tempo",
                    }
                ],
                "customQueryParameters": "",
            },
            "secureJsonFields": {},
            "isDefault": False,
            "readOnly": False,
            "withAdminCredentials": False,
            "version": 1,
            "orgId": 1,
        }

    @staticmethod
    def _status_to_color(status: HealthStatus) -> str:
        color_map: dict[HealthStatus, str] = {
            HealthStatus.HEALTHY: "#73BF69",
            HealthStatus.DEGRADED: "#FF9830",
            HealthStatus.UNHEALTHY: "#F2495C",
            HealthStatus.UNKNOWN: "#878787",
            HealthStatus.MAINTENANCE: "#5794F2",
        }
        return color_map.get(status, "#878787")
