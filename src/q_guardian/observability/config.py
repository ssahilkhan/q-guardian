"""Configuration for the Observability & Operations Platform."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MetricsConfig(BaseModel):
    """Metrics engine configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable metrics collection")
    collection_interval_seconds: int = Field(
        default=10, description="Metric collection interval in seconds"
    )
    default_window_size: int = Field(
        default=60, description="Default rolling window size in seconds"
    )
    max_series_per_metric: int = Field(
        default=10_000, description="Maximum data points per metric series"
    )
    histogram_bucket_count: int = Field(default=20, description="Number of histogram buckets")
    enable_percentiles: bool = Field(default=True, description="Enable percentile calculations")
    percentiles: list[float] = Field(
        default_factory=lambda: [50.0, 95.0, 99.0],
        description="Percentile values to compute",
    )
    enable_tags: bool = Field(default=True, description="Enable metric tags/labels")


class TracingConfig(BaseModel):
    """Tracing engine configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable distributed tracing")
    max_spans_per_trace: int = Field(default=500, description="Maximum spans per trace")
    max_trace_duration_seconds: int = Field(default=3600, description="Maximum trace duration")
    sample_rate: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Sampling rate (0.0 to 1.0)"
    )
    propagation_format: str = Field(
        default="w3c", description="Trace propagation format: w3c, b3, jaeger"
    )


class HealthConfig(BaseModel):
    """Health engine configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable health monitoring")
    heartbeat_interval_seconds: int = Field(default=30, description="Heartbeat check interval")
    heartbeat_timeout_seconds: int = Field(
        default=90, description="Heartbeat timeout before unhealthy"
    )
    unhealthy_threshold: int = Field(default=3, description="Consecutive failures before unhealthy")
    degraded_threshold: int = Field(default=1, description="Consecutive warnings before degraded")


class AnalyticsConfig(BaseModel):
    """Analytics engine configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable analytics")
    default_granularity: str = Field(default="hour", description="Default analytics granularity")
    retention_days: int = Field(default=90, description="Analytics data retention in days")
    enable_forecasting: bool = Field(default=True, description="Enable trend forecasting")
    forecast_horizon_hours: int = Field(default=24, description="Forecast horizon in hours")
    max_report_size: int = Field(default=10_000, description="Maximum entries per analytics report")


class AlertConfig(BaseModel):
    """Alert engine configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable alerting")
    evaluation_interval_seconds: int = Field(
        default=30, description="Alert rule evaluation interval"
    )
    suppression_window_seconds: int = Field(default=300, description="Alert suppression window")
    max_active_alerts: int = Field(default=1000, description="Maximum active alerts")
    default_severity: str = Field(default="medium", description="Default alert severity")
    enable_escalation: bool = Field(default=True, description="Enable alert escalation")
    escalation_timeout_seconds: int = Field(default=600, description="Escalation timeout")


class DashboardConfig(BaseModel):
    """Dashboard API configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable dashboard API")
    api_prefix: str = Field(default="/api/v1/observability", description="API endpoint prefix")
    max_results: int = Field(default=500, description="Maximum results per query")
    default_time_range_seconds: int = Field(
        default=3600, description="Default time range for queries"
    )


class ExporterConfig(BaseModel):
    """Exporter configuration."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable exporters")
    active_exporters: list[str] = Field(
        default_factory=lambda: ["json"],
        description="List of active exporter names",
    )
    export_interval_seconds: int = Field(default=60, description="Export interval")
    batch_size: int = Field(default=100, description="Batch size for exports")


class ObservabilityConfig(BaseModel):
    """Top-level configuration for the Observability module."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Enable observability platform")
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    exporters: ExporterConfig = Field(default_factory=ExporterConfig)
