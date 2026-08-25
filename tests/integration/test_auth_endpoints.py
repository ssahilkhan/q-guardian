"""Integration tests for console authentication endpoints."""

from __future__ import annotations

import json

import pytest

from q_guardian.security.auth import reset_auth_singletons


@pytest.fixture(autouse=True)
def _provision_user() -> None:
    """Provision a test user via AUTH_USERS and reset auth singletons."""
    import os

    from q_guardian.security.auth import hash_password

    os.environ["AUTH_USERS"] = json.dumps(
        {"tester": {"password_hash": hash_password("correct-password"), "roles": ["analyst"]}}
    )
    reset_auth_singletons()
    yield
    os.environ.pop("AUTH_USERS", None)
    reset_auth_singletons()


@pytest.mark.asyncio
class TestAuthEndpoints:
    """Tests for the /auth/login and /auth/refresh bootstrap endpoints."""

    async def test_login_success_returns_token_pair(self, authorized_client) -> None:
        """Valid credentials return 200 with access + refresh tokens."""
        # authorized_client is already authenticated; test the unauthenticated
        # login endpoint directly using a fresh client
        from httpx import ASGITransport, AsyncClient

        from q_guardian.api.app import create_app

        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/auth/login",
                json={"username": "tester", "password": "correct-password"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        tokens = data["data"]["tokens"]
        assert tokens.get("access")
        assert tokens.get("refresh")
        assert data["data"]["username"] == "tester"
        assert "analyst" in data["data"]["roles"]

    async def test_login_wrong_password_returns_401(self, client) -> None:
        """Invalid password returns 401 with consistent error shape."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "tester", "password": "wrong"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["code"] == "AUTHENTICATION_ERROR"
        assert body["error"]["details"]["reason"] == "invalid_credentials"

    async def test_login_unknown_user_returns_401(self, client) -> None:
        """Unknown username returns identical 401 (no user enumeration)."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "ghost", "password": "anything"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["code"] == "AUTHENTICATION_ERROR"
        assert body["error"]["details"]["reason"] == "invalid_credentials"

    async def test_login_malformed_body_returns_422(self, client) -> None:
        """Missing fields are rejected by schema validation."""
        resp = await client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422

    async def test_refresh_valid_token_returns_new_access(self, client) -> None:
        """A valid refresh token yields a new access token (refresh reused)."""
        from httpx import ASGITransport, AsyncClient

        from q_guardian.api.app import create_app

        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": "tester", "password": "correct-password"},
            )
        assert login.status_code == 200
        tokens = login.json()["data"]["tokens"]

        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": tokens["refresh"]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        new_tokens = data["data"]["tokens"]
        assert new_tokens["access"] != tokens["access"]
        # Current backend behavior: refresh token is reused (only access rotates)
        assert new_tokens["refresh"] == tokens["refresh"]

    async def test_refresh_invalid_token_returns_401(self, client) -> None:
        """Garbage refresh token returns 401."""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not-a-real-token"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["code"] == "AUTHENTICATION_ERROR"
        assert body["error"]["details"]["reason"] == "invalid_refresh_token"

    async def test_issued_token_works_on_protected_endpoint(self, client) -> None:
        """The access token from login authenticates a protected console endpoint."""
        from httpx import ASGITransport, AsyncClient

        from q_guardian.api.app import create_app

        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": "tester", "password": "correct-password"},
            )
        assert login.status_code == 200
        access = login.json()["data"]["tokens"]["access"]

        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/api/v1/system/version",
                headers={"Authorization": f"Bearer {access}"},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


@pytest.mark.asyncio
class TestConsoleEndpointsWithLoginToken:
    """Ensure the standard console endpoints work with a login-issued token."""

    async def test_summary_with_login_token(self, client) -> None:
        from httpx import ASGITransport, AsyncClient

        from q_guardian.api.app import create_app

        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": "tester", "password": "correct-password"},
            )
            access = login.json()["data"]["tokens"]["access"]

            resp = await ac.get(
                "/api/v1/console/summary",
                headers={"Authorization": f"Bearer {access}"},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_observability_with_login_token(self, client) -> None:
        from httpx import ASGITransport, AsyncClient

        from q_guardian.api.app import create_app

        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": "tester", "password": "correct-password"},
            )
            access = login.json()["data"]["tokens"]["access"]

            resp = await ac.get(
                "/api/v1/console/observability",
                headers={"Authorization": f"Bearer {access}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert "total_requests" in data
        assert "routes" in data
        assert "scan_decisions" in data
        assert isinstance(data["routes"], list)
        # The login + this request should have recorded at least 2 requests
        assert data["total_requests"] >= 2


@pytest.mark.asyncio
class TestModelsEndpointExtraFields:
    """Verify the models endpoint now returns the additional metadata fields."""

    async def test_models_includes_training_samples_and_features(self, authorized_client) -> None:
        resp = await authorized_client.get("/api/v1/console/models")
        assert resp.status_code == 200
        data = resp.json()["data"]["ml"]["models"]
        if data:
            m = data[0]
            for field in (
                "training_samples",
                "feature_count",
                "created_at",
                "updated_at",
                "artifact_registered",
                "tags",
            ):
                assert field in m, f"missing field {field}"
