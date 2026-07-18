from __future__ import annotations

import threading

import structlog

from q_guardian.utils.uuid_utils import generate_correlation_id

logger = structlog.get_logger()


class CorrelationManager:
    def __init__(self) -> None:
        self._thread_local = threading.local()
        self._correlation_traces: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        self._logger = logger.bind(component="correlation_manager")

    def generate_correlation_id(self) -> str:
        cid = generate_correlation_id()
        self._logger.debug("correlation_id_generated", correlation_id=cid)
        return cid

    def set_current(self, correlation_id: str) -> None:
        self._thread_local.current_correlation_id = correlation_id
        self._logger.debug("correlation_id_set", correlation_id=correlation_id)

    def get_current(self) -> str | None:
        return getattr(self._thread_local, "current_correlation_id", None)

    def clear_current(self) -> None:
        self._thread_local.current_correlation_id = None
        self._logger.debug("correlation_id_cleared")

    def link_trace(self, correlation_id: str, trace_id: str) -> None:
        with self._lock:
            if correlation_id not in self._correlation_traces:
                self._correlation_traces[correlation_id] = []
            if trace_id not in self._correlation_traces[correlation_id]:
                self._correlation_traces[correlation_id].append(trace_id)
        self._logger.debug(
            "trace_linked", correlation_id=correlation_id, trace_id=trace_id
        )

    def get_traces_for_correlation(self, correlation_id: str) -> list[str]:
        with self._lock:
            return list(self._correlation_traces.get(correlation_id, []))
