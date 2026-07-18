import time

import pytest

from q_guardian.observability.health.health_registry import HealthRegistry
from q_guardian.observability.health.heartbeat import HeartbeatManager
from q_guardian.observability.health.diagnostics import DiagnosticEngine
from q_guardian.observability.data import HealthStatusModel
from q_guardian.observability.enums import HealthStatus


class TestHealthRegistry:
    def test_register_and_get(self) -> None:
        reg = HealthRegistry()
        model = HealthStatusModel(component="db", status=HealthStatus.HEALTHY)
        reg.register("db", model)
        result = reg.get("db")
        assert result is not None
        assert result.component == "db"

    def test_unregister(self) -> None:
        reg = HealthRegistry()
        model = HealthStatusModel(component="db", status=HealthStatus.HEALTHY)
        reg.register("db", model)
        assert reg.unregister("db") is True
        assert reg.get("db") is None

    def test_unregister_nonexistent(self) -> None:
        reg = HealthRegistry()
        assert reg.unregister("nope") is False

    def test_list_all(self) -> None:
        reg = HealthRegistry()
        reg.register("a", HealthStatusModel(component="a"))
        reg.register("b", HealthStatusModel(component="b"))
        all_components = reg.list_all()
        assert len(all_components) == 2
        assert "a" in all_components
        assert "b" in all_components

    def test_count(self) -> None:
        reg = HealthRegistry()
        reg.register("a", HealthStatusModel(component="a"))
        reg.register("b", HealthStatusModel(component="b"))
        assert reg.count() == 2

    def test_get_healthy_count(self) -> None:
        reg = HealthRegistry()
        reg.register("a", HealthStatusModel(component="a", status=HealthStatus.HEALTHY))
        reg.register("b", HealthStatusModel(component="b", status=HealthStatus.UNHEALTHY))
        assert reg.get_healthy_count() == 1

    def test_get_unhealthy_count(self) -> None:
        reg = HealthRegistry()
        reg.register("a", HealthStatusModel(component="a", status=HealthStatus.HEALTHY))
        reg.register("b", HealthStatusModel(component="b", status=HealthStatus.UNHEALTHY))
        reg.register("c", HealthStatusModel(component="c", status=HealthStatus.UNHEALTHY))
        assert reg.get_unhealthy_count() == 2


class TestHeartbeatManager:
    def test_register(self) -> None:
        hb = HeartbeatManager(timeout_seconds=30)
        hb.register("svc")
        assert hb.is_alive("svc") is True

    def test_pulse(self) -> None:
        hb = HeartbeatManager(timeout_seconds=30)
        hb.register("svc")
        hb.pulse("svc")
        assert hb.is_alive("svc") is True

    def test_is_alive(self) -> None:
        hb = HeartbeatManager(timeout_seconds=60)
        hb.register("svc")
        assert hb.is_alive("svc") is True

    def test_is_timed_out(self) -> None:
        hb = HeartbeatManager(timeout_seconds=1)
        hb.register("svc")
        assert hb.is_timed_out("svc") is False

    def test_get_last_heartbeat(self) -> None:
        hb = HeartbeatManager(timeout_seconds=30)
        hb.register("svc")
        last = hb.get_last_heartbeat("svc")
        assert last is not None

    def test_get_elapsed_seconds(self) -> None:
        hb = HeartbeatManager(timeout_seconds=30)
        hb.register("svc")
        elapsed = hb.get_elapsed_seconds("svc")
        assert elapsed is not None
        assert elapsed >= 0.0

    def test_unregistered_component_not_alive(self) -> None:
        hb = HeartbeatManager(timeout_seconds=30)
        assert hb.is_alive("nonexistent") is False

    def test_get_last_heartbeat_nonexistent(self) -> None:
        hb = HeartbeatManager(timeout_seconds=30)
        assert hb.get_last_heartbeat("nonexistent") is None

    def test_get_elapsed_seconds_nonexistent(self) -> None:
        hb = HeartbeatManager(timeout_seconds=30)
        assert hb.get_elapsed_seconds("nonexistent") is None


class TestDiagnosticEngine:
    def test_get_system_info(self) -> None:
        diag = DiagnosticEngine()
        info = diag.get_system_info()
        assert "version" in info
        assert "platform" in info
        assert "python_version" in info
        assert "uptime_seconds" in info

    def test_run_connectivity_check(self) -> None:
        diag = DiagnosticEngine()
        results = diag.run_connectivity_check()
        assert isinstance(results, dict)
        assert "database" in results
        assert results["database"] is True

    def test_get_performance_summary(self) -> None:
        diag = DiagnosticEngine()
        summary = diag.get_performance_summary()
        assert "uptime_seconds" in summary
        assert "uptime_human" in summary
        assert "diagnostic_id" in summary
