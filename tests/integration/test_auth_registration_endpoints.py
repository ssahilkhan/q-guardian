"""Integration tests for the registration / logout HTTP endpoints.

Uses in-memory test doubles for the user store and blocklist so these
tests run without a real MongoDB, while exercising the full HTTP layer:
schema validation, rate limiting, wiring and error shaping.

The production Mongo-backed stores are covered by an end-to-end test that
requires a running database.
"""

from __future__ import annotations

import pytest

from q_guardian.database.repositories.user_repository import InMemoryUserRepository
from q_guardian.security.auth import (
    AuthenticationService,
    JWTService,
    reset_auth_singletons,
)
from q_guardian.security.token_blocklist import (
    InMemoryTokenBlocklistRepository,
    TokenBlocklistService,
)


@pytest.fixture(autouse=True)
def _inject_inmemory_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the auth singleton with in-memory-backed services."""
    import os

    import q_guardian.security.auth as auth_module

    os.environ.pop("AUTH_USERS", None)
    reset_auth_singletons()

    repo = InMemoryUserRepository()
    blocklist = TokenBlocklistService(repository=InMemoryTokenBlocklistRepository())
    svc = AuthenticationService(
        jwt_service=JWTService(),
        user_repository=repo,
        token_blocklist=blocklist,
    )
    monkeypatch.setattr(auth_module, "_authentication_service_instance", svc)
    # The principal-check dependency reads the singleton blocklist, so it
    # must be the same instance the auth service revokes into.
    monkeypatch.setattr(auth_module, "_token_blocklist_instance", blocklist)
    yield
    reset_auth_singletons()


@pytest.mark.asyncio
class TestRegisterEndpoint:
    """Tests for POST /api/v1/auth/register."""

    async def test_register_returns_201(self, client) -> None:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": "newoperator", "password": "secret-pass"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["username"] == "newoperator"
        assert body["data"]["roles"] == ["analyst"]

        # The new account can now log in.
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "newoperator", "password": "secret-pass"},
        )
        assert login.status_code == 200
        assert login.json()["data"]["tokens"]["access"]

    async def test_register_duplicate_returns_422(self, client) -> None:
        await client.post(
            "/api/v1/auth/register",
            json={"username": "taken", "password": "secret-pass"},
        )
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": "taken", "password": "other-pass"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    async def test_register_short_password_rejected(self, client) -> None:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": "weak", "password": "short"},
        )
        assert resp.status_code == 422

    async def test_register_bad_username_rejected(self, client) -> None:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": "bad name!", "password": "secret-pass"},
        )
        assert resp.status_code == 422

    async def test_register_malformed_body_rejected(self, client) -> None:
        resp = await client.post("/api/v1/auth/register", json={})
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestLogoutEndpoint:
    """Tests for POST /api/v1/auth/logout."""

    async def _register_and_login(self, client) -> tuple[str, str]:
        await client.post(
            "/api/v1/auth/register",
            json={"username": "logger", "password": "secret-pass"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "logger", "password": "secret-pass"},
        )
        tokens = login.json()["data"]["tokens"]
        return tokens["access"], tokens["refresh"]

    async def test_logout_requires_auth(self, client) -> None:
        resp = await client.post("/api/v1/auth/logout", json={})
        assert resp.status_code == 401

    async def test_logout_revokes_tokens(self, client) -> None:
        access, refresh = await self._register_and_login(client)

        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["revoked"] == 2
        assert body["data"]["username"] == "logger"

        # The access token is now rejected on a protected endpoint.
        denied = await client.get(
            "/api/v1/system/version",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert denied.status_code == 401

    async def test_logout_blocks_refresh(self, client) -> None:
        access, refresh = await self._register_and_login(client)

        await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )

        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert refresh_resp.status_code == 401


@pytest.mark.asyncio
class TestLoginRateLimitShape:
    """Verify the login/registration error contract is preserved."""

    async def test_login_unknown_user_401(self, client) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "ghost", "password": "anything"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"

    async def test_issued_token_works_on_protected(self, client) -> None:
        await client.post(
            "/api/v1/auth/register",
            json={"username": "works", "password": "secret-pass"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "works", "password": "secret-pass"},
        )
        access = login.json()["data"]["tokens"]["access"]

        resp = await client.get(
            "/api/v1/system/version",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert resp.status_code == 200
