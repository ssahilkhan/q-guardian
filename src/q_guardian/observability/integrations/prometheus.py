"""Prometheus remote write integration adapter for Q-Guardian Observability."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.observability.enums import (
    AlertState,
    HealthStatus,
)
from q_guardian.observability.exceptions import ExporterError
from q_guardian.utils.uuid_utils import generate_uuid

if TYPE_CHECKING:
    from q_guardian.observability.data import Alert, HealthReport, Metric

logger = structlog.get_logger("observability.integrations.prometheus")


class PrometheusIntegration:
    """Adapter that formats Q-Guardian data for Prometheus remote write and Alertmanager."""

    def __init__(
        self,
        remote_write_url: str = "",
        basic_auth_user: str = "",
        basic_auth_password: str = "",
    ) -> None:
        self.remote_write_url = remote_write_url
        self.basic_auth_user = basic_auth_user
        self.basic_auth_password = basic_auth_password
        self.name: str = "prometheus"
        self._job_label = "q-guardian"
        self._instance_label = f"q-guardian-{generate_uuid()[:8]}"
        logger.info(
            "prometheus_integration_initialized",
            has_url=bool(remote_write_url),
            has_auth=bool(basic_auth_user),
        )

    def format_metrics_for_remote_write(self, metrics: list[Metric]) -> dict[str, Any]:
        if not metrics:
            raise ExporterError(message="No metrics provided for Prometheus remote write")

        timeseries: list[dict[str, Any]] = []
        for metric in metrics:
            metric_type_label = metric.metric_type.value

            labels: dict[str, str] = {
                "__name__": f"qguardian_{metric.name}",
                "job": self._job_label,
                "instance": self._instance_label,
                "metric_type": metric_type_label,
                "metric_id": metric.metric_id,
            }
            labels.update(metric.labels)

            for point in metric.points:
                point_labels = {**labels}
                point_labels.update({f"label_{k}": v for k, v in point.labels.items()})

                sample: dict[str, Any] = {
                    "labels": point_labels,
                    "value": self._format_sample_value(point.value),
                    "timestamp": int(point.timestamp.timestamp() * 1000),
                }
                timeseries.append(sample)

            if (
                not timeseries
                or timeseries[-1].get("labels", {}).get("__name__") != f"qguardian_{metric.name}"
            ):
                default_val = metric.latest_value()
                if default_val is not None:
                    sample = {
                        "labels": labels,
                        "value": self._format_sample_value(default_val),
                        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                    }
                    timeseries.append(sample)

        payload: dict[str, Any] = {
            "timeseries": timeseries,
            "metadata": {
                "metricCount": len(metrics),
                "sampleCount": len(timeseries),
                "remoteWriteUrl": self.remote_write_url,
                "generatedAt": datetime.now(UTC).isoformat(),
            },
        }

        logger.info("prometheus_remote_write_formatted", timeseries_count=len(timeseries))
        return payload

    def create_write_request(self, metrics: list[Metric]) -> dict[str, Any]:
        if not metrics:
            raise ExporterError(message="No metrics provided for Prometheus write request")

        timeseries: list[dict[str, Any]] = []
        for metric in metrics:
            labels: dict[str, str] = {
                "__name__": f"qguardian_{metric.name}",
                "job": self._job_label,
                "instance": self._instance_label,
            }
            labels.update(metric.labels)

            samples: list[dict[str, Any]] = []
            for point in metric.points:
                samples.append(
                    {
                        "value": self._format_sample_value(point.value),
                        "timestamp": int(point.timestamp.timestamp() * 1000),
                    }
                )

            if not samples:
                default_val = metric.latest_value()
                if default_val is not None:
                    samples = [
                        {
                            "value": self._format_sample_value(default_val),
                            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                        }
                    ]

            timeseries.append(
                {
                    "labels": labels,
                    "exemplars": [],
                    "samples": samples,
                }
            )

        return {
            "request": {
                "timeseries": timeseries,
            },
            "headers": {
                "Content-Type": "application/x-protobuf",
                "X-Prometheus-Remote-Write-Version": "2.0.0",
            },
            "endpoint": self.remote_write_url,
            "metadata": {
                "metricCount": len(metrics),
                "timeseriesCount": len(timeseries),
                "requestId": generate_uuid(),
                "createdAt": datetime.now(UTC).isoformat(),
            },
        }

    def format_alertmanager_payload(self, alerts: list[Alert]) -> list[dict[str, Any]]:
        if not alerts:
            return []

        payload: list[dict[str, Any]] = []
        for alert in alerts:
            labels: dict[str, str] = {
                "alertname": f"qguardian_{alert.rule_name}",
                "severity": alert.severity.value,
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "job": self._job_label,
                "instance": self._instance_label,
            }
            labels.update(alert.labels)

            annotations: dict[str, str] = {
                "summary": alert.message or f"Q-Guardian alert: {alert.rule_name}",
                "description": (
                    f"Alert {alert.rule_name} is in state {alert.state.value} "
                    f"with severity {alert.severity.value}"
                ),
                "alert_type": alert.alert_type.value,
            }
            annotations.update(alert.annotations)

            starts_at = alert.created_at.isoformat()
            if alert.created_at.tzinfo is None:
                starts_at = alert.created_at.replace(tzinfo=UTC).isoformat()

            ends_at = None
            if alert.resolved_at:
                ends_at = alert.resolved_at.isoformat()
                if alert.resolved_at.tzinfo is None:
                    ends_at = alert.resolved_at.replace(tzinfo=UTC).isoformat()

            alert_entry: dict[str, Any] = {
                "labels": labels,
                "annotations": annotations,
                "startsAt": starts_at,
                "generatorURL": "http://q-guardian:9090/alerts",
                "fingerprint": alert.alert_id[:8],
                "status": {
                    "state": self._map_alertmanager_state(alert.state),
                    "silencedBy": [],
                    "inhibitedBy": [],
                },
            }

            if ends_at:
                alert_entry["endsAt"] = ends_at

            payload.append(alert_entry)

        logger.info("alertmanager_payload_formatted", alert_count=len(payload))
        return payload

    def create_prometheus_rule(
        self,
        name: str,
        query: str,
        severity: str = "warning",
        for_duration: str = "5m",
    ) -> dict[str, Any]:
        rule_name = f"qguardian_{name}"

        return {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusRule",
            "metadata": {
                "name": rule_name,
                "namespace": "q-guardian",
                "labels": {
                    "app.kubernetes.io/name": "q-guardian",
                    "app.kubernetes.io/component": "observability",
                    "prometheus": "q-guardian",
                    "role": "alert-rules",
                    "severity": severity,
                },
                "annotations": {
                    "prometheus.io/rule": "true",
                },
            },
            "spec": {
                "groups": [
                    {
                        "name": f"qguardian.{name}.rules",
                        "interval": "30s",
                        "rules": [
                            {
                                "alert": rule_name,
                                "expr": query,
                                "for": for_duration,
                                "labels": {
                                    "severity": severity,
                                    "job": self._job_label,
                                    "instance": self._instance_label,
                                },
                                "annotations": {
                                    "summary": f"Q-Guardian alert: {name}",
                                    "description": (
                                        f"Q-Guardian rule '{name}' has been "
                                        f"firing for {for_duration}"
                                    ),
                                },
                            }
                        ],
                    }
                ]
            },
        }

    def format_health_for_prometheus(self, health: HealthReport) -> dict[str, Any]:
        status_value_map: dict[HealthStatus, float] = {
            HealthStatus.HEALTHY: 1.0,
            HealthStatus.DEGRADED: 0.5,
            HealthStatus.UNHEALTHY: 0.0,
            HealthStatus.UNKNOWN: -1.0,
            HealthStatus.MAINTENANCE: 0.75,
        }

        lines: list[str] = []
        lines.append("# HELP qguardian_health_overall_score Overall health score of Q-Guardian")
        lines.append("# TYPE qguardian_health_overall_score gauge")
        lines.append(
            f"qguardian_health_overall_score "
            f'{{job="{self._job_label}",instance="{self._instance_label}"}} '
            f"{health.overall_score}"
        )

        lines.append(
            "# HELP qguardian_health_overall_status_code Overall health status as numeric code"
        )
        lines.append("# TYPE qguardian_health_overall_status_code gauge")
        overall_code = status_value_map.get(health.overall_status, -1.0)
        lines.append(
            f"qguardian_health_overall_status_code "
            f'{{job="{self._job_label}",instance="{self._instance_label}",'
            f'status="{health.overall_status.value}"}} '
            f"{overall_code}"
        )

        lines.append("# HELP qguardian_health_uptime_seconds Framework uptime in seconds")
        lines.append("# TYPE qguardian_health_uptime_seconds gauge")
        lines.append(
            f"qguardian_health_uptime_seconds "
            f'{{job="{self._job_label}",instance="{self._instance_label}"}} '
            f"{health.framework_uptime_seconds}"
        )

        lines.append("# HELP qguardian_health_active_warnings Number of active warnings")
        lines.append("# TYPE qguardian_health_active_warnings gauge")
        lines.append(
            f"qguardian_health_active_warnings "
            f'{{job="{self._job_label}",instance="{self._instance_label}"}} '
            f"{health.active_warnings}"
        )

        lines.append("# HELP qguardian_health_active_failures Number of active failures")
        lines.append("# TYPE qguardian_health_active_failures gauge")
        lines.append(
            f"qguardian_health_active_failures "
            f'{{job="{self._job_label}",instance="{self._instance_label}"}} '
            f"{health.active_failures}"
        )

        lines.append("# HELP qguardian_health_component_score Health score per component")
        lines.append("# TYPE qguardian_health_component_score gauge")
        for comp in health.components:
            lines.append(
                f"qguardian_health_component_score "
                f'{{job="{self._job_label}",instance="{self._instance_label}",'
                f'component="{comp.component}",status="{comp.status.value}"}} '
                f"{comp.health_score}"
            )

        lines.append("# HELP qguardian_health_component_warnings Number of warnings per component")
        lines.append("# TYPE qguardian_health_component_warnings gauge")
        for comp in health.components:
            lines.append(
                f"qguardian_health_component_warnings "
                f'{{job="{self._job_label}",instance="{self._instance_label}",'
                f'component="{comp.component}"}} '
                f"{len(comp.warnings)}"
            )

        lines.append("# HELP qguardian_health_component_failures Number of failures per component")
        lines.append("# TYPE qguardian_health_component_failures gauge")
        for comp in health.components:
            lines.append(
                f"qguardian_health_component_failures "
                f'{{job="{self._job_label}",instance="{self._instance_label}",'
                f'component="{comp.component}"}} '
                f"{len(comp.failures)}"
            )

        exposition_text = "\n".join(lines) + "\n"

        return {
            "exposition": exposition_text,
            "format": "prometheus",
            "contentType": "text/plain; version=0.0.4; charset=utf-8",
            "reportId": health.report_id,
            "timestamp": health.timestamp.isoformat(),
            "metadata": {
                "overallStatus": health.overall_status.value,
                "overallScore": health.overall_score,
                "componentCount": len(health.components),
            },
        }

    @staticmethod
    def _format_sample_value(value: float) -> str:
        if value != value:
            return "NaN"
        if value == float("inf"):
            return "+Inf"
        if value == float("-inf"):
            return "-Inf"
        return f"{value:.6f}"

    @staticmethod
    def _map_alertmanager_state(state: AlertState) -> str:
        state_map: dict[AlertState, str] = {
            AlertState.PENDING: "active",
            AlertState.FIRING: "active",
            AlertState.ACKNOWLEDGED: "active",
            AlertState.SUPPRESSED: "suppressed",
            AlertState.RESOLVED: "unprocessed",
            AlertState.ESCALATED: "active",
        }
        return state_map.get(state, "active")
