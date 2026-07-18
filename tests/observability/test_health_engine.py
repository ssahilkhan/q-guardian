import pytest

from q_guardian.observability.health.health_engine import HealthEngine
from q_guardian.observability.data import HealthCheckResult, HealthStatusModel
from q_guardian.observability.enums import HealthStatus, HealthLevel


class TestHealthEngineInitialization:
    def test_init_default_config(self) -> None:
        engine = HealthEngine()
        assert engine.engine_id is not None
        assert engine.is_initialized is False

    def test_init_with_config(self) -> None:
        engine = HealthEngine(config={"heartbeat_timeout_seconds": 30})
        assert engine.engine_id is not None
        assert engine._config["heartbeat_timeout_seconds"] == 30

    def test_initialize_sets_initialized(self) -> None:
        engine = HealthEngine()
        engine.initialize()
        assert engine.is_initialized is True

    def test_double_initialize_does_not_crash(self) -> None:
        engine = HealthEngine()
        engine.initialize()
        engine.initialize()
        assert engine.is_initialized is True


class TestHealthEngineComponents:
    def test_register_component(self) -> None:
        engine = HealthEngine()
        engine.register_component("db")
        status = engine.get_component_status("db")
        assert status is not None
        assert status.component == "db"

    def test_register_duplicate_component_does_not_crash(self) -> None:
        engine = HealthEngine()
        engine.register_component("db")
        engine.register_component("db")
        assert engine.get_component_status("db") is not None

    def test_unregister_component(self) -> None:
        engine = HealthEngine()
        engine.register_component("db")
        result = engine.unregister_component("db")
        assert result is True
        assert engine.get_component_status("db") is None

    def test_unregister_non_existent_returns_false(self) -> None:
        engine = HealthEngine()
        result = engine.unregister_component("nonexistent")
        assert result is False


class TestHealthEngineChecks:
    def test_check_component_without_custom_check(self) -> None:
        engine = HealthEngine()
        engine.register_component("svc")
        result = engine.check_component("svc")
        assert isinstance(result, HealthCheckResult)
        assert result.component == "svc"

    def test_check_component_returns_health_check_result(self) -> None:
        engine = HealthEngine()
        engine.register_component("svc")
        result = engine.check_component("svc")
        assert isinstance(result, HealthCheckResult)
        assert result.status == HealthStatus.UNKNOWN

    def test_check_component_nonexistent_returns_none(self) -> None:
        engine = HealthEngine()
        result = engine.check_component("nonexistent")
        assert result is None

    def test_check_component_with_custom_check(self) -> None:
        async def custom_check() -> HealthCheckResult:
            return HealthCheckResult(
                component="custom",
                status=HealthStatus.HEALTHY,
                message="OK",
            )

        engine = HealthEngine()
        engine.register_component("custom", health_check=custom_check)
        result = engine.check_component("custom")
        assert isinstance(result, HealthCheckResult)
        assert result.component == "custom"

    def test_check_all(self) -> None:
        engine = HealthEngine()
        engine.register_component("a")
        engine.register_component("b")
        report = engine.check_all()
        assert report is not None
        assert len(report.components) == 2

    def test_get_component_status(self) -> None:
        engine = HealthEngine()
        engine.register_component("svc")
        status = engine.get_component_status("svc")
        assert status is not None
        assert status.component == "svc"

    def test_get_component_status_nonexistent(self) -> None:
        engine = HealthEngine()
        assert engine.get_component_status("nope") is None

    def test_get_health_report(self) -> None:
        engine = HealthEngine()
        engine.register_component("svc")
        report = engine.get_health_report()
        assert report is not None
        assert len(report.components) == 1


class TestHealthEngineOverall:
    def test_get_overall_status_no_components_returns_unknown(self) -> None:
        engine = HealthEngine()
        assert engine.get_overall_status() == HealthStatus.UNKNOWN

    def test_get_overall_status_all_healthy(self) -> None:
        engine = HealthEngine()
        engine.register_component("a")
        engine.register_component("b")
        engine._components["a"].status = HealthStatus.HEALTHY
        engine._components["a"].health_score = 1.0
        engine._components["b"].status = HealthStatus.HEALTHY
        engine._components["b"].health_score = 1.0
        assert engine.get_overall_status() == HealthStatus.HEALTHY

    def test_get_overall_status_one_unhealthy(self) -> None:
        engine = HealthEngine()
        engine.register_component("a")
        engine.register_component("b")
        engine._components["a"].status = HealthStatus.UNHEALTHY
        engine._components["a"].health_score = 0.0
        engine._components["b"].status = HealthStatus.HEALTHY
        engine._components["b"].health_score = 1.0
        assert engine.get_overall_status() == HealthStatus.UNHEALTHY

    def test_get_overall_status_one_degraded(self) -> None:
        engine = HealthEngine()
        engine.register_component("a")
        engine._components["a"].status = HealthStatus.DEGRADED
        engine._components["a"].health_score = 0.5
        assert engine.get_overall_status() == HealthStatus.DEGRADED

    def test_get_overall_score_no_components_returns_zero(self) -> None:
        engine = HealthEngine()
        assert engine.get_overall_score() == 0.0

    def test_get_overall_score_single_healthy(self) -> None:
        engine = HealthEngine()
        engine.register_component("a")
        engine._components["a"].status = HealthStatus.HEALTHY
        engine._components["a"].health_score = 1.0
        assert engine.get_overall_score() == 1.0


class TestHealthEngineMisc:
    def test_update_heartbeat(self) -> None:
        engine = HealthEngine()
        engine.register_component("svc")
        engine.update_heartbeat("svc")
        status = engine.get_component_status("svc")
        assert status is not None
        assert status.last_heartbeat is not None

    def test_get_diagnostics(self) -> None:
        engine = HealthEngine()
        engine.register_component("svc")
        engine.initialize()
        diag = engine.get_diagnostics()
        assert "engine_id" in diag
        assert "initialized" in diag
        assert "component_count" in diag
        assert "overall_status" in diag

    def test_to_dict(self) -> None:
        engine = HealthEngine()
        engine.register_component("svc")
        d = engine.to_dict()
        assert "engine_id" in d
        assert "initialized" in d
        assert "components" in d
        assert "svc" in d["components"]
