from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from q_guardian.observability.data import (
    DashboardSnapshot,
    PerformanceMetrics,
    ResourceMetrics,
    RuntimeStatistics,
    TimeWindow,
)
from q_guardian.observability.dashboard.dto import (
    AlertsResponseDTO,
    AnalyticsResponseDTO,
    DashboardSnapshotDTO,
    HealthResponseDTO,
    IncidentsResponseDTO,
    MetricsResponseDTO,
    PluginsResponseDTO,
    PoliciesResponseDTO,
    ProvidersResponseDTO,
    ResponsesResponseDTO,
    RuntimeResponseDTO,
)
from q_guardian.observability.dashboard.serializers import DashboardSerializer
from q_guardian.observability.exceptions import DashboardError
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("observability.dashboard.api")


class DashboardAPI:
    def __init__(
        self,
        metrics_engine: Any = None,
        health_engine: Any = None,
        trace_engine: Any = None,
        analytics_engine: Any = None,
        alert_engine: Any = None,
        plugin_registry: Any = None,
        storage: Any = None,
    ) -> None:
        self._metrics_engine = metrics_engine
        self._health_engine = health_engine
        self._trace_engine = trace_engine
        self._analytics_engine = analytics_engine
        self._alert_engine = alert_engine
        self._plugin_registry = plugin_registry
        self._storage = storage
        self._serializer = DashboardSerializer()
        logger.info("dashboard_api_initialized")

    def get_metrics(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            metrics_list: list[dict[str, Any]] = []
            if self._metrics_engine is not None:
                all_metrics = self._metrics_engine.get_all_metrics()
                for name, metric in all_metrics.items():
                    metric_dict = metric.model_dump(mode="json")
                    if query is not None:
                        if not self._matches_query(metric_dict, query):
                            continue
                    metrics_list.append(
                        self._serializer.serialize_metric(metric_dict)
                    )
            dto = MetricsResponseDTO(
                metrics=metrics_list,
                total=len(metrics_list),
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_metrics_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve metrics",
                details={"error": str(e)},
            )

    def get_health(self) -> dict[str, Any]:
        try:
            overall_status = "unknown"
            overall_score = 0.0
            components: list[dict[str, Any]] = []

            if self._health_engine is not None:
                report = self._health_engine.get_health_report()
                overall_status = report.overall_status.value
                overall_score = report.overall_score
                for component in report.components:
                    comp_dict = component.model_dump(mode="json")
                    components.append(
                        self._serializer.serialize_health(comp_dict)
                    )

            dto = HealthResponseDTO(
                overall_status=overall_status,
                overall_score=overall_score,
                components=components,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_health_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve health status",
                details={"error": str(e)},
            )

    def get_analytics(
        self, time_window: TimeWindow | None = None
    ) -> dict[str, Any]:
        try:
            report_id = generate_uuid()
            title = "Q-Guardian Analytics Report"
            generated_at = datetime.now(UTC)
            summary: dict[str, Any] = {}
            threat_trends: list[dict[str, Any]] = []
            forecasts: list[dict[str, Any]] = []

            if self._analytics_engine is not None:
                report = self._analytics_engine.generate_report(time_window)
                report_id = report.report_id
                title = report.title
                generated_at = report.generated_at
                summary = report.summary
                for trend in report.threat_trends:
                    threat_trends.append(trend.model_dump(mode="json"))
                for forecast in report.forecasts:
                    forecasts.append(forecast.model_dump(mode="json"))

            dto = AnalyticsResponseDTO(
                report_id=report_id,
                title=title,
                generated_at=generated_at,
                summary=summary,
                threat_trends=threat_trends,
                forecasts=forecasts,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_analytics_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve analytics",
                details={"error": str(e)},
            )

    def get_runtime(self) -> dict[str, Any]:
        try:
            statistics: dict[str, Any] = {}
            performance: dict[str, Any] = {}
            resources: dict[str, Any] = {}

            if self._metrics_engine is not None:
                all_metrics = self._metrics_engine.get_all_metrics()
                statistics = {
                    name: {
                        "latest_value": m.latest_value(),
                        "point_count": len(m.points),
                        "metric_type": m.metric_type.value,
                    }
                    for name, m in all_metrics.items()
                }

            dto = RuntimeResponseDTO(
                statistics=statistics,
                performance=performance,
                resources=resources,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_runtime_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve runtime statistics",
                details={"error": str(e)},
            )

    def get_providers(self) -> dict[str, Any]:
        try:
            providers: list[dict[str, Any]] = []
            accuracy: dict[str, float] = {}

            if self._analytics_engine is not None:
                accuracy = self._analytics_engine.get_provider_accuracy()

            for name, acc in accuracy.items():
                providers.append({
                    "name": name,
                    "accuracy": acc,
                })

            dto = ProvidersResponseDTO(
                providers=providers,
                accuracy=accuracy,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_providers_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve provider data",
                details={"error": str(e)},
            )

    def get_incidents(self, limit: int = 50) -> dict[str, Any]:
        try:
            alerts: list[dict[str, Any]] = []
            active_count = 0
            resolved_count = 0

            if self._alert_engine is not None:
                active_alerts = self._alert_engine.get_active_alerts()
                history = self._alert_engine.get_alert_history()
                active_count = len(active_alerts)
                resolved_count = len(history)

                all_alerts = active_alerts + history
                for alert in all_alerts[:limit]:
                    alert_dict = alert.model_dump(mode="json")
                    alerts.append(self._serializer.serialize_alert(alert_dict))

            dto = IncidentsResponseDTO(
                alerts=alerts,
                active_count=active_count,
                resolved_count=resolved_count,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_incidents_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve incidents",
                details={"error": str(e)},
            )

    def get_responses(self, limit: int = 50) -> dict[str, Any]:
        try:
            responses: list[dict[str, Any]] = []
            total = 0

            if self._analytics_engine is not None:
                report = self._analytics_engine.generate_report()
                for trend in report.response_trends:
                    responses.append(trend.model_dump(mode="json"))
                total = len(responses)

            dto = ResponsesResponseDTO(
                responses=responses[:limit],
                total=total,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_responses_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve response data",
                details={"error": str(e)},
            )

    def get_policies(self) -> dict[str, Any]:
        try:
            policies: list[dict[str, Any]] = []
            total = 0

            if self._analytics_engine is not None:
                top_policies = self._analytics_engine.get_top_policies()
                policies = top_policies
                total = len(policies)

            dto = PoliciesResponseDTO(
                policies=policies,
                total=total,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_policies_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve policy data",
                details={"error": str(e)},
            )

    def get_plugins(self) -> dict[str, Any]:
        try:
            plugins: list[dict[str, Any]] = []
            total = 0

            if self._plugin_registry is not None:
                if hasattr(self._plugin_registry, "list_plugins"):
                    raw_plugins = self._plugin_registry.list_plugins()
                    for plugin in raw_plugins:
                        if isinstance(plugin, dict):
                            plugins.append(self._serializer.serialize_plugin(plugin))
                        else:
                            plugin_dict = {
                                "name": getattr(plugin, "name", str(plugin)),
                                "version": getattr(plugin, "version", ""),
                                "description": getattr(plugin, "description", ""),
                            }
                            plugins.append(self._serializer.serialize_plugin(plugin_dict))
                    total = len(plugins)

            dto = PluginsResponseDTO(
                plugins=plugins,
                total=total,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_plugins_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve plugin data",
                details={"error": str(e)},
            )

    def get_alerts(self) -> dict[str, Any]:
        try:
            alerts: list[dict[str, Any]] = []
            rules: list[dict[str, Any]] = []
            total = 0

            if self._alert_engine is not None:
                active_alerts = self._alert_engine.get_active_alerts()
                for alert in active_alerts:
                    alert_dict = alert.model_dump(mode="json")
                    alerts.append(self._serializer.serialize_alert(alert_dict))

                alert_rules = self._alert_engine.list_rules()
                for rule in alert_rules:
                    rules.append(rule.model_dump(mode="json"))

                total = len(alerts) + len(rules)

            dto = AlertsResponseDTO(
                alerts=alerts,
                rules=rules,
                total=total,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_alerts_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve alert data",
                details={"error": str(e)},
            )

    def get_snapshot(self) -> dict[str, Any]:
        try:
            snapshot_id = generate_uuid()
            runtime: dict[str, Any] = {}
            performance: dict[str, Any] = {}
            health: dict[str, Any] = {}
            active_alerts_count = 0

            if self._metrics_engine is not None:
                all_metrics = self._metrics_engine.get_all_metrics()
                runtime = {
                    "metric_count": len(all_metrics),
                    "metrics": {
                        name: {
                            "latest_value": m.latest_value(),
                            "point_count": len(m.points),
                        }
                        for name, m in all_metrics.items()
                    },
                }

            if self._health_engine is not None:
                report = self._health_engine.get_health_report()
                health = report.model_dump(mode="json")

            if self._alert_engine is not None:
                active_alerts_count = len(self._alert_engine.get_active_alerts())

            dto = DashboardSnapshotDTO(
                snapshot_id=snapshot_id,
                runtime=runtime,
                performance=performance,
                health=health,
                active_alerts_count=active_alerts_count,
            )
            return dto.model_dump(mode="json")
        except DashboardError:
            raise
        except Exception as e:
            logger.error("get_snapshot_error", error=str(e))
            raise DashboardError(
                message="Failed to retrieve dashboard snapshot",
                details={"error": str(e)},
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics_engine": self._metrics_engine is not None,
            "health_engine": self._health_engine is not None,
            "trace_engine": self._trace_engine is not None,
            "analytics_engine": self._analytics_engine is not None,
            "alert_engine": self._alert_engine is not None,
            "plugin_registry": self._plugin_registry is not None,
            "storage": self._storage is not None,
        }

    def _matches_query(self, metric_dict: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, value in query.items():
            if key == "name" and metric_dict.get("name") != value:
                return False
            if key == "metric_type" and metric_dict.get("metric_type") != value:
                return False
            if key == "unit" and metric_dict.get("unit") != value:
                return False
            if key == "labels":
                if isinstance(value, dict):
                    metric_labels = metric_dict.get("labels", {})
                    for lk, lv in value.items():
                        if metric_labels.get(lk) != lv:
                            return False
        return True
