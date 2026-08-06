"""Main MetricsEngine for recording, querying, and aggregating metrics."""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

import structlog

from q_guardian.observability.data import (
    AggregatedMetric,
    Metric,
    TimeWindow,
)
from q_guardian.observability.enums import AggregationType, MetricType, MetricUnit
from q_guardian.observability.exceptions import MetricError
from q_guardian.observability.metrics.aggregators import MetricAggregator
from q_guardian.utils.datetime_utils import get_utc_now

logger = structlog.get_logger("observability.metrics.engine")

_DEFAULT_MAX_POINTS = 10_000


class MetricsEngine:
    """Thread-safe metrics engine for recording, querying, and aggregating metrics."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._metrics: dict[str, Metric] = {}
        self._lock = threading.Lock()
        self._max_points = self._config.get("max_series_per_metric", _DEFAULT_MAX_POINTS)
        self._initialized = False
        self._histogram_buffers: dict[str, deque[float]] = {}

    def initialize(self) -> None:
        with self._lock:
            self._initialized = True
            logger.info(
                "metrics_engine_initialized",
                max_points=self._max_points,
            )

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise MetricError(
                message="MetricsEngine has not been initialized",
                details={"hint": "Call initialize() first"},
            )

    def _get_or_create_metric(
        self,
        name: str,
        metric_type: MetricType,
        unit: MetricUnit = MetricUnit.NONE,
    ) -> Metric:
        if name not in self._metrics:
            self._metrics[name] = Metric(
                name=name,
                metric_type=metric_type,
                unit=unit,
            )
            logger.debug("metric_created", name=name, metric_type=metric_type.value)
        return self._metrics[name]

    def _trim_points(self, metric: Metric) -> None:
        if len(metric.points) > self._max_points:
            metric.points = metric.points[-self._max_points :]

    def _get_or_create_histogram_buffer(self, name: str) -> deque[float]:
        if name not in self._histogram_buffers:
            max_size = self._config.get("histogram_max_size", self._max_points)
            self._histogram_buffers[name] = deque(maxlen=max_size)
        return self._histogram_buffers[name]

    def record_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        with self._lock:
            self._ensure_initialized()
            metric = self._get_or_create_metric(name, MetricType.COUNTER)
            merged_labels = {**metric.labels, **(labels or {})}
            if not metric.labels:
                metric.labels = merged_labels
            metric.add_point(value, labels)
            self._trim_points(metric)
            logger.debug(
                "counter_recorded",
                name=name,
                value=value,
                total_points=len(metric.points),
            )

    def record_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        with self._lock:
            self._ensure_initialized()
            metric = self._get_or_create_metric(name, MetricType.GAUGE)
            merged_labels = {**metric.labels, **(labels or {})}
            if not metric.labels:
                metric.labels = merged_labels
            metric.add_point(value, labels)
            self._trim_points(metric)
            logger.debug("gauge_recorded", name=name, value=value)

    def record_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        with self._lock:
            self._ensure_initialized()
            metric = self._get_or_create_metric(name, MetricType.HISTOGRAM)
            merged_labels = {**metric.labels, **(labels or {})}
            if not metric.labels:
                metric.labels = merged_labels
            metric.add_point(value, labels)
            self._trim_points(metric)
            buffer = self._get_or_create_histogram_buffer(name)
            buffer.append(value)
            logger.debug(
                "histogram_recorded",
                name=name,
                value=value,
                buffer_size=len(buffer),
            )

    def record_timer(
        self,
        name: str,
        duration_ms: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        with self._lock:
            self._ensure_initialized()
            metric = self._get_or_create_metric(name, MetricType.TIMER, MetricUnit.MILLISECONDS)
            merged_labels = {**metric.labels, **(labels or {})}
            if not metric.labels:
                metric.labels = merged_labels
            metric.add_point(duration_ms, labels)
            self._trim_points(metric)
            buffer = self._get_or_create_histogram_buffer(name)
            buffer.append(duration_ms)
            logger.debug(
                "timer_recorded",
                name=name,
                duration_ms=duration_ms,
            )

    def get_metric(self, name: str) -> Metric | None:
        with self._lock:
            return self._metrics.get(name)

    def get_all_metrics(self) -> dict[str, Metric]:
        with self._lock:
            return dict(self._metrics)

    def aggregate(
        self,
        name: str,
        aggregation: AggregationType,
        window: TimeWindow | None = None,
        percentile: float | None = None,
    ) -> AggregatedMetric:
        with self._lock:
            self._ensure_initialized()
            metric = self._metrics.get(name)
            if metric is None:
                raise MetricError(
                    message=f"Metric '{name}' not found",
                    details={"metric_name": name},
                )

            if window is not None:
                values = metric.values_in_window(window)
            else:
                values = [p.value for p in metric.points]

            if not values:
                return AggregatedMetric(
                    name=name,
                    aggregation=aggregation.value,
                    value=0.0,
                    count=0,
                    window=window,
                )

            effective_percentile = percentile if percentile is not None else 95.0
            return MetricAggregator.compute(values, aggregation, effective_percentile)

    def get_counter_value(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float:
        with self._lock:
            metric = self._metrics.get(name)
            if metric is None:
                return 0.0
            if labels is not None:
                values = [
                    p.value
                    for p in metric.points
                    if all(p.labels.get(k) == v for k, v in labels.items())
                ]
                return sum(values)
            return sum(p.value for p in metric.points)

    def get_gauge_value(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float | None:
        with self._lock:
            metric = self._metrics.get(name)
            if metric is None or not metric.points:
                return None
            if labels is not None:
                filtered = [
                    p for p in metric.points if all(p.labels.get(k) == v for k, v in labels.items())
                ]
                if not filtered:
                    return None
                return filtered[-1].value
            return metric.points[-1].value

    def get_percentile(
        self,
        name: str,
        percentile: float,
        labels: dict[str, str] | None = None,
    ) -> float | None:
        with self._lock:
            metric = self._metrics.get(name)
            if metric is None or not metric.points:
                return None
            if labels is not None:
                values = [
                    p.value
                    for p in metric.points
                    if all(p.labels.get(k) == v for k, v in labels.items())
                ]
            else:
                values = [p.value for p in metric.points]
            if not values:
                return None
            return MetricAggregator.aggregate_percentile(values, percentile)

    def get_rate(
        self,
        name: str,
        window_seconds: int = 60,
        labels: dict[str, str] | None = None,
    ) -> float:
        with self._lock:
            metric = self._metrics.get(name)
            if metric is None or not metric.points:
                return 0.0
            now = get_utc_now()
            window = TimeWindow(
                start=now,
                end=now,
            )
            from datetime import timedelta

            window = TimeWindow(
                start=now - timedelta(seconds=window_seconds),
                end=now,
            )
            if labels is not None:
                values = [
                    p.value
                    for p in metric.points
                    if window.contains(p.timestamp)
                    and all(p.labels.get(k) == v for k, v in labels.items())
                ]
            else:
                values = [p.value for p in metric.points if window.contains(p.timestamp)]
            return MetricAggregator.aggregate_rate(values, window_seconds)

    def reset(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self._metrics.clear()
                self._histogram_buffers.clear()
                logger.info("all_metrics_reset")
            else:
                self._metrics.pop(name, None)
                self._histogram_buffers.pop(name, None)
                logger.info("metric_reset", name=name)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "initialized": self._initialized,
                "metric_count": len(self._metrics),
                "metrics": {
                    name: {
                        "metric_id": m.metric_id,
                        "name": m.name,
                        "metric_type": m.metric_type.value,
                        "unit": m.unit.value,
                        "point_count": len(m.points),
                        "latest_value": m.latest_value(),
                        "labels": m.labels,
                    }
                    for name, m in self._metrics.items()
                },
            }
