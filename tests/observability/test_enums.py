from q_guardian.observability.enums import (
    AggregationType,
    AlertSeverity,
    AlertState,
    AlertType,
    AnalyticsGranularity,
    DashboardFormat,
    ExporterType,
    HealthLevel,
    HealthStatus,
    MetricType,
    MetricUnit,
    PercentileType,
    RollupInterval,
    SpanKind,
    TraceStatus,
    TrendDirection,
)


class TestMetricType:
    def test_counter_exists(self) -> None:
        assert MetricType.COUNTER == "counter"

    def test_gauge_exists(self) -> None:
        assert MetricType.GAUGE == "gauge"

    def test_histogram_exists(self) -> None:
        assert MetricType.HISTOGRAM == "histogram"

    def test_timer_exists(self) -> None:
        assert MetricType.TIMER == "timer"

    def test_str_representation(self) -> None:
        assert str(MetricType.COUNTER) == "counter"

    def test_is_str_subclass(self) -> None:
        assert isinstance(MetricType.COUNTER, str)


class TestMetricUnit:
    def test_none_exists(self) -> None:
        assert MetricUnit.NONE == "none"

    def test_bytes_exists(self) -> None:
        assert MetricUnit.BYTES == "bytes"

    def test_requests_per_second_exists(self) -> None:
        assert MetricUnit.REQUESTS_PER_SECOND == "requests_per_second"

    def test_str_representation(self) -> None:
        assert str(MetricUnit.NONE) == "none"


class TestHealthStatus:
    def test_healthy_exists(self) -> None:
        assert HealthStatus.HEALTHY == "healthy"

    def test_degraded_exists(self) -> None:
        assert HealthStatus.DEGRADED == "degraded"

    def test_unhealthy_exists(self) -> None:
        assert HealthStatus.UNHEALTHY == "unhealthy"

    def test_unknown_exists(self) -> None:
        assert HealthStatus.UNKNOWN == "unknown"

    def test_maintenance_exists(self) -> None:
        assert HealthStatus.MAINTENANCE == "maintenance"

    def test_str_representation(self) -> None:
        assert str(HealthStatus.HEALTHY) == "healthy"


class TestHealthLevel:
    def test_excellent_exists(self) -> None:
        assert HealthLevel.EXCELLENT == "excellent"

    def test_critical_exists(self) -> None:
        assert HealthLevel.CRITICAL == "critical"


class TestAlertSeverity:
    def test_info_exists(self) -> None:
        assert AlertSeverity.INFO == "info"

    def test_low_exists(self) -> None:
        assert AlertSeverity.LOW == "low"

    def test_medium_exists(self) -> None:
        assert AlertSeverity.MEDIUM == "medium"

    def test_high_exists(self) -> None:
        assert AlertSeverity.HIGH == "high"

    def test_critical_exists(self) -> None:
        assert AlertSeverity.CRITICAL == "critical"


class TestAlertState:
    def test_pending_exists(self) -> None:
        assert AlertState.PENDING == "pending"

    def test_firing_exists(self) -> None:
        assert AlertState.FIRING == "firing"

    def test_acknowledged_exists(self) -> None:
        assert AlertState.ACKNOWLEDGED == "acknowledged"

    def test_suppressed_exists(self) -> None:
        assert AlertState.SUPPRESSED == "suppressed"

    def test_resolved_exists(self) -> None:
        assert AlertState.RESOLVED == "resolved"

    def test_escalated_exists(self) -> None:
        assert AlertState.ESCALATED == "escalated"


class TestAlertType:
    def test_threshold_exists(self) -> None:
        assert AlertType.THRESHOLD == "threshold"

    def test_health_exists(self) -> None:
        assert AlertType.HEALTH == "health"

    def test_latency_exists(self) -> None:
        assert AlertType.LATENCY == "latency"

    def test_failure_exists(self) -> None:
        assert AlertType.FAILURE == "failure"

    def test_security_exists(self) -> None:
        assert AlertType.SECURITY == "security"

    def test_custom_exists(self) -> None:
        assert AlertType.CUSTOM == "custom"


class TestTraceStatus:
    def test_active_exists(self) -> None:
        assert TraceStatus.ACTIVE == "active"

    def test_completed_exists(self) -> None:
        assert TraceStatus.COMPLETED == "completed"

    def test_error_exists(self) -> None:
        assert TraceStatus.ERROR == "error"

    def test_timeout_exists(self) -> None:
        assert TraceStatus.TIMEOUT == "timeout"


class TestSpanKind:
    def test_internal_exists(self) -> None:
        assert SpanKind.INTERNAL == "internal"

    def test_server_exists(self) -> None:
        assert SpanKind.SERVER == "server"

    def test_client_exists(self) -> None:
        assert SpanKind.CLIENT == "client"

    def test_producer_exists(self) -> None:
        assert SpanKind.PRODUCER == "producer"

    def test_consumer_exists(self) -> None:
        assert SpanKind.CONSUMER == "consumer"


class TestAnalyticsGranularity:
    def test_minute_exists(self) -> None:
        assert AnalyticsGranularity.MINUTE == "minute"

    def test_hour_exists(self) -> None:
        assert AnalyticsGranularity.HOUR == "hour"

    def test_day_exists(self) -> None:
        assert AnalyticsGranularity.DAY == "day"

    def test_week_exists(self) -> None:
        assert AnalyticsGranularity.WEEK == "week"

    def test_month_exists(self) -> None:
        assert AnalyticsGranularity.MONTH == "month"


class TestExporterType:
    def test_prometheus_exists(self) -> None:
        assert ExporterType.PROMETHEUS == "prometheus"

    def test_opentelemetry_exists(self) -> None:
        assert ExporterType.OPENTELEMETRY == "opentelemetry"

    def test_json_exists(self) -> None:
        assert ExporterType.JSON == "json"

    def test_csv_exists(self) -> None:
        assert ExporterType.CSV == "csv"

    def test_custom_exists(self) -> None:
        assert ExporterType.CUSTOM == "custom"


class TestDashboardFormat:
    def test_json_exists(self) -> None:
        assert DashboardFormat.JSON == "json"

    def test_compact_exists(self) -> None:
        assert DashboardFormat.COMPACT == "compact"

    def test_detailed_exists(self) -> None:
        assert DashboardFormat.DETAILED == "detailed"


class TestAggregationType:
    def test_sum_exists(self) -> None:
        assert AggregationType.SUM == "sum"

    def test_average_exists(self) -> None:
        assert AggregationType.AVERAGE == "average"

    def test_percentile_exists(self) -> None:
        assert AggregationType.PERCENTILE == "percentile"


class TestPercentileType:
    def test_p50_exists(self) -> None:
        assert PercentileType.P50 == "p50"

    def test_p95_exists(self) -> None:
        assert PercentileType.P95 == "p95"

    def test_p99_exists(self) -> None:
        assert PercentileType.P99 == "p99"


class TestTrendDirection:
    def test_increasing_exists(self) -> None:
        assert TrendDirection.INCREASING == "increasing"

    def test_decreasing_exists(self) -> None:
        assert TrendDirection.DECREASING == "decreasing"

    def test_stable_exists(self) -> None:
        assert TrendDirection.STABLE == "stable"

    def test_volatile_exists(self) -> None:
        assert TrendDirection.VOLATILE == "volatile"


class TestRollupInterval:
    def test_one_minute(self) -> None:
        assert RollupInterval.ONE_MINUTE == "1m"

    def test_one_hour(self) -> None:
        assert RollupInterval.ONE_HOUR == "1h"

    def test_twenty_four_hours(self) -> None:
        assert RollupInterval.TWENTY_FOUR_HOURS == "24h"
