from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from q_guardian.observability.data import Span, SpanStatus
from q_guardian.observability.enums import SpanKind

logger = structlog.get_logger()


class SpanManager:
    def __init__(self) -> None:
        self._logger = logger.bind(component="span_manager")

    def create_span(
        self,
        trace_id: str,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        span = Span(
            trace_id=trace_id,
            name=name,
            kind=kind,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
            start_time=datetime.now(UTC),
        )
        self._logger.debug("span_created", span_id=span.span_id, name=name, kind=kind.value)
        return span

    def finish_span(self, span: Span, status: SpanStatus | None = None) -> None:
        if span.end_time is not None:
            self._logger.warning("span_already_finished", span_id=span.span_id)
            return
        span.finish(status=status)
        self._logger.debug(
            "span_finished",
            span_id=span.span_id,
            duration_ms=span.duration_ms,
            status_code=span.status.code,
        )

    def add_event(
        self, span: Span, name: str, attributes: dict[str, Any] | None = None
    ) -> None:
        span.add_event(name=name, attributes=attributes)
        self._logger.debug(
            "span_event_added", span_id=span.span_id, event_name=name
        )

    def set_attribute(self, span: Span, key: str, value: Any) -> None:
        span.set_attribute(key=key, value=value)
        self._logger.debug(
            "span_attribute_set", span_id=span.span_id, key=key
        )

    def get_duration_ms(self, span: Span) -> float | None:
        return span.duration_ms
