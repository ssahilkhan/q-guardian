from datetime import UTC, datetime

import pytest

from q_guardian.observability.data import Span, SpanStatus
from q_guardian.observability.enums import SpanKind
from q_guardian.observability.tracing.context import TraceContext
from q_guardian.observability.tracing.correlation import CorrelationManager
from q_guardian.observability.tracing.span import SpanManager


class TestSpanManagerCreateSpan:
    def test_create_span(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        assert isinstance(span, Span)
        assert span.trace_id == "trace-1"
        assert span.name == "test-span"
        assert span.kind == SpanKind.INTERNAL
        assert span.parent_span_id is None

    def test_create_span_with_all_params(self):
        mgr = SpanManager()
        span = mgr.create_span(
            trace_id="trace-1",
            name="db-query",
            kind=SpanKind.CLIENT,
            parent_span_id="parent-1",
            attributes={"db.system": "postgres"},
        )
        assert span.kind == SpanKind.CLIENT
        assert span.parent_span_id == "parent-1"
        assert span.attributes == {"db.system": "postgres"}


class TestSpanManagerFinishSpan:
    def test_finish_span(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        mgr.finish_span(span)
        assert span.end_time is not None
        assert span.status.code == 0

    def test_finish_span_with_status(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        mgr.finish_span(span, status=SpanStatus.error("something went wrong"))
        assert span.status.code == 1
        assert span.status.message == "something went wrong"

    def test_finish_span_already_finished(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        mgr.finish_span(span)
        end_time = span.end_time
        mgr.finish_span(span)
        assert span.end_time == end_time


class TestSpanManagerAddEvent:
    def test_add_event(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        mgr.add_event(span, "cache-hit")
        assert len(span.events) == 1
        assert span.events[0]["name"] == "cache-hit"

    def test_add_event_with_attributes(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        mgr.add_event(span, "cache-miss", {"key": "user:123"})
        assert span.events[0]["attributes"] == {"key": "user:123"}


class TestSpanManagerSetAttribute:
    def test_set_attribute(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        mgr.set_attribute(span, "http.method", "GET")
        assert span.attributes["http.method"] == "GET"

    def test_set_attribute_overwrites(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        mgr.set_attribute(span, "key", "value1")
        mgr.set_attribute(span, "key", "value2")
        assert span.attributes["key"] == "value2"


class TestSpanManagerGetDurationMs:
    def test_get_duration_ms(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        mgr.finish_span(span)
        duration = mgr.get_duration_ms(span)
        assert duration is not None
        assert duration >= 0

    def test_get_duration_ms_none_for_unfinished(self):
        mgr = SpanManager()
        span = mgr.create_span(trace_id="trace-1", name="test-span")
        duration = mgr.get_duration_ms(span)
        assert duration is None


class TestCorrelationManagerGenerateCorrelationId:
    def test_generate_correlation_id_returns_string(self):
        mgr = CorrelationManager()
        cid = mgr.generate_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) > 0

    def test_generate_correlation_id_unique(self):
        mgr = CorrelationManager()
        cid1 = mgr.generate_correlation_id()
        cid2 = mgr.generate_correlation_id()
        assert cid1 != cid2


class TestCorrelationManagerCurrent:
    def test_set_and_get_current(self):
        mgr = CorrelationManager()
        mgr.set_current("corr-123")
        assert mgr.get_current() == "corr-123"

    def test_get_current_defaults_to_none(self):
        mgr = CorrelationManager()
        assert mgr.get_current() is None

    def test_clear_current(self):
        mgr = CorrelationManager()
        mgr.set_current("corr-123")
        mgr.clear_current()
        assert mgr.get_current() is None


class TestCorrelationManagerLinkTrace:
    def test_link_trace_and_get_traces(self):
        mgr = CorrelationManager()
        mgr.link_trace("corr-1", "trace-1")
        mgr.link_trace("corr-1", "trace-2")
        traces = mgr.get_traces_for_correlation("corr-1")
        assert len(traces) == 2
        assert "trace-1" in traces
        assert "trace-2" in traces

    def test_get_traces_for_correlation_empty(self):
        mgr = CorrelationManager()
        assert mgr.get_traces_for_correlation("nonexistent") == []

    def test_link_trace_does_not_duplicate(self):
        mgr = CorrelationManager()
        mgr.link_trace("corr-1", "trace-1")
        mgr.link_trace("corr-1", "trace-1")
        assert len(mgr.get_traces_for_correlation("corr-1")) == 1


class TestCorrelationManagerThreadSafety:
    def test_thread_local_isolation(self):
        import threading
        mgr = CorrelationManager()

        def set_and_get():
            mgr.set_current("thread-specific")
            assert mgr.get_current() == "thread-specific"

        mgr.set_current("main-thread")
        t = threading.Thread(target=set_and_get)
        t.start()
        t.join()
        assert mgr.get_current() == "main-thread"


class TestTraceContextCreation:
    def test_create_trace_context(self):
        ctx = TraceContext(trace_id="trace-1")
        assert ctx.trace_id == "trace-1"
        assert ctx.correlation_id == ""
        assert ctx.current_span_id is None

    def test_create_trace_context_with_all_fields(self):
        ctx = TraceContext(
            trace_id="trace-1",
            correlation_id="corr-1",
            current_span_id="span-1",
        )
        assert ctx.trace_id == "trace-1"
        assert ctx.correlation_id == "corr-1"
        assert ctx.current_span_id == "span-1"


class TestTraceContextWithSpan:
    def test_with_span_returns_new_instance(self):
        ctx = TraceContext(trace_id="trace-1")
        ctx2 = ctx.with_span("span-1")
        assert ctx is not ctx2
        assert ctx.current_span_id is None
        assert ctx2.current_span_id == "span-1"
        assert ctx2.trace_id == "trace-1"


class TestTraceContextToDict:
    def test_to_dict_with_trace_only(self):
        ctx = TraceContext(trace_id="trace-1")
        d = ctx.to_dict()
        assert d == {"trace_id": "trace-1"}

    def test_to_dict_with_all_fields(self):
        ctx = TraceContext(trace_id="trace-1", correlation_id="corr-1", current_span_id="span-1")
        d = ctx.to_dict()
        assert d == {"trace_id": "trace-1", "correlation_id": "corr-1", "span_id": "span-1"}


class TestTraceContextFromDict:
    def test_from_dict(self):
        ctx = TraceContext.from_dict({
            "trace_id": "trace-1",
            "correlation_id": "corr-1",
            "span_id": "span-1",
        })
        assert ctx.trace_id == "trace-1"
        assert ctx.correlation_id == "corr-1"
        assert ctx.current_span_id == "span-1"

    def test_from_dict_empty(self):
        ctx = TraceContext.from_dict({})
        assert ctx.trace_id == ""
        assert ctx.correlation_id == ""
        assert ctx.current_span_id is None


class TestTraceContextProperties:
    def test_trace_context_is_frozen(self):
        ctx = TraceContext(trace_id="trace-1")
        with pytest.raises(Exception):
            ctx.trace_id = "new-trace"
