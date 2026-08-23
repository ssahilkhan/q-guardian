"""Unit tests for the database health TTL cache (F-11 fix)."""

from __future__ import annotations

import pytest

import q_guardian.database.health as health_mod
from q_guardian.database.health import check_database_health, reset_database_health_cache


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    reset_database_health_cache()


class _FakeClient:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.ping_calls = 0

    async def ping(self) -> bool:
        self.ping_calls += 1
        return self.connected


class TestHealthCache:
    async def test_repeated_probes_within_ttl_ping_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeClient()
        monkeypatch.setattr(health_mod, "get_db_client", lambda: fake)
        first = await check_database_health()
        second = await check_database_health()
        assert (
            first
            == second
            == {
                "status": "healthy",
                "database": "mongodb",
                "message": "Connection successful",
            }
        )
        assert fake.ping_calls == 1

    async def test_force_bypasses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient()
        monkeypatch.setattr(health_mod, "get_db_client", lambda: fake)
        await check_database_health()
        await check_database_health(force=True)
        assert fake.ping_calls == 2

    async def test_reset_clears_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeClient()
        monkeypatch.setattr(health_mod, "get_db_client", lambda: fake)
        await check_database_health()
        reset_database_health_cache()
        await check_database_health()
        assert fake.ping_calls == 2

    async def test_unreachable_db_result_is_cached_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeClient(connected=False)
        monkeypatch.setattr(health_mod, "get_db_client", lambda: fake)
        first = await check_database_health()
        second = await check_database_health()
        assert first["status"] == "unhealthy"
        assert second["status"] == "unhealthy"
        assert fake.ping_calls == 1

    async def test_exception_is_reported_as_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Boom:
            async def ping(self) -> bool:
                raise RuntimeError("server selection timeout")

        monkeypatch.setattr(health_mod, "get_db_client", _Boom)
        result = await check_database_health(force=True)
        assert result["status"] == "unhealthy"
        assert "server selection timeout" in result["message"]
