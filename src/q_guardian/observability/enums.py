"""Enumerations for the Observability & Operations Platform."""

from __future__ import annotations

from enum import StrEnum


class MetricType(StrEnum):
    """Type of metric measurement."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class MetricUnit(StrEnum):
    """Unit of measurement for metrics."""

    NONE = "none"
    COUNT = "count"
    PERCENTAGE = "percentage"
    SECONDS = "seconds"
    MILLISECONDS = "milliseconds"
    MICROSECONDS = "microseconds"
    BYTES = "bytes"
    KILOBYTES = "kilobytes"
    MEGABYTES = "megabytes"
    REQUESTS_PER_SECOND = "requests_per_second"
    PER_SECOND = "per_second"


class HealthStatus(StrEnum):
    """Health status of a component."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"


class HealthLevel(StrEnum):
    """Health score level classification."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertState(StrEnum):
    """Current state of an alert."""

    PENDING = "pending"
    FIRING = "firing"
    ACKNOWLEDGED = "acknowledged"
    SUPPRESSED = "suppressed"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class AlertType(StrEnum):
    """Type of alert rule."""

    THRESHOLD = "threshold"
    HEALTH = "health"
    LATENCY = "latency"
    FAILURE = "failure"
    SECURITY = "security"
    CUSTOM = "custom"


class TraceStatus(StrEnum):
    """Status of a distributed trace."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"


class SpanKind(StrEnum):
    """Kind of span in a trace."""

    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class AnalyticsGranularity(StrEnum):
    """Time granularity for analytics."""

    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ExporterType(StrEnum):
    """Type of metric exporter."""

    PROMETHEUS = "prometheus"
    OPENTELEMETRY = "opentelemetry"
    JSON = "json"
    CSV = "csv"
    CUSTOM = "custom"


class DashboardFormat(StrEnum):
    """Response format for dashboard API."""

    JSON = "json"
    COMPACT = "compact"
    DETAILED = "detailed"


class AggregationType(StrEnum):
    """Type of metric aggregation."""

    SUM = "sum"
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    RATE = "rate"
    LAST = "last"
    PERCENTILE = "percentile"


class PercentileType(StrEnum):
    """Standard percentile types."""

    P50 = "p50"
    P75 = "p75"
    P90 = "p90"
    P95 = "p95"
    P99 = "p99"


class TrendDirection(StrEnum):
    """Direction of a measured trend."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


class RollupInterval(StrEnum):
    """Time intervals for metric rollups."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    TWENTY_FOUR_HOURS = "24h"
