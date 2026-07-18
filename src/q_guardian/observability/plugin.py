"""Observability Plugin — integrates with the Q-Guardian plugin architecture."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.plugins.base import Plugin

if True:  # TYPE_CHECKING
    from q_guardian.framework.context import FrameworkContext

logger = structlog.get_logger("observability.plugin")


class ObservabilityPlugin(Plugin):
    """Plugin that provides full observability into the Q-Guardian framework.

    Integrates metrics, tracing, health, analytics, and alerts
    into the framework plugin lifecycle.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._context: FrameworkContext | None = None
        self._started = False
        self._metrics_engine = None
        self._health_engine = None
        self._trace_engine = None
        self._analytics_engine = None
        self._alert_engine = None

    @property
    def name(self) -> str:
        return "observability"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def author(self) -> str:
        return "Q-Guardian Team"

    @property
    def description(self) -> str:
        return "Enterprise observability and operations platform"

    @property
    def interfaces(self) -> list[str]:
        return [
            "observability",
            "metrics",
            "health",
            "tracing",
            "analytics",
            "alerting",
        ]

    async def initialize(self, context: FrameworkContext) -> None:
        self._context = context
        logger.info("observability_plugin_initializing")
        await self._setup_engines()

    async def start(self) -> None:
        self._started = True
        logger.info("observability_plugin_started")
        await self._subscribe_to_events()

    async def stop(self) -> None:
        self._started = False
        if self._trace_engine is not None:
            await self._trace_engine.shutdown()
        if self._alert_engine is not None:
            await self._alert_engine.shutdown()
        logger.info("observability_plugin_stopped")

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._started else "stopped",
            "plugin": self.name,
            "engines": {
                "metrics": self._metrics_engine is not None,
                "health": self._health_engine is not None,
                "tracing": self._trace_engine is not None,
                "analytics": self._analytics_engine is not None,
                "alerts": self._alert_engine is not None,
            },
        }

    def configuration(self) -> dict[str, Any]:
        return self._config

    @property
    def metrics_engine(self):
        return self._metrics_engine

    @property
    def health_engine(self):
        return self._health_engine

    @property
    def trace_engine(self):
        return self._trace_engine

    @property
    def analytics_engine(self):
        return self._analytics_engine

    @property
    def alert_engine(self):
        return self._alert_engine

    async def _setup_engines(self) -> None:
        from q_guardian.observability.metrics.metrics_engine import MetricsEngine
        from q_guardian.observability.health.health_engine import HealthEngine
        from q_guardian.observability.tracing.trace_engine import TraceEngine
        from q_guardian.observability.analytics.analytics_engine import AnalyticsEngine
        from q_guardian.observability.alerts.alert_engine import AlertEngine

        self._metrics_engine = MetricsEngine(config=self._config.get("metrics", {}))
        self._health_engine = HealthEngine(config=self._config.get("health", {}))
        self._trace_engine = TraceEngine(config=self._config.get("tracing", {}))
        self._analytics_engine = AnalyticsEngine(config=self._config.get("analytics", {}))
        self._alert_engine = AlertEngine(config=self._config.get("alerts", {}))

        self._metrics_engine.initialize()
        self._health_engine.initialize()
        self._trace_engine.initialize()
        self._analytics_engine.initialize()
        self._alert_engine.initialize(
            metrics_engine=self._metrics_engine,
        )

    async def _subscribe_to_events(self) -> None:
        if self._context is None or not hasattr(self._context, "event_bus"):
            return
        bus = self._context.event_bus
        await bus.subscribe("*", self._on_any_event, priority=100)

    async def _on_any_event(self, event: Any) -> None:
        if self._metrics_engine is not None:
            self._metrics_engine.record_counter(
                "observability.events.total",
                labels={"event_type": getattr(event, "event_type", "unknown")},
            )
        if self._analytics_engine is not None:
            self._analytics_engine.ingest_event(event)
