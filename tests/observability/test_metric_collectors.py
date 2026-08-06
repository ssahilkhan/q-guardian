from q_guardian.observability.data import Metric
from q_guardian.observability.enums import MetricType
from q_guardian.observability.metrics.collectors import (
    CustomMetricCollector,
    MetricCollector,
    PluginMetricsCollector,
    SystemMetricsCollector,
)


class TestSystemMetricsCollector:
    def test_instantiation_and_name(self):
        collector = SystemMetricsCollector()
        assert collector.name == "system_metrics"

    def test_collect(self):
        collector = SystemMetricsCollector()
        metrics = collector.collect()
        assert isinstance(metrics, list)
        assert len(metrics) == 4
        assert all(isinstance(m, Metric) for m in metrics)
        assert metrics[0].name == "system.uptime"


class TestPluginMetricsCollector:
    def test_instantiation_and_name(self):
        collector = PluginMetricsCollector()
        assert collector.name == "plugin_metrics"

    def test_register_plugin_and_collect(self):
        collector = PluginMetricsCollector()
        collector.register_plugin("test_plugin")
        collector.record_plugin_request("test_plugin", 100.0)
        collector.record_plugin_error("test_plugin")
        metrics = collector.collect()
        assert len(metrics) == 3
        names = {m.name for m in metrics}
        assert names == {"plugin.total_requests", "plugin.total_errors", "plugin.total_latency_ms"}

    def test_record_plugin_request_auto_registers(self):
        collector = PluginMetricsCollector()
        collector.record_plugin_request("auto_plugin", 50.0)
        metrics = collector.collect()
        requests_metric = next(m for m in metrics if m.name == "plugin.total_requests")
        assert requests_metric.points[0].value == 1.0


class TestCustomMetricCollector:
    def test_instantiation_and_default_name(self):
        collector = CustomMetricCollector()
        assert collector.name == "custom"

    def test_custom_name(self):
        collector = CustomMetricCollector("my_collector")
        assert collector.name == "my_collector"

    def test_add_metric_and_collect(self):
        collector = CustomMetricCollector()
        m = Metric(name="custom.test", metric_type=MetricType.GAUGE)
        collector.add_metric(m)
        metrics = collector.collect()
        assert len(metrics) == 1
        assert metrics[0].name == "custom.test"

    def test_remove_metric(self):
        collector = CustomMetricCollector()
        m = Metric(name="custom.test", metric_type=MetricType.GAUGE)
        collector.add_metric(m)
        assert collector.remove_metric("custom.test") is True
        assert collector.collect() == []

    def test_remove_metric_not_found(self):
        collector = CustomMetricCollector()
        assert collector.remove_metric("nonexistent") is False


class TestCollectorInterfaces:
    def test_system_collector_is_metric_collector(self):
        assert isinstance(SystemMetricsCollector(), MetricCollector)

    def test_plugin_collector_is_metric_collector(self):
        assert isinstance(PluginMetricsCollector(), MetricCollector)

    def test_custom_collector_is_metric_collector(self):
        assert isinstance(CustomMetricCollector(), MetricCollector)

    def test_all_collectors_have_name_and_collect(self):
        collectors = [
            SystemMetricsCollector(),
            PluginMetricsCollector(),
            CustomMetricCollector(),
        ]
        for c in collectors:
            assert hasattr(c, "name")
            assert hasattr(c, "collect")
            assert callable(c.collect)
