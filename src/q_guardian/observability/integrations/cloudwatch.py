"""AWS CloudWatch integration adapter for Q-Guardian Observability."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog

from q_guardian.observability.data import Alert, HealthReport, Metric
from q_guardian.observability.enums import (
    AlertSeverity,
    AlertState,
    ExporterType,
    HealthStatus,
    MetricType,
    MetricUnit,
)
from q_guardian.observability.exceptions import ExporterError
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("observability.integrations.cloudwatch")

CLOUDWATCH_UNIT_MAP: dict[MetricUnit, str] = {
    MetricUnit.NONE: "None",
    MetricUnit.COUNT: "Count",
    MetricUnit.PERCENTAGE: "Percent",
    MetricUnit.SECONDS: "Seconds",
    MetricUnit.MILLISECONDS: "Milliseconds",
    MetricUnit.MICROSECONDS: "Microseconds",
    MetricUnit.BYTES: "Bytes",
    MetricUnit.KILOBYTES: "Kilobytes",
    MetricUnit.MEGABYTES: "Megabytes",
    MetricUnit.REQUESTS_PER_SECOND: "Count/Second",
    MetricUnit.PER_SECOND: "Count/Second",
}

METRIC_TYPE_CLOUDWATCH: dict[str, str] = {
    "counter": "CumulativeCount",
    "gauge": "Gauge",
    "histogram": "StatisticSet",
    "timer": "Gauge",
}

ALERT_TYPE_MAP: dict[AlertState, str] = {
    AlertState.PENDING: "info",
    AlertState.FIRING: "danger",
    AlertState.ACKNOWLEDGED: "warning",
    AlertState.SUPPRESSED: "info",
    AlertState.RESOLVED: "ok",
    AlertState.ESCALATED: "critical",
}


class CloudWatchIntegration:
    """Adapter that formats Q-Guardian data for AWS CloudWatch."""

    def __init__(self, region: str = "us-east-1", namespace: str = "QGuardian") -> None:
        self.region = region
        self.namespace = namespace
        self.name: str = "cloudwatch"
        self._log_group = "/aws/q-guardian/observability"
        self._log_stream = f"q-guardian-{generate_uuid()[:8]}"
        logger.info("cloudwatch_integration_initialized", region=region, namespace=namespace)

    def format_metrics_for_cloudwatch(self, metrics: list[Metric]) -> dict[str, Any]:
        if not metrics:
            raise ExporterError(message="No metrics provided for CloudWatch formatting")

        metric_data: list[dict[str, Any]] = []
        for metric in metrics:
            for point in metric.points:
                dimensions: dict[str, str] = {"MetricName": metric.name}
                dimensions.update(metric.labels)
                dimensions.update(point.labels)

                unit = CLOUDWATCH_UNIT_MAP.get(metric.unit, "None")
                cloudwatch_type = METRIC_TYPE_CLOUDWATCH.get(metric.metric_type.value, "Gauge")

                entry: dict[str, Any] = {
                    "MetricName": metric.name,
                    "Dimensions": [
                        {"Name": k, "Value": v} for k, v in dimensions.items()
                    ],
                    "Timestamp": point.timestamp,
                    "Value": point.value,
                    "Unit": unit,
                    "StorageResolution": 1,
                }

                if cloudwatch_type == "CumulativeCount":
                    entry["StorageResolution"] = 60

                metric_data.append(entry)

        payload: dict[str, Any] = {
            "Namespace": self.namespace,
            "MetricData": metric_data,
        }

        logger.info("cloudwatch_metrics_formatted", metric_data_count=len(metric_data))
        return payload

    def format_alert_for_cloudwatch(self, alert: Alert) -> dict[str, Any]:
        severity_detail: dict[AlertSeverity, dict[str, str]] = {
            AlertSeverity.INFO: {"color": "#5bc0de", "awsSeverity": "INFO"},
            AlertSeverity.LOW: {"color": "#5bc0de", "awsSeverity": "INFO"},
            AlertSeverity.MEDIUM: {"color": "#f0ad4e", "awsSeverity": "WARNING"},
            AlertSeverity.HIGH: {"color": "#d9534f", "awsSeverity": "ERROR"},
            AlertSeverity.CRITICAL: {"color": "#d9534f", "awsSeverity": "CRITICAL"},
        }

        detail_info = severity_detail.get(alert.severity, {"color": "#f0ad4e", "awsSeverity": "WARNING"})
        alert_type = ALERT_TYPE_MAP.get(alert.state, "info")

        resources: list[dict[str, str]] = [
            {
                "type": "QGuardianAlert",
                "id": alert.alert_id,
                "arn": f"arn:aws:q-guardian:{self.region}:alert/{alert.rule_name}",
                "details": {
                    "ruleId": alert.rule_id,
                    "ruleName": alert.rule_name,
                    "severity": alert.severity.value,
                    "state": alert.state.value,
                    "alertType": alert.alert_type.value,
                },
            }
        ]

        return {
            "version": "0",
            "id": alert.alert_id,
            "source": "q-guardian",
            "account": "q-guardian-account",
            "time": alert.created_at.isoformat(),
            "region": self.region,
            "resources": resources,
            "detail-type": f"Q-Guardian Alert: {alert.rule_name}",
            "detail": {
                "alertId": alert.alert_id,
                "ruleName": alert.rule_name,
                "ruleId": alert.rule_id,
                "severity": alert.severity.value,
                "awsSeverity": detail_info["awsSeverity"],
                "state": alert.state.value,
                "type": alert_type,
                "message": alert.message,
                "description": (
                    f"Q-Guardian alert '{alert.rule_name}' "
                    f"in state {alert.state.value} "
                    f"with severity {alert.severity.value}"
                ),
                "evaluationValue": alert.evaluation_value,
                "escalationLevel": alert.escalation_level,
                "createdAt": alert.created_at.isoformat(),
                "updatedAt": alert.updated_at.isoformat(),
                "resolvedAt": alert.resolved_at.isoformat() if alert.resolved_at else None,
                "labels": alert.labels,
                "annotations": alert.annotations,
            },
        }

    def create_metric_data(
        self,
        name: str,
        value: float,
        unit: str = "None",
        dimensions: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        dim_list: list[dict[str, str]] = [{"Name": "Source", "Value": "QGuardian"}]
        if dimensions:
            for k, v in dimensions.items():
                dim_list.append({"Name": k, "Value": v})

        return {
            "MetricName": name,
            "Dimensions": dim_list,
            "Timestamp": datetime.now(UTC),
            "Value": value,
            "Unit": unit,
            "StorageResolution": 1,
        }

    def create_event_pattern(self, detail_type: str, source: str = "q-guardian") -> dict[str, Any]:
        return {
            "source": [source],
            "detail-type": [detail_type],
            "account": [],
            "region": [self.region],
            "detail": {
                "source": [source],
            },
        }

    def format_health_for_cloudwatch(self, health: HealthReport) -> dict[str, Any]:
        status_alarm_map: dict[HealthStatus, dict[str, str]] = {
            HealthStatus.HEALTHY: {"state": "OK", "reason": "All systems healthy"},
            HealthStatus.DEGRADED: {"state": "ALARM", "reason": "System degraded"},
            HealthStatus.UNHEALTHY: {"state": "ALARM", "reason": "System unhealthy"},
            HealthStatus.UNKNOWN: {"state": "INSUFFICIENT_DATA", "reason": "Status unknown"},
            HealthStatus.MAINTENANCE: {"state": "OK", "reason": "Under maintenance"},
        }

        alarm_info = status_alarm_map.get(
            health.overall_status,
            {"state": "INSUFFICIENT_DATA", "reason": "Status unknown"},
        )

        metric_data: list[dict[str, Any]] = [
            {
                "MetricName": "OverallHealthScore",
                "Dimensions": [{"Name": "Source", "Value": "QGuardian"}],
                "Timestamp": health.timestamp,
                "Value": health.overall_score,
                "Unit": "Percent",
                "StorageResolution": 1,
            },
            {
                "MetricName": "ActiveWarnings",
                "Dimensions": [{"Name": "Source", "Value": "QGuardian"}],
                "Timestamp": health.timestamp,
                "Value": float(health.active_warnings),
                "Unit": "Count",
                "StorageResolution": 1,
            },
            {
                "MetricName": "ActiveFailures",
                "Dimensions": [{"Name": "Source", "Value": "QGuardian"}],
                "Timestamp": health.timestamp,
                "Value": float(health.active_failures),
                "Unit": "Count",
                "StorageResolution": 1,
            },
        ]

        for comp in health.components:
            metric_data.append({
                "MetricName": f"ComponentHealth.{comp.component}",
                "Dimensions": [
                    {"Name": "Source", "Value": "QGuardian"},
                    {"Name": "Component", "Value": comp.component},
                ],
                "Timestamp": health.timestamp,
                "Value": comp.health_score,
                "Unit": "Percent",
                "StorageResolution": 1,
            })

        alarm_event = {
            "version": "0",
            "id": health.report_id,
            "source": "q-guardian",
            "account": "q-guardian-account",
            "time": health.timestamp.isoformat(),
            "region": self.region,
            "resources": [],
            "detail-type": "Q-Guardian Health Report",
            "detail": {
                "reportId": health.report_id,
                "overallStatus": health.overall_status.value,
                "overallScore": health.overall_score,
                "alarmState": alarm_info["state"],
                "alarmReason": alarm_info["reason"],
                "componentCount": len(health.components),
                "activeWarnings": health.active_warnings,
                "activeFailures": health.active_failures,
                "frameworkUptimeSeconds": health.framework_uptime_seconds,
                "components": [
                    {
                        "name": c.component,
                        "status": c.status.value,
                        "score": c.health_score,
                        "warnings": len(c.warnings),
                        "failures": len(c.failures),
                    }
                    for c in health.components
                ],
            },
        }

        return {
            "metricData": metric_data,
            "alarmEvent": alarm_event,
            "logGroup": self._log_group,
            "logStream": self._log_stream,
        }

    def create_log_event(
        self, message: str, timestamp: datetime | None = None
    ) -> dict[str, Any]:
        ts = timestamp or datetime.now(UTC)

        return {
            "logGroupName": self._log_group,
            "logStreamName": self._log_stream,
            "logEvents": [
                {
                    "timestamp": int(ts.timestamp() * 1000),
                    "message": message,
                }
            ],
        }
