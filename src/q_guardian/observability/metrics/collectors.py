"""MetricCollector implementations for collecting various metric sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

from q_guardian.observability.data import Metric, MetricPoint
from q_guardian.observability.enums import MetricType, MetricUnit
from q_guardian.utils.datetime_utils import get_utc_now

logger = structlog.get_logger("observability.metrics.collectors")


class MetricCollector(ABC):
    """Abstract base class for metric collectors."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def collect(self) -> list[Metric]: ...


class SystemMetricsCollector(MetricCollector):
    """Collects framework-level system metrics."""

    def __init__(self) -> None:
        self._collected: list[Metric] = []

    @property
    def name(self) -> str:
        return "system_metrics"

    def collect(self) -> list[Metric]:
        metrics: list[Metric] = []
        now = get_utc_now()

        uptime_metric = Metric(
            name="system.uptime",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.SECONDS,
        )
        uptime_metric.points.append(
            MetricPoint(timestamp=now, value=0.0, labels={"component": "framework"})
        )
        metrics.append(uptime_metric)

        requests_metric = Metric(
            name="system.total_requests",
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.COUNT,
        )
        requests_metric.points.append(
            MetricPoint(timestamp=now, value=0.0, labels={"component": "framework"})
        )
        metrics.append(requests_metric)

        memory_metric = Metric(
            name="system.memory_usage",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.BYTES,
        )
        memory_metric.points.append(
            MetricPoint(timestamp=now, value=0.0, labels={"component": "framework"})
        )
        metrics.append(memory_metric)

        queue_metric = Metric(
            name="system.queue_size",
            metric_type=MetricType.GAUGE,
            unit=MetricUnit.COUNT,
        )
        queue_metric.points.append(
            MetricPoint(timestamp=now, value=0.0, labels={"component": "framework"})
        )
        metrics.append(queue_metric)

        self._collected.extend(metrics)
        logger.debug("system_metrics_collected", count=len(metrics))
        return metrics


class PluginMetricsCollector(MetricCollector):
    """Collects per-plugin metrics."""

    def __init__(self) -> None:
        self._plugin_metrics: dict[str, dict[str, Any]] = {}
        self._collected: list[Metric] = []

    @property
    def name(self) -> str:
        return "plugin_metrics"

    def register_plugin(self, plugin_name: str) -> None:
        self._plugin_metrics[plugin_name] = {
            "requests": 0.0,
            "errors": 0.0,
            "latency_ms": 0.0,
        }

    def record_plugin_request(self, plugin_name: str, latency_ms: float = 0.0) -> None:
        if plugin_name not in self._plugin_metrics:
            self.register_plugin(plugin_name)
        self._plugin_metrics[plugin_name]["requests"] += 1.0
        self._plugin_metrics[plugin_name]["latency_ms"] += latency_ms

    def record_plugin_error(self, plugin_name: str) -> None:
        if plugin_name not in self._plugin_metrics:
            self.register_plugin(plugin_name)
        self._plugin_metrics[plugin_name]["errors"] += 1.0

    def collect(self) -> list[Metric]:
        metrics: list[Metric] = []
        now = get_utc_now()

        requests_metric = Metric(
            name="plugin.total_requests",
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.COUNT,
        )
        errors_metric = Metric(
            name="plugin.total_errors",
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.COUNT,
        )
        latency_metric = Metric(
            name="plugin.total_latency_ms",
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.MILLISECONDS,
        )

        for plugin_name, data in self._plugin_metrics.items():
            labels = {"plugin": plugin_name}
            requests_metric.points.append(
                MetricPoint(
                    timestamp=now,
                    value=data["requests"],
                    labels=labels,
                )
            )
            errors_metric.points.append(
                MetricPoint(
                    timestamp=now,
                    value=data["errors"],
                    labels=labels,
                )
            )
            latency_metric.points.append(
                MetricPoint(
                    timestamp=now,
                    value=data["latency_ms"],
                    labels=labels,
                )
            )

        metrics.extend([requests_metric, errors_metric, latency_metric])
        self._collected.extend(metrics)
        logger.debug(
            "plugin_metrics_collected", count=len(metrics), plugins=len(self._plugin_metrics)
        )
        return metrics


class CustomMetricCollector(MetricCollector):
    """Collector for user-defined custom metrics."""

    def __init__(self, collector_name: str = "custom") -> None:
        self._collector_name = collector_name
        self._custom_metrics: list[Metric] = []

    @property
    def name(self) -> str:
        return self._collector_name

    def add_metric(self, metric: Metric) -> None:
        self._custom_metrics.append(metric)

    def remove_metric(self, name: str) -> bool:
        for i, m in enumerate(self._custom_metrics):
            if m.name == name:
                self._custom_metrics.pop(i)
                return True
        return False

    def collect(self) -> list[Metric]:
        logger.debug(
            "custom_metrics_collected",
            collector_name=self._collector_name,
            count=len(self._custom_metrics),
        )
        return list(self._custom_metrics)
