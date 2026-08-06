from datetime import UTC, datetime

from q_guardian.observability.dashboard.api import DashboardAPI
from q_guardian.observability.dashboard.dto import (
    AlertsResponseDTO,
    AnalyticsResponseDTO,
    DashboardSnapshotDTO,
    HealthResponseDTO,
    MetricsResponseDTO,
    PluginsResponseDTO,
    RuntimeResponseDTO,
)
from q_guardian.observability.dashboard.endpoints import DashboardEndpoints
from q_guardian.observability.dashboard.filters import (
    DashboardFilter,
    MetricFilter,
    TimeRangeFilter,
)
from q_guardian.observability.dashboard.serializers import DashboardSerializer
from q_guardian.observability.enums import (
    AlertSeverity,
    AnalyticsGranularity,
    DashboardFormat,
)


class TestDashboardAPICreation:
    def test_creation_with_no_engines(self):
        api = DashboardAPI()
        assert api is not None
        result = api.to_dict()
        assert result["metrics_engine"] is False
        assert result["health_engine"] is False
        assert result["trace_engine"] is False
        assert result["analytics_engine"] is False
        assert result["alert_engine"] is False

    def test_creation_with_all_engines(self):
        api = DashboardAPI(
            metrics_engine="m",
            health_engine="h",
            trace_engine="t",
            analytics_engine="a",
            alert_engine="al",
            plugin_registry="p",
            storage="s",
        )
        result = api.to_dict()
        assert result["metrics_engine"] is True
        assert result["health_engine"] is True
        assert result["trace_engine"] is True
        assert result["analytics_engine"] is True
        assert result["alert_engine"] is True
        assert result["plugin_registry"] is True
        assert result["storage"] is True


class TestDashboardAPIEndpoints:
    def test_get_metrics_returns_dict_with_metrics_key(self):
        api = DashboardAPI()
        result = api.get_metrics()
        assert isinstance(result, dict)
        assert "metrics" in result
        assert "total" in result

    def test_get_health_returns_dict_with_overall_status(self):
        api = DashboardAPI()
        result = api.get_health()
        assert isinstance(result, dict)
        assert "overall_status" in result
        assert result["overall_status"] == "unknown"

    def test_get_analytics_returns_dict(self):
        api = DashboardAPI()
        result = api.get_analytics()
        assert isinstance(result, dict)
        assert "report_id" in result
        assert "title" in result

    def test_get_runtime_returns_dict(self):
        api = DashboardAPI()
        result = api.get_runtime()
        assert isinstance(result, dict)
        assert "statistics" in result
        assert "performance" in result
        assert "resources" in result

    def test_get_providers_returns_dict(self):
        api = DashboardAPI()
        result = api.get_providers()
        assert isinstance(result, dict)
        assert "providers" in result
        assert "accuracy" in result

    def test_get_incidents_returns_dict(self):
        api = DashboardAPI()
        result = api.get_incidents()
        assert isinstance(result, dict)
        assert "alerts" in result
        assert "active_count" in result
        assert "resolved_count" in result

    def test_get_responses_returns_dict(self):
        api = DashboardAPI()
        result = api.get_responses()
        assert isinstance(result, dict)
        assert "responses" in result
        assert "total" in result

    def test_get_policies_returns_dict(self):
        api = DashboardAPI()
        result = api.get_policies()
        assert isinstance(result, dict)
        assert "policies" in result
        assert "total" in result

    def test_get_plugins_returns_dict(self):
        api = DashboardAPI()
        result = api.get_plugins()
        assert isinstance(result, dict)
        assert "plugins" in result
        assert "total" in result

    def test_get_alerts_returns_dict(self):
        api = DashboardAPI()
        result = api.get_alerts()
        assert isinstance(result, dict)
        assert "alerts" in result
        assert "rules" in result
        assert "total" in result

    def test_get_snapshot_returns_dict(self):
        api = DashboardAPI()
        result = api.get_snapshot()
        assert isinstance(result, dict)
        assert "snapshot_id" in result
        assert "runtime" in result
        assert "health" in result

    def test_to_dict_shows_engine_presence(self):
        api = DashboardAPI(metrics_engine="m", alert_engine="a")
        result = api.to_dict()
        assert result["metrics_engine"] is True
        assert result["alert_engine"] is True
        assert result["health_engine"] is False
        assert result["trace_engine"] is False
        assert result["analytics_engine"] is False


class TestDashboardEndpoints:
    def test_metrics_endpoint_wrapping(self):
        api = DashboardAPI()
        endpoints = DashboardEndpoints(api)
        result = endpoints.metrics_endpoint()
        assert isinstance(result, dict)
        assert "metrics" in result

    def test_health_endpoint_wrapping(self):
        api = DashboardAPI()
        endpoints = DashboardEndpoints(api)
        result = endpoints.health_endpoint()
        assert isinstance(result, dict)
        assert "overall_status" in result

    def test_snapshot_endpoint_wrapping(self):
        api = DashboardAPI()
        endpoints = DashboardEndpoints(api)
        result = endpoints.snapshot_endpoint()
        assert isinstance(result, dict)
        assert "snapshot_id" in result


class TestDashboardSerializer:
    def test_serialize_metric(self):
        serializer = DashboardSerializer()
        metric = {
            "metric_id": "m1",
            "name": "test.metric",
            "metric_type": "counter",
            "unit": "count",
            "description": "test desc",
            "labels": {"env": "test"},
            "points": [],
        }
        result = serializer.serialize_metric(metric)
        assert result["metric_id"] == "m1"
        assert result["name"] == "test.metric"
        assert result["type"] == "counter"

    def test_serialize_health(self):
        serializer = DashboardSerializer()
        health = {
            "component": "core",
            "status": "healthy",
            "health_score": 0.95,
            "level": "excellent",
            "last_heartbeat": datetime.now(UTC),
            "uptime_seconds": 100.0,
            "warnings": [],
            "failures": [],
            "dependencies": {},
            "metadata": {},
        }
        result = serializer.serialize_health(health)
        assert result["component"] == "core"
        assert result["status"] == "healthy"
        assert result["health_score"] == 0.95

    def test_serialize_alert(self):
        serializer = DashboardSerializer()
        alert = {
            "alert_id": "a1",
            "rule_id": "r1",
            "rule_name": "test_rule",
            "state": "firing",
            "severity": "high",
            "alert_type": "threshold",
            "message": "test msg",
            "labels": {},
            "annotations": {},
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "resolved_at": None,
            "acknowledged_at": None,
            "acknowledged_by": None,
            "evaluation_value": 42.0,
            "escalation_level": 0,
        }
        result = serializer.serialize_alert(alert)
        assert result["alert_id"] == "a1"
        assert result["rule_name"] == "test_rule"
        assert result["severity"] == "high"

    def test_format_timestamp_with_datetime(self):
        serializer = DashboardSerializer()
        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = serializer.format_timestamp(dt)
        assert isinstance(result, str)
        assert "2025" in result

    def test_format_timestamp_with_string(self):
        serializer = DashboardSerializer()
        result = serializer.format_timestamp("2025-01-15T12:00:00Z")
        assert result == "2025-01-15T12:00:00Z"

    def test_format_timestamp_with_none(self):
        serializer = DashboardSerializer()
        result = serializer.format_timestamp(None)
        assert result == ""


class TestDashboardFilter:
    def test_creation(self):
        f = DashboardFilter()
        assert f.limit == 100
        assert f.offset == 0
        assert f.format == DashboardFormat.JSON

    def test_creation_with_params(self):
        f = DashboardFilter(
            start_time=datetime.now(UTC),
            metric_name="cpu",
            severity=AlertSeverity.HIGH,
            limit=50,
        )
        assert f.metric_name == "cpu"
        assert f.severity == AlertSeverity.HIGH
        assert f.limit == 50


class TestTimeRangeFilter:
    def test_creation(self):
        f = TimeRangeFilter()
        assert f.granularity == AnalyticsGranularity.HOUR

    def test_to_time_window_returns_none_when_no_times(self):
        f = TimeRangeFilter()
        assert f.to_time_window() is None

    def test_to_time_window_with_start(self):
        start = datetime(2025, 1, 1, tzinfo=UTC)
        f = TimeRangeFilter(start=start)
        tw = f.to_time_window()
        assert tw is not None
        assert tw.start == start

    def test_to_time_window_with_end(self):
        end = datetime(2025, 12, 31, tzinfo=UTC)
        f = TimeRangeFilter(end=end)
        tw = f.to_time_window()
        assert tw is not None
        assert tw.end == end


class TestMetricFilter:
    def test_creation(self):
        f = MetricFilter()
        assert f.name is None
        assert f.labels == {}
        assert f.min_value is None
        assert f.max_value is None

    def test_creation_with_params(self):
        f = MetricFilter(name="cpu", min_value=0.0, max_value=100.0, labels={"env": "prod"})
        assert f.name == "cpu"
        assert f.min_value == 0.0
        assert f.max_value == 100.0
        assert f.labels == {"env": "prod"}


class TestDTOs:
    def test_metrics_response_dto(self):
        dto = MetricsResponseDTO(metrics=[], total=0)
        d = dto.model_dump(mode="json")
        assert "metrics" in d
        assert "total" in d
        assert "timestamp" in d

    def test_health_response_dto(self):
        dto = HealthResponseDTO(overall_status="healthy", overall_score=0.95)
        d = dto.model_dump(mode="json")
        assert d["overall_status"] == "healthy"
        assert d["overall_score"] == 0.95

    def test_analytics_response_dto(self):
        dto = AnalyticsResponseDTO(title="Test Report")
        d = dto.model_dump(mode="json")
        assert d["title"] == "Test Report"
        assert "report_id" in d

    def test_runtime_response_dto(self):
        dto = RuntimeResponseDTO(statistics={"rps": 100})
        d = dto.model_dump(mode="json")
        assert d["statistics"]["rps"] == 100

    def test_alerts_response_dto(self):
        dto = AlertsResponseDTO(alerts=[], rules=[], total=5)
        d = dto.model_dump(mode="json")
        assert d["total"] == 5

    def test_plugins_response_dto(self):
        dto = PluginsResponseDTO(plugins=[], total=2)
        d = dto.model_dump(mode="json")
        assert d["total"] == 2

    def test_dashboard_snapshot_dto(self):
        dto = DashboardSnapshotDTO(runtime={"key": "val"}, active_alerts_count=3)
        d = dto.model_dump(mode="json")
        assert d["active_alerts_count"] == 3
        assert "snapshot_id" in d
