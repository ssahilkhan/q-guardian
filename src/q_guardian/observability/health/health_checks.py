from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import structlog

from q_guardian.observability.data import HealthCheckResult
from q_guardian.observability.enums import HealthStatus

logger = structlog.get_logger("observability.health_checks")


class HealthCheck(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def check(self) -> HealthCheckResult: ...


class FrameworkHealthCheck(HealthCheck):
    def __init__(self) -> None:
        self._start_time: float = time.time()

    @property
    def name(self) -> str:
        return "framework"

    def check(self) -> HealthCheckResult:
        start = time.monotonic()
        try:
            uptime = time.time() - self._start_time
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component=self.name,
                status=HealthStatus.HEALTHY,
                message="Framework is operational",
                latency_ms=latency_ms,
                details={
                    "uptime_seconds": uptime,
                    "checked_at": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=latency_ms,
                details={"error": str(e)},
            )


class PluginManagerHealthCheck(HealthCheck):
    def __init__(self, plugin_registry: Any | None = None) -> None:
        self._plugin_registry = plugin_registry

    @property
    def name(self) -> str:
        return "plugin_manager"

    def check(self) -> HealthCheckResult:
        start = time.monotonic()
        try:
            plugin_count = 0
            if self._plugin_registry is not None:
                if hasattr(self._plugin_registry, "list_plugins"):
                    plugin_count = len(self._plugin_registry.list_plugins())
                elif hasattr(self._plugin_registry, "count"):
                    plugin_count = self._plugin_registry.count()

            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component=self.name,
                status=HealthStatus.HEALTHY,
                message=f"Plugin manager operational with {plugin_count} plugins",
                latency_ms=latency_ms,
                details={"plugin_count": plugin_count},
            )
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=latency_ms,
                details={"error": str(e)},
            )


class StorageHealthCheck(HealthCheck):
    def __init__(self, storage: Any | None = None) -> None:
        self._storage = storage

    @property
    def name(self) -> str:
        return "storage"

    def check(self) -> HealthCheckResult:
        start = time.monotonic()
        try:
            if self._storage is None:
                latency_ms = (time.monotonic() - start) * 1000
                return HealthCheckResult(
                    component=self.name,
                    status=HealthStatus.UNKNOWN,
                    message="No storage backend configured",
                    latency_ms=latency_ms,
                    details={"configured": False},
                )

            readable = hasattr(self._storage, "read") or hasattr(self._storage, "get")
            writable = hasattr(self._storage, "write") or hasattr(self._storage, "save")

            if readable and writable:
                status = HealthStatus.HEALTHY
                message = "Storage is accessible and read/write capable"
            elif readable:
                status = HealthStatus.DEGRADED
                message = "Storage is readable but not writable"
            else:
                status = HealthStatus.UNHEALTHY
                message = "Storage is not accessible"

            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component=self.name,
                status=status,
                message=message,
                latency_ms=latency_ms,
                details={"configured": True, "readable": readable, "writable": writable},
            )
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=latency_ms,
                details={"error": str(e)},
            )


class MetricsHealthCheck(HealthCheck):
    def __init__(self, metrics_engine: Any | None = None) -> None:
        self._metrics_engine = metrics_engine

    @property
    def name(self) -> str:
        return "metrics"

    def check(self) -> HealthCheckResult:
        start = time.monotonic()
        try:
            if self._metrics_engine is None:
                latency_ms = (time.monotonic() - start) * 1000
                return HealthCheckResult(
                    component=self.name,
                    status=HealthStatus.UNKNOWN,
                    message="No metrics engine configured",
                    latency_ms=latency_ms,
                    details={"configured": False},
                )

            metric_count = 0
            if hasattr(self._metrics_engine, "list_metrics"):
                metric_count = len(self._metrics_engine.list_metrics())
            elif hasattr(self._metrics_engine, "_metrics"):
                metric_count = len(self._metrics_engine._metrics)

            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component=self.name,
                status=HealthStatus.HEALTHY,
                message=f"Metrics engine operational with {metric_count} metrics",
                latency_ms=latency_ms,
                details={"configured": True, "metric_count": metric_count},
            )
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=latency_ms,
                details={"error": str(e)},
            )
