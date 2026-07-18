import pytest

from q_guardian.observability.config import (
    AlertConfig,
    AnalyticsConfig,
    DashboardConfig,
    ExporterConfig,
    HealthConfig,
    MetricsConfig,
    ObservabilityConfig,
    TracingConfig,
)


class TestMetricsConfig:
    def test_defaults(self) -> None:
        config = MetricsConfig()
        assert config.enabled is True
        assert config.collection_interval_seconds == 10
        assert config.default_window_size == 60
        assert config.max_series_per_metric == 10_000
        assert config.histogram_bucket_count == 20
        assert config.enable_percentiles is True
        assert config.percentiles == [50.0, 95.0, 99.0]
        assert config.enable_tags is True

    def test_custom_values(self) -> None:
        config = MetricsConfig(
            enabled=False,
            collection_interval_seconds=30,
            percentiles=[50.0, 99.0],
        )
        assert config.enabled is False
        assert config.collection_interval_seconds == 30
        assert config.percentiles == [50.0, 99.0]

    def test_percentiles_default_factory(self) -> None:
        c1 = MetricsConfig()
        c2 = MetricsConfig()
        assert c1.percentiles == c2.percentiles
        c1.percentiles.append(99.9)
        assert c2.percentiles == [50.0, 95.0, 99.0]

    def test_extra_allow(self) -> None:
        config = MetricsConfig(custom_key="custom_value")
        assert config.custom_key == "custom_value"

    def test_serialization(self) -> None:
        config = MetricsConfig(enabled=False)
        data = config.model_dump()
        assert data["enabled"] is False
        assert "collection_interval_seconds" in data

    def test_from_dict(self) -> None:
        data = {"enabled": True, "collection_interval_seconds": 5}
        config = MetricsConfig(**data)
        assert config.collection_interval_seconds == 5


class TestTracingConfig:
    def test_defaults(self) -> None:
        config = TracingConfig()
        assert config.enabled is True
        assert config.max_spans_per_trace == 500
        assert config.max_trace_duration_seconds == 3600
        assert config.sample_rate == 1.0
        assert config.propagation_format == "w3c"

    def test_custom_values(self) -> None:
        config = TracingConfig(sample_rate=0.5, propagation_format="b3")
        assert config.sample_rate == 0.5
        assert config.propagation_format == "b3"

    def test_sample_rate_bounds(self) -> None:
        config_min = TracingConfig(sample_rate=0.0)
        assert config_min.sample_rate == 0.0
        config_max = TracingConfig(sample_rate=1.0)
        assert config_max.sample_rate == 1.0

    def test_extra_allow(self) -> None:
        config = TracingConfig(custom_field=42)
        assert config.custom_field == 42


class TestHealthConfig:
    def test_defaults(self) -> None:
        config = HealthConfig()
        assert config.enabled is True
        assert config.heartbeat_interval_seconds == 30
        assert config.heartbeat_timeout_seconds == 90
        assert config.unhealthy_threshold == 3
        assert config.degraded_threshold == 1

    def test_heartbeat_settings(self) -> None:
        config = HealthConfig(
            heartbeat_interval_seconds=60,
            heartbeat_timeout_seconds=180,
        )
        assert config.heartbeat_interval_seconds == 60
        assert config.heartbeat_timeout_seconds == 180

    def test_thresholds(self) -> None:
        config = HealthConfig(unhealthy_threshold=5, degraded_threshold=2)
        assert config.unhealthy_threshold == 5
        assert config.degraded_threshold == 2


class TestAnalyticsConfig:
    def test_defaults(self) -> None:
        config = AnalyticsConfig()
        assert config.enabled is True
        assert config.default_granularity == "hour"
        assert config.retention_days == 90
        assert config.enable_forecasting is True
        assert config.forecast_horizon_hours == 24
        assert config.max_report_size == 10_000

    def test_custom_values(self) -> None:
        config = AnalyticsConfig(
            default_granularity="minute",
            retention_days=30,
            enable_forecasting=False,
        )
        assert config.default_granularity == "minute"
        assert config.retention_days == 30
        assert config.enable_forecasting is False


class TestAlertConfig:
    def test_defaults(self) -> None:
        config = AlertConfig()
        assert config.enabled is True
        assert config.evaluation_interval_seconds == 30
        assert config.suppression_window_seconds == 300
        assert config.max_active_alerts == 1000
        assert config.default_severity == "medium"
        assert config.enable_escalation is True
        assert config.escalation_timeout_seconds == 600

    def test_custom_values(self) -> None:
        config = AlertConfig(
            evaluation_interval_seconds=10,
            suppression_window_seconds=60,
            default_severity="high",
            enable_escalation=False,
        )
        assert config.evaluation_interval_seconds == 10
        assert config.suppression_window_seconds == 60
        assert config.default_severity == "high"
        assert config.enable_escalation is False

    def test_extra_allow(self) -> None:
        config = AlertConfig(custom_alert_field="test")
        assert config.custom_alert_field == "test"


class TestDashboardConfig:
    def test_defaults(self) -> None:
        config = DashboardConfig()
        assert config.enabled is True
        assert config.api_prefix == "/api/v1/observability"
        assert config.max_results == 500
        assert config.default_time_range_seconds == 3600

    def test_custom_values(self) -> None:
        config = DashboardConfig(api_prefix="/custom", max_results=100)
        assert config.api_prefix == "/custom"
        assert config.max_results == 100


class TestExporterConfig:
    def test_defaults(self) -> None:
        config = ExporterConfig()
        assert config.enabled is True
        assert config.active_exporters == ["json"]
        assert config.export_interval_seconds == 60
        assert config.batch_size == 100

    def test_custom_values(self) -> None:
        config = ExporterConfig(
            active_exporters=["json", "prometheus"],
            batch_size=500,
        )
        assert config.active_exporters == ["json", "prometheus"]
        assert config.batch_size == 500


class TestObservabilityConfig:
    def test_defaults(self) -> None:
        config = ObservabilityConfig()
        assert config.enabled is True
        assert isinstance(config.metrics, MetricsConfig)
        assert isinstance(config.tracing, TracingConfig)
        assert isinstance(config.health, HealthConfig)
        assert isinstance(config.analytics, AnalyticsConfig)
        assert isinstance(config.alerts, AlertConfig)
        assert isinstance(config.dashboard, DashboardConfig)
        assert isinstance(config.exporters, ExporterConfig)

    def test_nested_customization(self) -> None:
        config = ObservabilityConfig(
            metrics=MetricsConfig(collection_interval_seconds=5),
            tracing=TracingConfig(sample_rate=0.1),
        )
        assert config.metrics.collection_interval_seconds == 5
        assert config.tracing.sample_rate == 0.1

    def test_serialization(self) -> None:
        config = ObservabilityConfig(enabled=True)
        data = config.model_dump()
        assert data["enabled"] is True
        assert "metrics" in data
        assert "tracing" in data

    def test_from_dict(self) -> None:
        data = {
            "enabled": True,
            "metrics": {"collection_interval_seconds": 3},
        }
        config = ObservabilityConfig(**data)
        assert config.metrics.collection_interval_seconds == 3

    def test_extra_allow(self) -> None:
        config = ObservabilityConfig(custom_top="value")
        assert config.custom_top == "value"
