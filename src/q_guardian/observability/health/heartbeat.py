from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger("observability.heartbeat")


class HeartbeatManager:
    def __init__(self, timeout_seconds: int = 90) -> None:
        self._timeout_seconds: int = timeout_seconds
        self._heartbeats: dict[str, float] = {}
        self._lock: threading.Lock = threading.Lock()

    @property
    def timeout_seconds(self) -> int:
        return self._timeout_seconds

    def register(self, component: str) -> None:
        with self._lock:
            now = time.time()
            self._heartbeats[component] = now
            logger.info(
                "heartbeat_registered",
                component=component,
                timeout_seconds=self._timeout_seconds,
            )

    def pulse(self, component: str) -> None:
        with self._lock:
            self._heartbeats[component] = time.time()
            logger.debug("heartbeat_pulsed", component=component)

    def is_alive(self, component: str) -> bool:
        with self._lock:
            if component not in self._heartbeats:
                return False
            elapsed = time.time() - self._heartbeats[component]
            return elapsed <= self._timeout_seconds

    def get_last_heartbeat(self, component: str) -> datetime | None:
        with self._lock:
            ts = self._heartbeats.get(component)
            if ts is None:
                return None
            return datetime.fromtimestamp(ts, tz=UTC)

    def get_elapsed_seconds(self, component: str) -> float | None:
        with self._lock:
            ts = self._heartbeats.get(component)
            if ts is None:
                return None
            return time.time() - ts

    def is_timed_out(self, component: str) -> bool:
        return not self.is_alive(component)

    def unregister(self, component: str) -> None:
        with self._lock:
            self._heartbeats.pop(component, None)
            logger.info("heartbeat_unregistered", component=component)

    def list_components(self) -> list[str]:
        with self._lock:
            return list(self._heartbeats.keys())
