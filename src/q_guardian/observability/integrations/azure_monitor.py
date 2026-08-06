"""Azure Monitor integration adapter for Q-Guardian Observability."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.observability.enums import (
    AlertSeverity,
    AlertState,
    HealthStatus,
)
from q_guardian.observability.exceptions import ExporterError
from q_guardian.utils.uuid_utils import generate_uuid

if TYPE_CHECKING:
    from q_guardian.observability.data import Alert, HealthReport, Metric

logger = structlog.get_logger("observability.integrations.azure_monitor")

SEVERITY_MAP: dict[AlertSeverity, int] = {
    AlertSeverity.INFO: 4,
    AlertSeverity.LOW: 3,
    AlertSeverity.MEDIUM: 2,
    AlertSeverity.HIGH: 1,
    AlertSeverity.CRITICAL: 0,
}

METRIC_TYPE_AZURE: dict[str, str] = {
    "counter": "Sum",
    "gauge": "Average",
    "histogram": "Average",
    "timer": "Average",
}

SEVERITY_NAMES: dict[AlertSeverity, str] = {
    AlertSeverity.INFO: "Informational",
    AlertSeverity.LOW: "Low",
    AlertSeverity.MEDIUM: "Medium",
    AlertSeverity.HIGH: "High",
    AlertSeverity.CRITICAL: "Critical",
}


class AzureMonitorIntegration:
    """Adapter that formats Q-Guardian data for Azure Monitor."""

    def __init__(self, workspace_id: str = "", instrumentation_key: str = "") -> None:
        self.workspace_id = workspace_id
        self.instrumentation_key = instrumentation_key
        self.name: str = "azure_monitor"
        self._api_version = "2018-03-28"
        logger.info(
            "azure_monitor_integration_initialized",
            has_workspace=bool(workspace_id),
            has_ikey=bool(instrumentation_key),
        )

    def format_metrics_for_azure(self, metrics: list[Metric]) -> list[dict[str, Any]]:
        if not metrics:
            raise ExporterError(message="No metrics provided for Azure Monitor formatting")

        entries: list[dict[str, Any]] = []
        for metric in metrics:
            for point in metric.points:
                entry: dict[str, Any] = {
                    "metric": metric.name,
                    "namespace": "QGuardian",
                    "dimNames": list(metric.labels.keys()) + list(point.labels.keys()),
                    "series": [
                        {
                            "dimValues": list(metric.labels.values()) + list(point.labels.values()),
                            "min": point.value,
                            "max": point.value,
                            "sum": point.value,
                            "count": 1,
                        }
                    ],
                    "time": point.timestamp.isoformat(),
                    "top": 1,
                }
                entries.append(entry)

        logger.info("azure_monitor_metrics_formatted", entry_count=len(entries))
        return entries

    def format_alert_for_azure(self, alert: Alert) -> dict[str, Any]:
        severity_name = SEVERITY_NAMES.get(alert.severity, "Medium")
        severity_number = SEVERITY_MAP.get(alert.severity, 2)

        condition: dict[str, Any] = {
            "allOf": [
                {
                    "query": f"QGuardianMetrics | where name == '{alert.rule_name}'",
                    "timeAggregation": "Average",
                    "operator": "GreaterThan",
                    "threshold": alert.evaluation_value or 0,
                    "failingPeriods": {
                        "numberOfEvaluationPeriods": 1,
                        "minFailingPeriodsToAlert": 1,
                    },
                }
            ],
        }

        return {
            "alertId": alert.alert_id,
            "ruleName": f"QGuardian/{alert.rule_name}",
            "severity": severity_name,
            "severityNumber": severity_number,
            "status": self._map_azure_alert_state(alert.state),
            "description": alert.message or f"Q-Guardian alert: {alert.rule_name}",
            "condition": condition,
            "resolvedTime": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "triggeredTime": alert.created_at.isoformat(),
            "lastModifiedTime": alert.updated_at.isoformat(),
            "context": {
                "ruleId": alert.rule_id,
                "alertType": alert.alert_type.value,
                "escalationLevel": alert.escalation_level,
                "evaluationValue": alert.evaluation_value,
            },
            "labels": {
                "source": "q-guardian",
                "severity": alert.severity.value,
                "state": alert.state.value,
                **alert.labels,
            },
            "annotations": {
                "summary": alert.message,
                "description": f"Alert {alert.rule_name} in state {alert.state.value}",
                **alert.annotations,
            },
        }

    def create_metric_entry(
        self,
        name: str,
        value: float,
        namespace: str = "QGuardian",
        dimensions: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        dims = dimensions or {}

        return {
            "metric": {
                "name": name,
                "namespace": namespace,
                "dimNames": list(dims.keys()),
                "series": [
                    {
                        "dimValues": list(dims.values()),
                        "min": value,
                        "max": value,
                        "sum": value,
                        "count": 1,
                    }
                ],
            },
            "time": datetime.now(UTC).isoformat(),
            "top": 1,
        }

    def create_log_entry(
        self,
        severity: str,
        message: str,
        properties: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        valid_severities = {"Information", "Warning", "Error", "Critical", "Verbose"}
        if severity not in valid_severities:
            severity = "Information"

        entry_properties: dict[str, str] = {
            "Source": "QGuardian",
            "Timestamp": datetime.now(UTC).isoformat(),
        }
        if properties:
            entry_properties.update(properties)

        return {
            "severity": severity,
            "message": message,
            "properties": entry_properties,
            "time": datetime.now(UTC).isoformat(),
            "_type": "Microsoft.Insights/Logs",
            "instrumentationKey": self.instrumentation_key,
            "workspaceId": self.workspace_id,
        }

    def format_health_for_azure(self, health: HealthReport) -> dict[str, Any]:
        severity_map: dict[HealthStatus, str] = {
            HealthStatus.HEALTHY: "Information",
            HealthStatus.DEGRADED: "Warning",
            HealthStatus.UNHEALTHY: "Error",
            HealthStatus.UNKNOWN: "Warning",
            HealthStatus.MAINTENANCE: "Information",
        }

        component_metrics: list[dict[str, Any]] = []
        for comp in health.components:
            component_metrics.append(
                {
                    "metric": f"QGuardian.ComponentHealth/{comp.component}",
                    "namespace": "QGuardian",
                    "dimNames": ["component", "status"],
                    "series": [
                        {
                            "dimValues": [comp.component, comp.status.value],
                            "min": comp.health_score,
                            "max": comp.health_score,
                            "sum": comp.health_score,
                            "count": 1,
                        }
                    ],
                    "time": health.timestamp.isoformat(),
                    "top": 1,
                }
            )

        overall_metric = {
            "metric": "QGuardian.OverallHealth",
            "namespace": "QGuardian",
            "dimNames": ["status"],
            "series": [
                {
                    "dimValues": [health.overall_status.value],
                    "min": health.overall_score,
                    "max": health.overall_score,
                    "sum": health.overall_score,
                    "count": 1,
                }
            ],
            "time": health.timestamp.isoformat(),
            "top": 1,
        }

        log_entry = self.create_log_entry(
            severity=severity_map.get(health.overall_status, "Warning"),
            message=(
                f"Q-Guardian Health: {health.overall_status.value} "
                f"(score: {health.overall_score:.2f}, "
                f"warnings: {health.active_warnings}, "
                f"failures: {health.active_failures})"
            ),
            properties={
                "ReportId": health.report_id,
                "OverallStatus": health.overall_status.value,
                "OverallScore": str(
                    health.health_score if hasattr(health, "health_score") else health.overall_score
                ),
                "Uptime": str(health.framework_uptime_seconds),
                "ComponentCount": str(len(health.components)),
            },
        )

        return {
            "metrics": [overall_metric, *component_metrics],
            "logEntry": log_entry,
            "report": {
                "reportId": health.report_id,
                "overallStatus": health.overall_status.value,
                "overallScore": health.overall_score,
                "componentCount": len(health.components),
                "activeWarnings": health.active_warnings,
                "activeFailures": health.active_failures,
                "frameworkUptimeSeconds": health.framework_uptime_seconds,
                "timestamp": health.timestamp.isoformat(),
            },
        }

    def create_trace_entry(
        self,
        name: str,
        duration_ms: float,
        success: bool = True,
        properties: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        trace_id = generate_uuid()
        span_id = generate_uuid()[:16]
        now = datetime.now(UTC)

        trace_properties: dict[str, str] = {
            "Source": "QGuardian",
            "OperationName": name,
            "DurationMs": str(duration_ms),
            "Success": str(success).lower(),
            "TraceId": trace_id,
            "SpanId": span_id,
        }
        if properties:
            trace_properties.update(properties)

        status_code = 0 if success else 2

        return {
            "traceId": trace_id,
            "spanId": span_id,
            "operationName": name,
            "startTime": now.isoformat(),
            "duration": int(duration_ms * 1000),
            "success": success,
            "resultType": status_code,
            "properties": trace_properties,
            "_type": "Microsoft.ApplicationInsights/Request",
            "instrumentationKey": self.instrumentation_key,
        }

    @staticmethod
    def _map_azure_alert_state(state: AlertState) -> str:
        state_map: dict[AlertState, str] = {
            AlertState.PENDING: "Firing",
            AlertState.FIRING: "Firing",
            AlertState.ACKNOWLEDGED: "Firing",
            AlertState.SUPPRESSED: "Suppressed",
            AlertState.RESOLVED: "Resolved",
            AlertState.ESCALATED: "Firing",
        }
        return state_map.get(state, "Firing")
