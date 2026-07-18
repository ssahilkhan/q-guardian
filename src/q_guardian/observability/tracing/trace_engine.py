from __future__ import annotations

import threading
from typing import Any

import structlog

from q_guardian.observability.data import Span, SpanStatus, Trace
from q_guardian.observability.enums import SpanKind, TraceStatus
from q_guardian.observability.exceptions import TraceError
from q_guardian.observability.tracing.correlation import CorrelationManager
from q_guardian.observability.tracing.exporters import TraceExporter
from q_guardian.observability.tracing.span import SpanManager

logger = structlog.get_logger()

DEFAULT_MAX_TRACES = 10000
DEFAULT_TRACE_TTL_SECONDS = 3600


class TraceEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._max_traces: int = self._config.get("max_traces", DEFAULT_MAX_TRACES)
        self._trace_ttl_seconds: int = self._config.get(
            "trace_ttl_seconds", DEFAULT_TRACE_TTL_SECONDS
        )
        self._traces: dict[str, Trace] = {}
        self._lock = threading.Lock()
        self._span_manager = SpanManager()
        self._correlation_manager = CorrelationManager()
        self._exporters: list[TraceExporter] = []
        self._initialized = False
        self._logger = logger.bind(component="trace_engine")

    def initialize(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._logger.info(
            "trace_engine_initialized",
            max_traces=self._max_traces,
            trace_ttl_seconds=self._trace_ttl_seconds,
        )

    def start_trace(
        self,
        correlation_id: str = "",
        execution_id: str = "",
        labels: dict[str, str] | None = None,
    ) -> Trace:
        if not self._initialized:
            raise TraceError("TraceEngine not initialized, call initialize() first")

        with self._lock:
            if len(self._traces) >= self._max_traces:
                self._cleanup_expired_traces_internal()
                if len(self._traces) >= self._max_traces:
                    raise TraceError(
                        "Maximum trace limit reached",
                        details={"max_traces": self._max_traces},
                    )

        trace = Trace(
            correlation_id=correlation_id,
            execution_id=execution_id,
            labels=labels or {},
            status=TraceStatus.ACTIVE,
        )

        with self._lock:
            self._traces[trace.trace_id] = trace

        if correlation_id:
            self._correlation_manager.link_trace(correlation_id, trace.trace_id)

        self._logger.info(
            "trace_started",
            trace_id=trace.trace_id,
            correlation_id=correlation_id,
            execution_id=execution_id,
        )
        return trace

    def get_trace(self, trace_id: str) -> Trace | None:
        with self._lock:
            return self._traces.get(trace_id)

    def finish_trace(
        self, trace_id: str, status: TraceStatus | None = None
    ) -> Trace | None:
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                return None

        if trace.end_time is not None:
            self._logger.warning("trace_already_finished", trace_id=trace_id)
            return trace

        trace.finish(status=status)

        self._logger.info(
            "trace_finished",
            trace_id=trace_id,
            status=trace.status.value,
            duration_ms=trace.duration_ms,
            span_count=trace.span_count,
        )
        return trace

    def start_span(
        self,
        trace_id: str,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span | None:
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                self._logger.warning("span_start_failed_trace_not_found", trace_id=trace_id)
                return None
            if trace.end_time is not None:
                self._logger.warning("span_start_failed_trace_finished", trace_id=trace_id)
                return None

        span = self._span_manager.create_span(
            trace_id=trace_id,
            name=name,
            kind=kind,
            parent_span_id=parent_span_id,
            attributes=attributes,
        )

        with self._lock:
            trace.add_span(span)

        self._logger.debug(
            "span_started",
            trace_id=trace_id,
            span_id=span.span_id,
            name=name,
        )
        return span

    def finish_span(
        self, trace_id: str, span_id: str, status: SpanStatus | None = None
    ) -> bool:
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                return False

        span = trace.get_span(span_id)
        if span is None:
            self._logger.warning(
                "span_not_found", trace_id=trace_id, span_id=span_id
            )
            return False

        self._span_manager.finish_span(span, status=status)
        return True

    def add_span_event(
        self,
        trace_id: str,
        span_id: str,
        event_name: str,
        attributes: dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                return False

        span = trace.get_span(span_id)
        if span is None:
            return False

        self._span_manager.add_event(span, name=event_name, attributes=attributes)
        return True

    def set_span_attribute(
        self, trace_id: str, span_id: str, key: str, value: Any
    ) -> bool:
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                return False

        span = trace.get_span(span_id)
        if span is None:
            return False

        self._span_manager.set_attribute(span, key=key, value=value)
        return True

    def get_all_traces(self, active_only: bool = False) -> list[Trace]:
        with self._lock:
            traces = list(self._traces.values())
        if active_only:
            traces = [t for t in traces if t.end_time is None]
        return traces

    def get_traces_by_correlation(self, correlation_id: str) -> list[Trace]:
        trace_ids = self._correlation_manager.get_traces_for_correlation(
            correlation_id
        )
        with self._lock:
            return [
                self._traces[tid]
                for tid in trace_ids
                if tid in self._traces
            ]

    def cleanup_expired_traces(self) -> int:
        with self._lock:
            return self._cleanup_expired_traces_internal()

    def _cleanup_expired_traces_internal(self) -> int:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        expired_ids: list[str] = []
        for trace_id, trace in self._traces.items():
            if trace.end_time is not None:
                elapsed = (now - trace.end_time).total_seconds()
                if elapsed > self._trace_ttl_seconds:
                    expired_ids.append(trace_id)
        for tid in expired_ids:
            del self._traces[tid]
        if expired_ids:
            self._logger.info("traces_cleaned_up", count=len(expired_ids))
        return len(expired_ids)

    def add_exporter(self, exporter: TraceExporter) -> None:
        self._exporters.append(exporter)
        self._logger.debug("exporter_added", exporter_name=exporter.name)

    def export_traces(self) -> None:
        with self._lock:
            traces = list(self._traces.values())
        for exporter in self._exporters:
            try:
                exporter.export(traces)
            except Exception as exc:
                self._logger.error(
                    "trace_export_failed",
                    exporter=exporter.name,
                    error=str(exc),
                )

    @property
    def correlation_manager(self) -> CorrelationManager:
        return self._correlation_manager

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            traces = [t.model_dump(mode="json") for t in self._traces.values()]
        return {
            "initialized": self._initialized,
            "max_traces": self._max_traces,
            "trace_ttl_seconds": self._trace_ttl_seconds,
            "active_trace_count": len(self._traces),
            "exporters": [e.name for e in self._exporters],
            "traces": traces,
        }

    def shutdown(self) -> None:
        if not self._initialized:
            return
        self._logger.info(
            "trace_engine_shutting_down",
            active_traces=len(self._traces),
        )
        with self._lock:
            self._traces.clear()
            self._exporters.clear()
        self._initialized = False
        self._logger.info("trace_engine_shutdown_complete")
