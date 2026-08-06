"""Data models for the Observability & Operations Platform."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.observability.enums import (
    AlertSeverity,
    AlertState,
    AlertType,
    HealthLevel,
    HealthStatus,
    MetricType,
    MetricUnit,
    SpanKind,
    TraceStatus,
    TrendDirection,
)
from q_guardian.utils.uuid_utils import generate_uuid


class TimeWindow(BaseModel):
    """Time range for queries and aggregations."""

    model_config = ConfigDict(populate_by_name=True)

    start: datetime = Field(description="Window start time")
    end: datetime = Field(description="Window end time")

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    def contains(self, dt: datetime) -> bool:
        return self.start <= dt <= self.end


class MetricPoint(BaseModel):
    """Single metric data point."""

    model_config = ConfigDict(populate_by_name=True)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    value: float = Field(description="Metric value")
    labels: dict[str, str] = Field(default_factory=dict, description="Metric labels")


class Metric(BaseModel):
    """A named metric with type, unit, and data points."""

    model_config = ConfigDict(populate_by_name=True)

    metric_id: str = Field(default_factory=generate_uuid)
    name: str = Field(description="Metric name")
    metric_type: MetricType = Field(description="Metric type")
    unit: MetricUnit = Field(default=MetricUnit.NONE)
    description: str = Field(default="")
    labels: dict[str, str] = Field(default_factory=dict)
    points: list[MetricPoint] = Field(default_factory=list)

    def add_point(self, value: float, labels: dict[str, str] | None = None) -> MetricPoint:
        merged = {**self.labels, **(labels or {})}
        point = MetricPoint(value=value, labels=merged)
        self.points.append(point)
        return point

    def latest_value(self) -> float | None:
        return self.points[-1].value if self.points else None

    def values_in_window(self, window: TimeWindow) -> list[float]:
        return [p.value for p in self.points if window.contains(p.timestamp)]


class MetricSeries(BaseModel):
    """Time series of aggregated metric values."""

    model_config = ConfigDict(populate_by_name=True)

    series_id: str = Field(default_factory=generate_uuid)
    metric_name: str = Field(description="Source metric name")
    aggregation: str = Field(default="last", description="Aggregation type")
    interval_seconds: int = Field(default=60, description="Aggregation interval")
    points: list[MetricPoint] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)


class AggregatedMetric(BaseModel):
    """Aggregated metric result."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Metric name")
    aggregation: str = Field(description="Aggregation type applied")
    value: float = Field(description="Aggregated value")
    count: int = Field(default=0)
    min_value: float | None = None
    max_value: float | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    window: TimeWindow | None = None


class HealthStatusModel(BaseModel):
    """Health status for a single component."""

    model_config = ConfigDict(populate_by_name=True)

    component: str = Field(description="Component name")
    status: HealthStatus = Field(default=HealthStatus.UNKNOWN)
    health_score: float = Field(default=1.0, ge=0.0, le=1.0)
    level: HealthLevel = Field(default=HealthLevel.GOOD)
    last_heartbeat: datetime | None = None
    uptime_seconds: float = Field(default=0.0)
    warnings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    dependencies: dict[str, HealthStatus] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update_level(self) -> None:
        if self.health_score >= 0.9:
            self.level = HealthLevel.EXCELLENT
        elif self.health_score >= 0.7:
            self.level = HealthLevel.GOOD
        elif self.health_score >= 0.5:
            self.level = HealthLevel.FAIR
        elif self.health_score >= 0.3:
            self.level = HealthLevel.POOR
        else:
            self.level = HealthLevel.CRITICAL


class HealthCheckResult(BaseModel):
    """Result of a health check execution."""

    model_config = ConfigDict(populate_by_name=True)

    check_id: str = Field(default_factory=generate_uuid)
    component: str = Field(description="Component checked")
    status: HealthStatus = Field(description="Health status")
    message: str = Field(default="")
    latency_ms: float = Field(default=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = Field(default_factory=dict)


class HealthReport(BaseModel):
    """Aggregate health report across all components."""

    model_config = ConfigDict(populate_by_name=True)

    report_id: str = Field(default_factory=generate_uuid)
    overall_status: HealthStatus = Field(default=HealthStatus.UNKNOWN)
    overall_score: float = Field(default=1.0, ge=0.0, le=1.0)
    components: list[HealthStatusModel] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    framework_uptime_seconds: float = Field(default=0.0)
    active_warnings: int = Field(default=0)
    active_failures: int = Field(default=0)

    def calculate_overall(self) -> None:
        if not self.components:
            self.overall_status = HealthStatus.UNKNOWN
            self.overall_score = 0.0
            return
        scores = [c.health_score for c in self.components]
        self.overall_score = sum(scores) / len(scores)
        statuses = {c.status for c in self.components}
        if HealthStatus.UNHEALTHY in statuses:
            self.overall_status = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            self.overall_status = HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            self.overall_status = HealthStatus.HEALTHY
        else:
            self.overall_status = HealthStatus.DEGRADED
        self.active_warnings = sum(len(c.warnings) for c in self.components)
        self.active_failures = sum(len(c.failures) for c in self.components)


class SpanStatus(BaseModel):
    """Status code for a span."""

    model_config = ConfigDict(populate_by_name=True)

    code: int = Field(default=0, description="Status code: 0=OK, 1=ERROR, 2=TIMEOUT")
    message: str = Field(default="")

    @classmethod
    def ok(cls) -> SpanStatus:
        return cls(code=0, message="OK")

    @classmethod
    def error(cls, message: str = "error") -> SpanStatus:
        return cls(code=1, message=message)

    @classmethod
    def timeout(cls) -> SpanStatus:
        return cls(code=2, message="timeout")


class Span(BaseModel):
    """A single span within a distributed trace."""

    model_config = ConfigDict(populate_by_name=True)

    span_id: str = Field(default_factory=generate_uuid)
    trace_id: str = Field(description="Parent trace ID")
    parent_span_id: str | None = None
    name: str = Field(description="Span operation name")
    kind: SpanKind = Field(default=SpanKind.INTERNAL)
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    status: SpanStatus = Field(default_factory=SpanStatus.ok)
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    @property
    def is_complete(self) -> bool:
        return self.end_time is not None

    def finish(self, status: SpanStatus | None = None) -> None:
        self.end_time = datetime.now(UTC)
        if status:
            self.status = status

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append(
            {
                "name": name,
                "timestamp": datetime.now(UTC).isoformat(),
                "attributes": attributes or {},
            }
        )

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value


class Trace(BaseModel):
    """A distributed trace containing multiple spans."""

    model_config = ConfigDict(populate_by_name=True)

    trace_id: str = Field(default_factory=generate_uuid)
    correlation_id: str = Field(default="", description="Request correlation ID")
    execution_id: str = Field(default="", description="Execution context ID")
    status: TraceStatus = Field(default=TraceStatus.ACTIVE)
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    spans: list[Span] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    @property
    def span_count(self) -> int:
        return len(self.spans)

    def add_span(self, span: Span) -> None:
        span.trace_id = self.trace_id
        self.spans.append(span)

    def get_span(self, span_id: str) -> Span | None:
        for s in self.spans:
            if s.span_id == span_id:
                return s
        return None

    def get_root_spans(self) -> list[Span]:
        return [s for s in self.spans if s.parent_span_id is None]

    def get_child_spans(self, parent_span_id: str) -> list[Span]:
        return [s for s in self.spans if s.parent_span_id == parent_span_id]

    def finish(self, status: TraceStatus | None = None) -> None:
        self.end_time = datetime.now(UTC)
        self.status = status or TraceStatus.COMPLETED


class AlertRule(BaseModel):
    """Definition of an alert rule."""

    model_config = ConfigDict(populate_by_name=True)

    rule_id: str = Field(default_factory=generate_uuid)
    name: str = Field(description="Alert rule name")
    description: str = Field(default="")
    alert_type: AlertType = Field(default=AlertType.THRESHOLD)
    severity: AlertSeverity = Field(default=AlertSeverity.MEDIUM)
    metric_name: str = Field(description="Metric to evaluate")
    condition: str = Field(description="Condition: gt, lt, eq, gte, lte")
    threshold: float = Field(description="Threshold value")
    duration_seconds: int = Field(default=0, description="Condition must be true for this duration")
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    enabled: bool = Field(default=True)
    cooldown_seconds: int = Field(default=300, description="Min time between alerts")

    def evaluate(self, value: float) -> bool:
        ops = {
            "gt": lambda v, t: v > t,
            "lt": lambda v, t: v < t,
            "eq": lambda v, t: v == t,
            "gte": lambda v, t: v >= t,
            "lte": lambda v, t: v <= t,
        }
        op_fn = ops.get(self.condition)
        if op_fn is None:
            return False
        return bool(op_fn(value, self.threshold))


class Alert(BaseModel):
    """An active or resolved alert."""

    model_config = ConfigDict(populate_by_name=True)

    alert_id: str = Field(default_factory=generate_uuid)
    rule_id: str = Field(description="Source rule ID")
    rule_name: str = Field(default="")
    state: AlertState = Field(default=AlertState.PENDING)
    severity: AlertSeverity = Field(default=AlertSeverity.MEDIUM)
    alert_type: AlertType = Field(default=AlertType.THRESHOLD)
    message: str = Field(default="")
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    evaluation_value: float | None = None
    escalation_level: int = Field(default=0)

    @property
    def duration_seconds(self) -> float:
        end = self.resolved_at or datetime.now(UTC)
        return (end - self.created_at).total_seconds()

    def acknowledge(self, user: str = "system") -> None:
        self.state = AlertState.ACKNOWLEDGED
        self.acknowledged_at = datetime.now(UTC)
        self.acknowledged_by = user
        self.updated_at = datetime.now(UTC)

    def resolve(self) -> None:
        self.state = AlertState.RESOLVED
        self.resolved_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def escalate(self) -> None:
        self.state = AlertState.ESCALATED
        self.escalation_level += 1
        self.updated_at = datetime.now(UTC)

    def suppress(self) -> None:
        self.state = AlertState.SUPPRESSED
        self.updated_at = datetime.now(UTC)


class AlertEvent(BaseModel):
    """Event generated by alert state changes."""

    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(default_factory=generate_uuid)
    alert_id: str = Field(description="Related alert ID")
    old_state: AlertState | None = None
    new_state: AlertState = Field(description="New alert state")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrendData(BaseModel):
    """Trend analysis result for a metric."""

    model_config = ConfigDict(populate_by_name=True)

    metric_name: str = Field(description="Metric name")
    direction: TrendDirection = Field(description="Trend direction")
    slope: float = Field(default=0.0, description="Linear regression slope")
    r_squared: float = Field(default=0.0, description="R-squared value")
    mean: float = Field(default=0.0)
    std_dev: float = Field(default=0.0)
    min_value: float = Field(default=0.0)
    max_value: float = Field(default=0.0)
    sample_count: int = Field(default=0)
    period: TimeWindow | None = None


class ForecastResult(BaseModel):
    """Forecast result for future metric values."""

    model_config = ConfigDict(populate_by_name=True)

    metric_name: str = Field(description="Metric name")
    forecast_values: list[MetricPoint] = Field(default_factory=list)
    confidence_interval_lower: list[MetricPoint] = Field(default_factory=list)
    confidence_interval_upper: list[MetricPoint] = Field(default_factory=list)
    method: str = Field(default="linear", description="Forecasting method")
    confidence_level: float = Field(default=0.95)


class AnalyticsReport(BaseModel):
    """Comprehensive analytics report."""

    model_config = ConfigDict(populate_by_name=True)

    report_id: str = Field(default_factory=generate_uuid)
    title: str = Field(default="Analytics Report")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    time_window: TimeWindow | None = None
    threat_trends: list[TrendData] = Field(default_factory=list)
    policy_trends: list[TrendData] = Field(default_factory=list)
    risk_trends: list[TrendData] = Field(default_factory=list)
    response_trends: list[TrendData] = Field(default_factory=list)
    provider_accuracy: dict[str, float] = Field(default_factory=dict)
    plugin_usage: dict[str, int] = Field(default_factory=dict)
    quantum_usage: dict[str, int] = Field(default_factory=dict)
    fusion_strategy_usage: dict[str, int] = Field(default_factory=dict)
    average_confidence: float = Field(default=0.0)
    top_threat_types: list[dict[str, Any]] = Field(default_factory=list)
    top_policies: list[dict[str, Any]] = Field(default_factory=list)
    most_active_sessions: list[dict[str, Any]] = Field(default_factory=list)
    most_active_agents: list[dict[str, Any]] = Field(default_factory=list)
    forecasts: list[ForecastResult] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class RuntimeStatistics(BaseModel):
    """Runtime statistics snapshot."""

    model_config = ConfigDict(populate_by_name=True)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_requests: int = Field(default=0)
    active_requests: int = Field(default=0)
    requests_per_second: float = Field(default=0.0)
    total_sessions: int = Field(default=0)
    active_sessions: int = Field(default=0)
    total_agents: int = Field(default=0)
    active_agents: int = Field(default=0)
    total_threats_detected: int = Field(default=0)
    threats_per_second: float = Field(default=0.0)
    blocked_requests: int = Field(default=0)
    allowed_requests: int = Field(default=0)
    quarantined_count: int = Field(default=0)
    success_rate: float = Field(default=0.0)
    failure_rate: float = Field(default=0.0)
    recovery_rate: float = Field(default=0.0)


class PerformanceMetrics(BaseModel):
    """Framework performance metrics."""

    model_config = ConfigDict(populate_by_name=True)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    prompt_latency_ms: float = Field(default=0.0)
    detection_latency_ms: float = Field(default=0.0)
    fusion_latency_ms: float = Field(default=0.0)
    quantum_latency_ms: float = Field(default=0.0)
    ml_latency_ms: float = Field(default=0.0)
    policy_latency_ms: float = Field(default=0.0)
    response_latency_ms: float = Field(default=0.0)
    average_execution_time_ms: float = Field(default=0.0)
    peak_execution_time_ms: float = Field(default=0.0)
    plugin_execution_times: dict[str, float] = Field(default_factory=dict)
    p50_latency_ms: float = Field(default=0.0)
    p95_latency_ms: float = Field(default=0.0)
    p99_latency_ms: float = Field(default=0.0)


class ResourceMetrics(BaseModel):
    """Resource utilization metrics (framework-level abstractions)."""

    model_config = ConfigDict(populate_by_name=True)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    queue_size: int = Field(default=0)
    max_queue_size: int = Field(default=0)
    active_workers: int = Field(default=0)
    max_workers: int = Field(default=0)
    memory_usage_bytes: int = Field(default=0)
    cpu_usage_percent: float = Field(default=0.0)
    open_connections: int = Field(default=0)
    file_descriptors: int = Field(default=0)


class DashboardSnapshot(BaseModel):
    """Complete dashboard data snapshot."""

    model_config = ConfigDict(populate_by_name=True)

    snapshot_id: str = Field(default_factory=generate_uuid)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    runtime_stats: RuntimeStatistics = Field(default_factory=RuntimeStatistics)
    performance: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    resources: ResourceMetrics = Field(default_factory=ResourceMetrics)
    health: HealthReport = Field(default_factory=HealthReport)
    recent_alerts: list[Alert] = Field(default_factory=list)
    active_alerts_count: int = Field(default=0)
    top_metrics: list[AggregatedMetric] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
