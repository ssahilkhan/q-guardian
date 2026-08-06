import pytest

from q_guardian.observability.enums import TraceStatus
from q_guardian.observability.exceptions import TraceError
from q_guardian.observability.tracing.exporters import JsonTraceExporter
from q_guardian.observability.tracing.trace_engine import TraceEngine


class TestTraceEngineInitialization:
    def test_init_not_initialized_by_default(self):
        engine = TraceEngine()
        assert engine._initialized is False

    def test_initialize_sets_initialized(self):
        engine = TraceEngine()
        engine.initialize()
        assert engine._initialized is True

    def test_initialize_idempotent(self):
        engine = TraceEngine()
        engine.initialize()
        engine.initialize()
        assert engine._initialized is True

    def test_custom_config(self):
        engine = TraceEngine({"max_traces": 100, "trace_ttl_seconds": 60})
        assert engine._max_traces == 100
        assert engine._trace_ttl_seconds == 60


class TestTraceEngineStartTrace:
    def test_start_trace_before_init_raises(self):
        engine = TraceEngine()
        with pytest.raises(TraceError):
            engine.start_trace()

    def test_start_trace_without_correlation(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        assert trace is not None
        assert trace.correlation_id == ""

    def test_start_trace_with_correlation_id(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace(correlation_id="corr-123")
        assert trace.correlation_id == "corr-123"

    def test_start_trace_with_labels(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace(labels={"env": "test"})
        assert trace.labels == {"env": "test"}


class TestTraceEngineGetTrace:
    def test_get_trace_returns_trace(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        assert engine.get_trace(trace.trace_id) is trace

    def test_get_trace_returns_none_for_missing(self):
        engine = TraceEngine()
        engine.initialize()
        assert engine.get_trace("nonexistent") is None


class TestTraceEngineFinishTrace:
    def test_finish_trace(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        finished = engine.finish_trace(trace.trace_id)
        assert finished is not None
        assert finished.status == TraceStatus.COMPLETED

    def test_finish_trace_with_status(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        finished = engine.finish_trace(trace.trace_id, status=TraceStatus.ERROR)
        assert finished.status == TraceStatus.ERROR

    def test_finish_trace_nonexistent(self):
        engine = TraceEngine()
        engine.initialize()
        assert engine.finish_trace("nonexistent") is None


class TestTraceEngineStartSpan:
    def test_start_span(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        span = engine.start_span(trace.trace_id, "test-span")
        assert span is not None
        assert span.name == "test-span"

    def test_start_span_on_nonexistent_trace_returns_none(self):
        engine = TraceEngine()
        engine.initialize()
        span = engine.start_span("nonexistent", "test-span")
        assert span is None

    def test_start_span_with_parent(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        parent = engine.start_span(trace.trace_id, "parent")
        child = engine.start_span(trace.trace_id, "child", parent_span_id=parent.span_id)
        assert child.parent_span_id == parent.span_id


class TestTraceEngineFinishSpan:
    def test_finish_span(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        span = engine.start_span(trace.trace_id, "test-span")
        assert engine.finish_span(trace.trace_id, span.span_id) is True

    def test_finish_span_on_nonexistent_trace_returns_false(self):
        engine = TraceEngine()
        engine.initialize()
        assert engine.finish_span("nonexistent", "span-id") is False


class TestTraceEngineAddSpanEvent:
    def test_add_span_event(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        span = engine.start_span(trace.trace_id, "test-span")
        assert engine.add_span_event(trace.trace_id, span.span_id, "test-event") is True

    def test_add_span_event_nonexistent_trace(self):
        engine = TraceEngine()
        engine.initialize()
        assert engine.add_span_event("nonexistent", "span-id", "event") is False


class TestTraceEngineSetSpanAttribute:
    def test_set_span_attribute(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        span = engine.start_span(trace.trace_id, "test-span")
        assert engine.set_span_attribute(trace.trace_id, span.span_id, "key", "value") is True

    def test_set_span_attribute_nonexistent_trace(self):
        engine = TraceEngine()
        engine.initialize()
        assert engine.set_span_attribute("nonexistent", "span-id", "key", "value") is False


class TestTraceEngineGetAllTraces:
    def test_get_all_traces(self):
        engine = TraceEngine()
        engine.initialize()
        engine.start_trace()
        engine.start_trace()
        all_traces = engine.get_all_traces()
        assert len(all_traces) == 2

    def test_get_all_traces_active_only(self):
        engine = TraceEngine()
        engine.initialize()
        t1 = engine.start_trace()
        engine.start_trace()
        engine.finish_trace(t1.trace_id)
        active = engine.get_all_traces(active_only=True)
        assert len(active) == 1


class TestTraceEngineGetTracesByCorrelation:
    def test_get_traces_by_correlation(self):
        engine = TraceEngine()
        engine.initialize()
        engine.start_trace(correlation_id="corr-1")
        engine.start_trace(correlation_id="corr-1")
        traces = engine.get_traces_by_correlation("corr-1")
        assert len(traces) == 2


class TestTraceEngineCleanupExpiredTraces:
    def test_cleanup_expired_traces(self):
        engine = TraceEngine({"trace_ttl_seconds": 0})
        engine.initialize()
        trace = engine.start_trace()
        engine.finish_trace(trace.trace_id)
        cleaned = engine.cleanup_expired_traces()
        assert cleaned >= 0


class TestTraceEngineToDict:
    def test_to_dict(self):
        engine = TraceEngine()
        engine.initialize()
        engine.start_trace()
        d = engine.to_dict()
        assert d["initialized"] is True
        assert d["active_trace_count"] == 1
        assert len(d["traces"]) == 1

    def test_to_dict_before_init(self):
        engine = TraceEngine()
        d = engine.to_dict()
        assert d["initialized"] is False
        assert d["active_trace_count"] == 0


class TestTraceEngineShutdown:
    def test_shutdown_clears_traces(self):
        engine = TraceEngine()
        engine.initialize()
        engine.start_trace()
        engine.shutdown()
        assert engine._initialized is False
        assert len(engine._traces) == 0

    def test_shutdown_idempotent(self):
        engine = TraceEngine()
        engine.shutdown()
        assert engine._initialized is False


class TestTraceEngineExporters:
    def test_add_exporter(self):
        engine = TraceEngine()
        exporter = JsonTraceExporter()
        engine.add_exporter(exporter)
        assert exporter in engine._exporters

    def test_export_traces(self):
        engine = TraceEngine()
        engine.initialize()
        engine.start_trace()
        exporter = JsonTraceExporter()
        engine.add_exporter(exporter)
        engine.export_traces()


class TestTraceEngineNestedSpans:
    def test_nested_spans_parent_child(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        parent = engine.start_span(trace.trace_id, "parent")
        child = engine.start_span(trace.trace_id, "child", parent_span_id=parent.span_id)
        grandchild = engine.start_span(trace.trace_id, "grandchild", parent_span_id=child.span_id)
        root_spans = trace.get_root_spans()
        assert len(root_spans) == 1
        assert root_spans[0].span_id == parent.span_id
        children_of_child = trace.get_child_spans(child.span_id)
        assert len(children_of_child) == 1
        assert children_of_child[0].span_id == grandchild.span_id


class TestTraceEngineTraceWithLabels:
    def test_trace_with_labels(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace(labels={"env": "prod", "region": "us-east"})
        assert trace.labels == {"env": "prod", "region": "us-east"}

    def test_trace_labels_default_to_empty_dict(self):
        engine = TraceEngine()
        engine.initialize()
        trace = engine.start_trace()
        assert trace.labels == {}
