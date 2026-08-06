import contextlib

from q_guardian.observability.alerts.alert_engine import AlertEngine
from q_guardian.observability.analytics.analytics_engine import AnalyticsEngine
from q_guardian.observability.health.health_engine import HealthEngine
from q_guardian.observability.metrics.metrics_engine import MetricsEngine
from q_guardian.observability.plugin import ObservabilityPlugin
from q_guardian.observability.tracing.trace_engine import TraceEngine


class MockContext:
    def __init__(self):
        from q_guardian.events.bus import EventBus

        self.event_bus = EventBus()


class TestObservabilityPluginMetadata:
    def test_name(self):
        plugin = ObservabilityPlugin()
        assert plugin.name == "observability"

    def test_version(self):
        plugin = ObservabilityPlugin()
        assert plugin.version == "1.0.0"

    def test_author(self):
        plugin = ObservabilityPlugin()
        assert plugin.author == "Q-Guardian Team"

    def test_description(self):
        plugin = ObservabilityPlugin()
        assert plugin.description == "Enterprise observability and operations platform"

    def test_interfaces(self):
        plugin = ObservabilityPlugin()
        assert isinstance(plugin.interfaces, list)
        assert "observability" in plugin.interfaces
        assert "metrics" in plugin.interfaces
        assert "health" in plugin.interfaces
        assert "tracing" in plugin.interfaces
        assert "analytics" in plugin.interfaces
        assert "alerting" in plugin.interfaces


class TestObservabilityPluginLifecycle:
    def test_initialization_creates_engines(self):
        plugin = ObservabilityPlugin()
        ctx = MockContext()
        import asyncio

        asyncio.run(plugin.initialize(ctx))
        assert plugin.metrics_engine is not None
        assert plugin.health_engine is not None
        assert plugin.trace_engine is not None
        assert plugin.analytics_engine is not None
        assert plugin.alert_engine is not None

    def test_health_before_start(self):
        plugin = ObservabilityPlugin()
        health = plugin.health()
        assert health["status"] == "stopped"
        assert health["plugin"] == "observability"

    def test_health_after_start(self):
        plugin = ObservabilityPlugin()
        ctx = MockContext()
        import asyncio

        asyncio.run(plugin.initialize(ctx))
        asyncio.run(plugin.start())
        health = plugin.health()
        assert health["status"] == "healthy"

    def test_configuration_returns_config(self):
        config = {"metrics": {"max_points": 5000}, "tracing": {"max_traces": 500}}
        plugin = ObservabilityPlugin(config=config)
        assert plugin.configuration() == config

    def test_engines_are_created_after_init(self):
        plugin = ObservabilityPlugin()
        assert plugin.metrics_engine is None
        assert plugin.health_engine is None
        ctx = MockContext()
        import asyncio

        asyncio.run(plugin.initialize(ctx))
        assert isinstance(plugin.metrics_engine, MetricsEngine)
        assert isinstance(plugin.health_engine, HealthEngine)
        assert isinstance(plugin.trace_engine, TraceEngine)
        assert isinstance(plugin.analytics_engine, AnalyticsEngine)
        assert isinstance(plugin.alert_engine, AlertEngine)

    def test_stop(self):
        plugin = ObservabilityPlugin()
        ctx = MockContext()
        import asyncio

        asyncio.run(plugin.initialize(ctx))
        asyncio.run(plugin.start())
        with contextlib.suppress(TypeError):
            asyncio.run(plugin.stop())
        health = plugin.health()
        assert health["status"] == "stopped"

    def test_engines_none_before_init(self):
        plugin = ObservabilityPlugin()
        assert plugin.metrics_engine is None
        assert plugin.health_engine is None
        assert plugin.trace_engine is None
        assert plugin.analytics_engine is None
        assert plugin.alert_engine is None

    def test_engines_report_status_in_health(self):
        plugin = ObservabilityPlugin()
        ctx = MockContext()
        import asyncio

        asyncio.run(plugin.initialize(ctx))
        asyncio.run(plugin.start())
        health = plugin.health()
        engines = health["engines"]
        assert engines["metrics"] is True
        assert engines["health"] is True
        assert engines["tracing"] is True
        assert engines["analytics"] is True
        assert engines["alerts"] is True
