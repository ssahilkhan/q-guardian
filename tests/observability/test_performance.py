import pytest
import threading
import time

from q_guardian.observability.metrics.metrics_engine import MetricsEngine
from q_guardian.observability.health.health_engine import HealthEngine
from q_guardian.observability.tracing.trace_engine import TraceEngine
from q_guardian.observability.analytics.analytics_engine import AnalyticsEngine
from q_guardian.observability.alerts.alert_engine import AlertEngine
from q_guardian.observability.data import AlertRule
from q_guardian.observability.enums import AlertSeverity, AlertType, AggregationType, MetricType


def _init_metrics_engine() -> MetricsEngine:
    engine = MetricsEngine()
    engine.initialize()
    return engine


def _init_health_engine() -> HealthEngine:
    engine = HealthEngine()
    engine.initialize()
    return engine


def _init_trace_engine() -> TraceEngine:
    engine = TraceEngine({"max_traces": 100000})
    engine.initialize()
    return engine


def _init_analytics_engine() -> AnalyticsEngine:
    engine = AnalyticsEngine()
    engine.initialize()
    return engine


def _init_alert_engine() -> AlertEngine:
    engine = AlertEngine()
    engine.initialize()
    return engine


class TestMetricsEnginePerformance:
    def test_rapid_counter_recording(self):
        engine = _init_metrics_engine()
        start = time.perf_counter()
        for i in range(1000):
            engine.record_counter("rapid_counter", value=float(i))
        elapsed = time.perf_counter() - start
        metric = engine.get_metric("rapid_counter")
        assert metric is not None
        assert len(metric.points) == 1000
        assert elapsed < 5.0

    def test_aggregate_performance_large_dataset(self):
        engine = _init_metrics_engine()
        for i in range(5000):
            engine.record_counter("agg_metric", value=float(i % 100))
        start = time.perf_counter()
        result = engine.aggregate("agg_metric", aggregation=AggregationType.SUM)
        elapsed = time.perf_counter() - start
        assert result.count == 5000
        assert elapsed < 2.0


class TestTraceEnginePerformance:
    def test_many_concurrent_traces(self):
        engine = _init_trace_engine()
        start = time.perf_counter()
        for i in range(500):
            trace = engine.start_trace(correlation_id=f"corr-{i}", execution_id=f"exec-{i}")
            span = engine.start_span(trace.trace_id, f"span-{i}")
            engine.finish_span(trace.trace_id, span.span_id)
            engine.finish_trace(trace.trace_id)
        elapsed = time.perf_counter() - start
        all_traces = engine.get_all_traces()
        assert len(all_traces) == 500
        assert elapsed < 10.0


class TestHealthEnginePerformance:
    def test_many_component_registrations(self):
        engine = _init_health_engine()
        start = time.perf_counter()
        for i in range(500):
            engine.register_component(f"component_{i}")
        elapsed = time.perf_counter() - start
        report = engine.get_health_report()
        assert len(report.components) == 500
        assert elapsed < 5.0


class TestAnalyticsEnginePerformance:
    def test_many_event_ingestions(self):
        engine = _init_analytics_engine()
        start = time.perf_counter()
        for i in range(1000):
            engine.ingest_event({"type": "threat.detected", "value": float(i), "confidence": 0.8})
        elapsed = time.perf_counter() - start
        info = engine.to_dict()
        assert info["total_events"] == 1000
        assert elapsed < 5.0

    def test_generate_report_performance(self):
        engine = _init_analytics_engine()
        for i in range(500):
            engine.ingest_event({"type": "threat.detected", "value": float(i % 10)})
            engine.ingest_event({"type": "policy.evaluated", "value": float(i % 5)})
        start = time.perf_counter()
        report = engine.generate_report()
        elapsed = time.perf_counter() - start
        assert report is not None
        assert elapsed < 5.0


class TestAlertEnginePerformance:
    def test_many_rule_evaluations(self):
        engine = _init_alert_engine()
        metrics_engine = _init_metrics_engine()
        engine.initialize(metrics_engine=metrics_engine)
        for i in range(100):
            rule = AlertRule(
                name=f"rule_{i}",
                metric_name="test_metric",
                condition="gt",
                threshold=float(i),
                severity=AlertSeverity.HIGH,
                alert_type=AlertType.THRESHOLD,
            )
            engine.add_rule(rule)
        metrics_engine.record_counter("test_metric", value=50.0)
        start = time.perf_counter()
        engine.evaluate_rules()
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0


class TestThreadSafety:
    def test_record_counter_from_multiple_threads(self):
        engine = _init_metrics_engine()
        errors = []

        def worker(thread_id):
            try:
                for i in range(100):
                    engine.record_counter(
                        "threaded_counter",
                        value=1.0,
                        labels={"thread": str(thread_id)},
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start
        assert len(errors) == 0
        metric = engine.get_metric("threaded_counter")
        assert metric is not None
        assert len(metric.points) == 1000
        assert elapsed < 10.0

    def test_start_trace_from_multiple_threads(self):
        engine = _init_trace_engine()
        errors = []
        trace_ids = []

        def worker(thread_id):
            try:
                for i in range(20):
                    trace = engine.start_trace(correlation_id=f"t-{thread_id}-{i}")
                    trace_ids.append(trace.trace_id)
                    span = engine.start_span(trace.trace_id, f"span-{i}")
                    engine.finish_span(trace.trace_id, span.span_id)
                    engine.finish_trace(trace.trace_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start
        assert len(errors) == 0
        assert len(trace_ids) == 200
        assert elapsed < 15.0


class TestStorageConcurrency:
    def test_concurrent_storage_writes(self):
        from q_guardian.observability.storage import ObservabilityStorage
        from q_guardian.observability.data import Metric
        import tempfile
        import os

        tmpdir = tempfile.mkdtemp()
        storage = ObservabilityStorage(storage_root=tmpdir)
        errors = []

        def worker(thread_id):
            try:
                for i in range(10):
                    m = Metric(
                        name=f"metric_t{thread_id}",
                        metric_type=MetricType.COUNTER,
                    )
                    m.add_point(float(thread_id * 100 + i))
                    storage.save_metric(m)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
