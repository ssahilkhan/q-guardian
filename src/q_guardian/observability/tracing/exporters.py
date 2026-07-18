from __future__ import annotations

import json
from abc import ABC, abstractmethod

import structlog

from q_guardian.observability.data import Trace

logger = structlog.get_logger()


class TraceExporter(ABC):
    def __init__(self) -> None:
        self._logger = logger.bind(component=self.name)

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def export(self, traces: list[Trace]) -> None: ...


class JsonTraceExporter(TraceExporter):
    @property
    def name(self) -> str:
        return "json"

    def export(self, traces: list[Trace]) -> None:
        serialized = json.dumps(
            [t.model_dump(mode="json") for t in traces],
            indent=2,
            default=str,
        )
        self._logger.info(
            "traces_exported_json",
            trace_count=len(traces),
            payload_length=len(serialized),
        )

    def serialize(self, traces: list[Trace]) -> str:
        return json.dumps(
            [t.model_dump(mode="json") for t in traces],
            indent=2,
            default=str,
        )


class ConsoleTraceExporter(TraceExporter):
    @property
    def name(self) -> str:
        return "console"

    def export(self, traces: list[Trace]) -> None:
        for trace in traces:
            span_count = trace.span_count
            duration = trace.duration_ms
            duration_str = f"{duration:.2f}ms" if duration is not None else "N/A"
            self._logger.info(
                "trace_summary",
                trace_id=trace.trace_id,
                status=trace.status.value,
                span_count=span_count,
                duration_ms=duration_str,
                correlation_id=trace.correlation_id,
            )
