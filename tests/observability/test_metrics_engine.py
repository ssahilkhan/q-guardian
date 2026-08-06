from datetime import UTC, datetime, timedelta

import pytest

from q_guardian.observability.data import TimeWindow
from q_guardian.observability.enums import AggregationType, MetricType, MetricUnit
from q_guardian.observability.exceptions import MetricError
from q_guardian.observability.metrics.metrics_engine import MetricsEngine


class TestMetricsEngineInitialization:
    def test_init_not_initialized_by_default(self):
        engine = MetricsEngine()
        assert engine._initialized is False

    def test_initialize_sets_initialized(self):
        engine = MetricsEngine()
        engine.initialize()
        assert engine._initialized is True

    def test_custom_config(self):
        config = {"max_series_per_metric": 100}
        engine = MetricsEngine(config)
        assert engine._max_points == 100


class TestMetricsEngineRequiresInitialize:
    def test_record_counter_raises_before_init(self):
        engine = MetricsEngine()
        with pytest.raises(MetricError):
            engine.record_counter("test")

    def test_record_gauge_raises_before_init(self):
        engine = MetricsEngine()
        with pytest.raises(MetricError):
            engine.record_gauge("test", 1.0)

    def test_record_histogram_raises_before_init(self):
        engine = MetricsEngine()
        with pytest.raises(MetricError):
            engine.record_histogram("test", 1.0)

    def test_record_timer_raises_before_init(self):
        engine = MetricsEngine()
        with pytest.raises(MetricError):
            engine.record_timer("test", 100.0)

    def test_aggregate_raises_before_init(self):
        engine = MetricsEngine()
        with pytest.raises(MetricError):
            engine.aggregate("test", AggregationType.SUM)


class TestMetricsEngineRecordCounter:
    def test_record_counter_single(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests")
        assert engine.get_counter_value("requests") == 1.0

    def test_record_counter_multiple(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests", 5.0)
        engine.record_counter("requests", 3.0)
        assert engine.get_counter_value("requests") == 8.0

    def test_record_counter_with_labels(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests", 1.0, {"endpoint": "/api"})
        assert engine.get_counter_value("requests", {"endpoint": "/api"}) == 1.0

    def test_record_counter_empty_labels(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests", 1.0, {})
        assert engine.get_counter_value("requests") == 1.0


class TestMetricsEngineRecordGauge:
    def test_record_gauge_single(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_gauge("temperature", 36.5)
        assert engine.get_gauge_value("temperature") == 36.5

    def test_record_gauge_multiple(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_gauge("temperature", 36.5)
        engine.record_gauge("temperature", 37.0)
        assert engine.get_gauge_value("temperature") == 37.0

    def test_record_gauge_with_labels(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_gauge("temperature", 36.5, {"sensor": "cpu"})
        assert engine.get_gauge_value("temperature", {"sensor": "cpu"}) == 36.5

    def test_record_gauge_empty_labels(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_gauge("temperature", 36.5, {})
        assert engine.get_gauge_value("temperature") == 36.5


class TestMetricsEngineRecordHistogram:
    def test_record_histogram_with_labels(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_histogram("latency", 100.0, {"endpoint": "/api"})
        metric = engine.get_metric("latency")
        assert metric is not None
        assert metric.metric_type == MetricType.HISTOGRAM

    def test_record_histogram_multiple(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_histogram("latency", 100.0)
        engine.record_histogram("latency", 200.0)
        metric = engine.get_metric("latency")
        assert len(metric.points) == 2


class TestMetricsEngineRecordTimer:
    def test_record_timer_with_labels(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_timer("response_time", 150.0, {"endpoint": "/api"})
        metric = engine.get_metric("response_time")
        assert metric is not None
        assert metric.metric_type == MetricType.TIMER
        assert metric.unit == MetricUnit.MILLISECONDS


class TestMetricsEngineGetMetric:
    def test_get_metric_returns_metric(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests")
        metric = engine.get_metric("requests")
        assert metric is not None
        assert metric.name == "requests"

    def test_get_metric_returns_none_for_missing(self):
        engine = MetricsEngine()
        engine.initialize()
        assert engine.get_metric("nonexistent") is None

    def test_get_all_metrics_returns_dict(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests")
        engine.record_gauge("temperature", 36.5)
        all_metrics = engine.get_all_metrics()
        assert isinstance(all_metrics, dict)
        assert len(all_metrics) == 2


class TestMetricsEngineGetCounterValue:
    def test_get_counter_value_with_labels(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests", 1.0, {"endpoint": "/api"})
        engine.record_counter("requests", 1.0, {"endpoint": "/api"})
        assert engine.get_counter_value("requests", {"endpoint": "/api"}) == 2.0

    def test_get_counter_value_returns_zero_for_missing(self):
        engine = MetricsEngine()
        engine.initialize()
        assert engine.get_counter_value("nonexistent") == 0.0


class TestMetricsEngineGetGaugeValue:
    def test_get_gauge_value_with_labels(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_gauge("temperature", 36.5, {"sensor": "cpu"})
        engine.record_gauge("temperature", 37.0, {"sensor": "cpu"})
        assert engine.get_gauge_value("temperature", {"sensor": "cpu"}) == 37.0

    def test_get_gauge_value_returns_none_for_missing(self):
        engine = MetricsEngine()
        engine.initialize()
        assert engine.get_gauge_value("nonexistent") is None


class TestMetricsEngineGetPercentile:
    def test_get_percentile_p50(self):
        engine = MetricsEngine()
        engine.initialize()
        for v in [1, 2, 3, 4, 5]:
            engine.record_histogram("latency", float(v))
        p50 = engine.get_percentile("latency", 50.0)
        assert p50 == 3.0

    def test_get_percentile_p95(self):
        engine = MetricsEngine()
        engine.initialize()
        for v in range(1, 101):
            engine.record_histogram("latency", float(v))
        p95 = engine.get_percentile("latency", 95.0)
        assert p95 == pytest.approx(95.0, abs=0.1)

    def test_get_percentile_p99(self):
        engine = MetricsEngine()
        engine.initialize()
        for v in range(1, 101):
            engine.record_histogram("latency", float(v))
        p99 = engine.get_percentile("latency", 99.0)
        assert p99 == pytest.approx(99.0, abs=0.1)

    def test_get_percentile_returns_none_for_missing(self):
        engine = MetricsEngine()
        engine.initialize()
        assert engine.get_percentile("nonexistent", 95.0) is None


class TestMetricsEngineGetRate:
    def test_get_rate(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests", 60.0)
        rate = engine.get_rate("requests", window_seconds=60)
        assert rate > 0


class TestMetricsEngineAggregate:
    def test_aggregate_sum(self):
        engine = MetricsEngine()
        engine.initialize()
        for v in [1, 2, 3, 4, 5]:
            engine.record_counter("requests", float(v))
        result = engine.aggregate("requests", AggregationType.SUM)
        assert result.value == 15.0

    def test_aggregate_average(self):
        engine = MetricsEngine()
        engine.initialize()
        for v in [1, 2, 3, 4, 5]:
            engine.record_counter("requests", float(v))
        result = engine.aggregate("requests", AggregationType.AVERAGE)
        assert result.value == 3.0

    def test_aggregate_min(self):
        engine = MetricsEngine()
        engine.initialize()
        for v in [3, 1, 4, 1, 5]:
            engine.record_counter("requests", float(v))
        result = engine.aggregate("requests", AggregationType.MIN)
        assert result.value == 1.0

    def test_aggregate_max(self):
        engine = MetricsEngine()
        engine.initialize()
        for v in [3, 1, 4, 1, 5]:
            engine.record_counter("requests", float(v))
        result = engine.aggregate("requests", AggregationType.MAX)
        assert result.value == 5.0

    def test_aggregate_count(self):
        engine = MetricsEngine()
        engine.initialize()
        for _ in range(10):
            engine.record_counter("requests")
        result = engine.aggregate("requests", AggregationType.COUNT)
        assert result.count == 10

    def test_aggregate_last(self):
        engine = MetricsEngine()
        engine.initialize()
        for v in [1, 2, 3]:
            engine.record_counter("requests", float(v))
        result = engine.aggregate("requests", AggregationType.LAST)
        assert result.value == 3.0

    def test_aggregate_percentile(self):
        engine = MetricsEngine()
        engine.initialize()
        for v in range(1, 101):
            engine.record_histogram("latency", float(v))
        result = engine.aggregate("latency", AggregationType.PERCENTILE, percentile=95.0)
        assert result.value == pytest.approx(95.0, abs=0.1)

    def test_aggregate_raises_for_missing_metric(self):
        engine = MetricsEngine()
        engine.initialize()
        with pytest.raises(MetricError):
            engine.aggregate("nonexistent", AggregationType.SUM)

    def test_aggregate_with_window(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests", 10.0)
        now = datetime.now(UTC)
        window = TimeWindow(start=now - timedelta(hours=1), end=now)
        result = engine.aggregate("requests", AggregationType.SUM, window=window)
        assert result.value == 10.0


class TestMetricsEngineReset:
    def test_reset_single_metric(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests")
        engine.record_gauge("temperature", 36.5)
        engine.reset("requests")
        assert engine.get_metric("requests") is None
        assert engine.get_metric("temperature") is not None

    def test_reset_all_metrics(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests")
        engine.record_gauge("temperature", 36.5)
        engine.reset()
        assert engine.get_all_metrics() == {}


class TestMetricsEngineToDict:
    def test_to_dict_returns_structured_data(self):
        engine = MetricsEngine()
        engine.initialize()
        engine.record_counter("requests", 5.0)
        d = engine.to_dict()
        assert d["initialized"] is True
        assert d["metric_count"] == 1
        assert "requests" in d["metrics"]

    def test_to_dict_without_metrics(self):
        engine = MetricsEngine()
        engine.initialize()
        d = engine.to_dict()
        assert d["metric_count"] == 0
        assert d["metrics"] == {}


class TestMetricsEngineMaxPoints:
    def test_max_points_trimming(self):
        engine = MetricsEngine({"max_series_per_metric": 5})
        engine.initialize()
        for _i in range(10):
            engine.record_counter("requests", 1.0)
        metric = engine.get_metric("requests")
        assert len(metric.points) <= 5


class TestMetricsEngineThreadSafety:
    def test_thread_safety(self):
        import threading

        engine = MetricsEngine()
        engine.initialize()
        errors = []

        def record():
            try:
                for _ in range(50):
                    engine.record_counter("requests", 1.0)
                    engine.record_gauge("temp", float(_))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
