from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

import structlog

from q_guardian.observability.data import HealthCheckResult, HealthReport, HealthStatusModel, TimeWindow
from q_guardian.observability.enums import HealthLevel, HealthStatus
from q_guardian.observability.exceptions import HealthError
from q_guardian.observability.health.diagnostics import DiagnosticEngine
from q_guardian.observability.health.health_registry import HealthRegistry
from q_guardian.observability.health.heartbeat import HeartbeatManager
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("observability.health_engine")


class HealthEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = config or {}
        self._initialized: bool = False
        self._engine_id: str = generate_uuid()
        self._start_time: float = time.time()
        self._lock: threading.Lock = threading.Lock()
        self._components: dict[str, HealthStatusModel] = {}
        self._checks: dict[str, Callable[[], Awaitable[HealthCheckResult]]] = {}
        self._check_results: dict[str, HealthCheckResult] = {}
        self._registry: HealthRegistry = HealthRegistry()
        self._heartbeat_manager: HeartbeatManager = HeartbeatManager(
            timeout_seconds=self._config.get("heartbeat_timeout_seconds", 90)
        )
        self._diagnostics: DiagnosticEngine = DiagnosticEngine()

    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                logger.warning("health_engine_already_initialized", engine_id=self._engine_id)
                return
            self._initialized = True
            self._start_time = time.time()
            logger.info("health_engine_initialized", engine_id=self._engine_id)

    def register_component(
        self,
        name: str,
        health_check: Callable[[], Awaitable[HealthCheckResult]] | None = None,
    ) -> None:
        with self._lock:
            if name in self._components:
                logger.warning("component_already_registered", component=name)
                return

            model = HealthStatusModel(
                component=name,
                status=HealthStatus.UNKNOWN,
                health_score=1.0,
                level=HealthLevel.GOOD,
                uptime_seconds=0.0,
            )
            self._components[name] = model
            self._registry.register(name, model)
            self._heartbeat_manager.register(name)

            if health_check is not None:
                self._checks[name] = health_check

            logger.info("component_registered", component=name, engine_id=self._engine_id)

    def unregister_component(self, name: str) -> bool:
        with self._lock:
            if name not in self._components:
                return False

            del self._components[name]
            self._checks.pop(name, None)
            self._check_results.pop(name, None)
            self._registry.unregister(name)
            self._heartbeat_manager.unregister(name)

            logger.info("component_unregistered", component=name, engine_id=self._engine_id)
            return True

    def check_component(self, name: str) -> HealthCheckResult | None:
        with self._lock:
            if name not in self._components:
                return None

            check_fn = self._checks.get(name)
            if check_fn is None:
                result = HealthCheckResult(
                    component=name,
                    status=self._components[name].status,
                    message="No health check registered",
                    latency_ms=0.0,
                )
                self._check_results[name] = result
                return result

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, check_fn())
                    result = future.result(timeout=30.0)
            else:
                result = loop.run_until_complete(check_fn())
        except Exception as e:
            result = HealthCheckResult(
                component=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                details={"error": str(e)},
            )

        with self._lock:
            self._check_results[name] = result
            model = self._components[name]
            model.status = result.status
            model.health_score = self._status_to_score(result.status)
            model.update_level()
            model.uptime_seconds = time.time() - self._start_time
            if result.status == HealthStatus.UNHEALTHY:
                model.failures.append(result.message)
            elif result.status == HealthStatus.DEGRADED:
                model.warnings.append(result.message)

        logger.debug(
            "component_checked",
            component=name,
            status=result.status.value,
            latency_ms=result.latency_ms,
        )
        return result

    def check_all(self) -> HealthReport:
        with self._lock:
            component_names = list(self._components.keys())

        for name in component_names:
            self.check_component(name)

        return self.get_health_report()

    def get_component_status(self, name: str) -> HealthStatusModel | None:
        with self._lock:
            return self._components.get(name)

    def get_health_report(self) -> HealthReport:
        with self._lock:
            components = list(self._components.values())

        report = HealthReport(
            overall_status=self.get_overall_status(),
            overall_score=self.get_overall_score(),
            components=components,
            framework_uptime_seconds=time.time() - self._start_time,
        )
        report.calculate_overall()
        return report

    def get_overall_status(self) -> HealthStatus:
        with self._lock:
            if not self._components:
                return HealthStatus.UNKNOWN

            statuses = {c.status for c in self._components.values()}

            if HealthStatus.UNHEALTHY in statuses:
                return HealthStatus.UNHEALTHY
            if HealthStatus.DEGRADED in statuses:
                return HealthStatus.DEGRADED
            if all(s == HealthStatus.HEALTHY for s in statuses):
                return HealthStatus.HEALTHY
            if all(s == HealthStatus.UNKNOWN for s in statuses):
                return HealthStatus.UNKNOWN
            return HealthStatus.DEGRADED

    def get_overall_score(self) -> float:
        with self._lock:
            if not self._components:
                return 0.0
            scores = [c.health_score for c in self._components.values()]
            return sum(scores) / len(scores)

    def update_heartbeat(self, component: str) -> None:
        self._heartbeat_manager.pulse(component)
        with self._lock:
            if component in self._components:
                self._components[component].last_heartbeat = datetime.now(UTC)

    def get_diagnostics(self, component: str | None = None) -> dict[str, Any]:
        diag = self._diagnostics.collect_diagnostics(component)
        diag["engine_id"] = self._engine_id
        diag["initialized"] = self._initialized
        diag["component_count"] = len(self._components)
        diag["overall_status"] = self.get_overall_status().value
        diag["overall_score"] = self.get_overall_score()

        with self._lock:
            heartbeat_status = {}
            for name in self._components:
                heartbeat_status[name] = {
                    "alive": self._heartbeat_manager.is_alive(name),
                    "last_heartbeat": (
                        self._heartbeat_manager.get_last_heartbeat(name).isoformat()
                        if self._heartbeat_manager.get_last_heartbeat(name) is not None
                        else None
                    ),
                    "timed_out": self._heartbeat_manager.is_timed_out(name),
                }

        diag["heartbeats"] = heartbeat_status
        diag["performance"] = self._diagnostics.get_performance_summary()
        return diag

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            components_dict = {
                name: model.model_dump(mode="json")
                for name, model in self._components.items()
            }
            checks_registered = list(self._checks.keys())

        return {
            "engine_id": self._engine_id,
            "initialized": self._initialized,
            "uptime_seconds": time.time() - self._start_time,
            "overall_status": self.get_overall_status().value,
            "overall_score": self.get_overall_score(),
            "component_count": len(self._components),
            "components": components_dict,
            "checks_registered": checks_registered,
            "heartbeat_timeout_seconds": self._heartbeat_manager.timeout_seconds,
        }

    @staticmethod
    def _status_to_score(status: HealthStatus) -> float:
        mapping = {
            HealthStatus.HEALTHY: 1.0,
            HealthStatus.DEGRADED: 0.5,
            HealthStatus.UNHEALTHY: 0.0,
            HealthStatus.MAINTENANCE: 0.75,
            HealthStatus.UNKNOWN: 0.5,
        }
        return mapping.get(status, 0.5)
