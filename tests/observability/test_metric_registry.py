import pytest

from q_guardian.observability.exceptions import MetricError
from q_guardian.observability.metrics.collectors import (
    CustomMetricCollector,
    SystemMetricsCollector,
)
from q_guardian.observability.metrics.exporters import JsonMetricExporter
from q_guardian.observability.metrics.registry import MetricRegistry


class TestMetricRegistryCreation:
    def test_create_registry(self):
        registry = MetricRegistry()
        assert registry.list_collectors() == []
        assert registry.list_exporters() == []

    def test_to_dict_empty(self):
        registry = MetricRegistry()
        d = registry.to_dict()
        assert d == {"collectors": {}, "exporters": {}}


class TestMetricRegistryCollectors:
    def test_register_collector(self):
        registry = MetricRegistry()
        collector = SystemMetricsCollector()
        registry.register_collector(collector)
        assert collector in registry.list_collectors()

    def test_list_collectors(self):
        registry = MetricRegistry()
        c1 = SystemMetricsCollector()
        c2 = CustomMetricCollector()
        registry.register_collector(c1)
        registry.register_collector(c2)
        assert len(registry.list_collectors()) == 2

    def test_get_collector(self):
        registry = MetricRegistry()
        collector = SystemMetricsCollector()
        registry.register_collector(collector)
        assert registry.get_collector("system_metrics") is collector

    def test_get_collector_nonexistent(self):
        registry = MetricRegistry()
        assert registry.get_collector("nonexistent") is None

    def test_register_duplicate_collector_raises(self):
        registry = MetricRegistry()
        c1 = SystemMetricsCollector()
        registry.register_collector(c1)
        with pytest.raises(MetricError):
            registry.register_collector(c1)

    def test_unregister_collector(self):
        registry = MetricRegistry()
        collector = SystemMetricsCollector()
        registry.register_collector(collector)
        assert registry.unregister_collector("system_metrics") is True
        assert registry.get_collector("system_metrics") is None

    def test_unregister_collector_nonexistent(self):
        registry = MetricRegistry()
        assert registry.unregister_collector("nonexistent") is False


class TestMetricRegistryExporters:
    def test_register_exporter(self):
        registry = MetricRegistry()
        exporter = JsonMetricExporter()
        registry.register_exporter(exporter)
        assert exporter in registry.list_exporters()

    def test_list_exporters(self):
        registry = MetricRegistry()
        e1 = JsonMetricExporter()
        registry.register_exporter(e1)
        assert len(registry.list_exporters()) == 1

    def test_get_exporter(self):
        registry = MetricRegistry()
        exporter = JsonMetricExporter()
        registry.register_exporter(exporter)
        assert registry.get_exporter("json") is exporter

    def test_get_exporter_nonexistent(self):
        registry = MetricRegistry()
        assert registry.get_exporter("nonexistent") is None

    def test_register_duplicate_exporter_raises(self):
        registry = MetricRegistry()
        e1 = JsonMetricExporter()
        registry.register_exporter(e1)
        with pytest.raises(MetricError):
            registry.register_exporter(e1)

    def test_unregister_exporter(self):
        registry = MetricRegistry()
        exporter = JsonMetricExporter()
        registry.register_exporter(exporter)
        assert registry.unregister_exporter("json") is True
        assert registry.get_exporter("json") is None

    def test_unregister_exporter_nonexistent(self):
        registry = MetricRegistry()
        assert registry.unregister_exporter("nonexistent") is False
