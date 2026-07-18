from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

import structlog

logger = structlog.get_logger("observability.dashboard.serializers")


class DashboardSerializer:
    def __init__(self) -> None:
        pass

    def serialize_metric(self, metric: dict[str, Any]) -> dict[str, Any]:
        return {
            "metric_id": metric.get("metric_id", ""),
            "name": metric.get("name", ""),
            "type": metric.get("metric_type", metric.get("type", "unknown")),
            "unit": metric.get("unit", "none"),
            "description": metric.get("description", ""),
            "labels": metric.get("labels", {}),
            "latest_value": metric.get("latest_value"),
            "point_count": metric.get("point_count", 0),
            "points": [
                self._serialize_metric_point(p) for p in metric.get("points", [])
            ],
        }

    def serialize_health(self, health: dict[str, Any]) -> dict[str, Any]:
        return {
            "component": health.get("component", ""),
            "status": health.get("status", "unknown"),
            "health_score": health.get("health_score", 0.0),
            "level": health.get("level", "unknown"),
            "last_heartbeat": self.format_timestamp(health["last_heartbeat"])
            if health.get("last_heartbeat")
            else None,
            "uptime_seconds": health.get("uptime_seconds", 0.0),
            "warnings": health.get("warnings", []),
            "failures": health.get("failures", []),
            "dependencies": health.get("dependencies", {}),
            "metadata": health.get("metadata", {}),
        }

    def serialize_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        return {
            "alert_id": alert.get("alert_id", ""),
            "rule_id": alert.get("rule_id", ""),
            "rule_name": alert.get("rule_name", ""),
            "state": alert.get("state", "unknown"),
            "severity": alert.get("severity", "medium"),
            "alert_type": alert.get("alert_type", "threshold"),
            "message": alert.get("message", ""),
            "labels": alert.get("labels", {}),
            "annotations": alert.get("annotations", {}),
            "created_at": self.format_timestamp(alert["created_at"])
            if alert.get("created_at")
            else None,
            "updated_at": self.format_timestamp(alert["updated_at"])
            if alert.get("updated_at")
            else None,
            "resolved_at": self.format_timestamp(alert["resolved_at"])
            if alert.get("resolved_at")
            else None,
            "acknowledged_at": self.format_timestamp(alert["acknowledged_at"])
            if alert.get("acknowledged_at")
            else None,
            "acknowledged_by": alert.get("acknowledged_by"),
            "evaluation_value": alert.get("evaluation_value"),
            "escalation_level": alert.get("escalation_level", 0),
            "duration_seconds": alert.get("duration_seconds", 0.0),
        }

    def serialize_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        return {
            "trace_id": trace.get("trace_id", ""),
            "correlation_id": trace.get("correlation_id", ""),
            "execution_id": trace.get("execution_id", ""),
            "status": trace.get("status", "active"),
            "start_time": self.format_timestamp(trace["start_time"])
            if trace.get("start_time")
            else None,
            "end_time": self.format_timestamp(trace["end_time"])
            if trace.get("end_time")
            else None,
            "duration_ms": trace.get("duration_ms"),
            "span_count": trace.get("span_count", 0),
            "labels": trace.get("labels", {}),
            "metadata": trace.get("metadata", {}),
        }

    def serialize_analytics(self, analytics: dict[str, Any]) -> dict[str, Any]:
        return {
            "report_id": analytics.get("report_id", ""),
            "title": analytics.get("title", ""),
            "generated_at": self.format_timestamp(analytics["generated_at"])
            if analytics.get("generated_at")
            else None,
            "time_window": analytics.get("time_window"),
            "threat_trends": analytics.get("threat_trends", []),
            "policy_trends": analytics.get("policy_trends", []),
            "risk_trends": analytics.get("risk_trends", []),
            "response_trends": analytics.get("response_trends", []),
            "provider_accuracy": analytics.get("provider_accuracy", {}),
            "plugin_usage": analytics.get("plugin_usage", {}),
            "quantum_usage": analytics.get("quantum_usage", {}),
            "fusion_strategy_usage": analytics.get("fusion_strategy_usage", {}),
            "average_confidence": analytics.get("average_confidence", 0.0),
            "top_threat_types": analytics.get("top_threat_types", []),
            "top_policies": analytics.get("top_policies", []),
            "most_active_sessions": analytics.get("most_active_sessions", []),
            "most_active_agents": analytics.get("most_active_agents", []),
            "forecasts": [
                self._serialize_forecast(f) for f in analytics.get("forecasts", [])
            ],
            "summary": analytics.get("summary", {}),
        }

    def serialize_plugin(self, plugin: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": plugin.get("name", ""),
            "version": plugin.get("version", ""),
            "author": plugin.get("author", ""),
            "description": plugin.get("description", ""),
            "interfaces": plugin.get("interfaces", []),
            "enabled": plugin.get("enabled", True),
            "metadata": plugin.get("metadata", {}),
        }

    def serialize_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "snapshot_id": snapshot.get("snapshot_id", ""),
            "timestamp": self.format_timestamp(snapshot["timestamp"])
            if snapshot.get("timestamp")
            else None,
            "runtime": snapshot.get("runtime", {}),
            "performance": snapshot.get("performance", {}),
            "health": snapshot.get("health", {}),
            "resources": snapshot.get("resources", {}),
            "active_alerts_count": snapshot.get("active_alerts_count", 0),
            "recent_alerts": [
                self.serialize_alert(a) for a in snapshot.get("recent_alerts", [])
            ],
            "top_metrics": snapshot.get("top_metrics", []),
            "metadata": snapshot.get("metadata", {}),
        }

    def serialize_list(
        self,
        items: list[dict[str, Any]],
        serializer: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in items:
            try:
                result.append(serializer(item))
            except Exception as e:
                logger.error(
                    "serialization_error",
                    error=str(e),
                    item_type=type(item).__name__,
                )
                result.append(item)
        return result

    def format_timestamp(self, dt: datetime | str | None) -> str:
        if dt is None:
            return ""
        if isinstance(dt, str):
            return dt
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()

    def _serialize_metric_point(self, point: dict[str, Any]) -> dict[str, Any]:
        return {
            "timestamp": self.format_timestamp(point.get("timestamp")),
            "value": point.get("value", 0.0),
            "labels": point.get("labels", {}),
        }

    def _serialize_forecast(self, forecast: dict[str, Any]) -> dict[str, Any]:
        return {
            "metric_name": forecast.get("metric_name", ""),
            "method": forecast.get("method", "linear"),
            "confidence_level": forecast.get("confidence_level", 0.95),
            "forecast_values": forecast.get("forecast_values", []),
            "confidence_interval_lower": forecast.get("confidence_interval_lower", []),
            "confidence_interval_upper": forecast.get("confidence_interval_upper", []),
        }
