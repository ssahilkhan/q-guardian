"""Integration tests for authentication endpoints and dependencies.

Covers the Person 1 Task 1 API layer:
- POST /api/v1/auth/token (credential exchange)
- POST /api/v1/auth/token/refresh (refresh flow)
- POST/GET/DELETE /api/v1/auth/api-keys (admin-gated lifecycle)
- require_auth dependency (Bearer JWT and X-API-Key resolution)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from q_guardian.security.auth import (
    hash_password,
    reset_auth_singletons,
)

if TYPE_CHECKING:
    from httpx import AsyncClient

AUTH_URL = "/api/v1/auth"
ADMIN = {"username": "admin", "password": "admin-secret-pass"}


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate auth environment variables and singletons per test."""
    monkeypatch.delenv("AUTH_USERS", raising=False)
    monkeypatch.delenv("API_KEYS", raising=False)
    users = {
        "admin": {
            "password_hash": hash_password(ADMIN["password"]),
            "roles": ["admin"],
        },
        "analyst": {
            "password_hash": hash_password("analyst-secret-pass"),
            "roles": ["analyst"],
        },
    }
    monkeypatch.setenv("AUTH_USERS", json.dumps(users))
    reset_auth_singletons()
    yield
    reset_auth_singletons()


async def _login(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    """Authenticate and return the Authorization header mapping."""
    response = await client.post(
        f"{AUTH_URL}/token", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestTokenEndpoint:
    """Tests for credential exchange."""

    async def test_valid_credentials_issue_token_pair(self, client: AsyncClient) -> None:
        """Verify valid credentials return access and refresh tokens."""
        response = await client.post(f"{AUTH_URL}/token", json=ADMIN)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert data["access_token"] and data["refresh_token"]
        assert data["access_token"] != data["refresh_token"]

    async def test_invalid_password_rejected(self, client: AsyncClient) -> None:
        """Verify wrong password returns 401."""
        response = await client.post(
            f"{AUTH_URL}/token",
            json={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == 401

    async def test_unknown_user_rejected(self, client: AsyncClient) -> None:
        """Verify unknown user returns 401."""
        response = await client.post(
            f"{AUTH_URL}/token",
            json={"username": "ghost", "password": "nope"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestRefreshEndpoint:
    """Tests for the refresh-token flow."""

    async def test_refresh_issues_new_access_token(self, client: AsyncClient) -> None:
        """Verify refresh token yields a new, different access token."""
        first = (await client.post(f"{AUTH_URL}/token", json=ADMIN)).json()["data"]
        response = await client.post(
            f"{AUTH_URL}/token/refresh",
            json={"refresh_token": first["refresh_token"]},
        )
        assert response.status_code == 200
        new_access = response.json()["data"]["access_token"]
        assert new_access
        assert new_access != first["access_token"]

    async def test_refresh_with_access_token_fails(self, client: AsyncClient) -> None:
        """Verify access tokens cannot be replayed as refresh tokens."""
        first = (await client.post(f"{AUTH_URL}/token", json=ADMIN)).json()["data"]
        response = await client.post(
            f"{AUTH_URL}/token/refresh",
            json={"refresh_token": first["access_token"]},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestRequireAuthDependency:
    """Tests for the require_auth dependency."""

    async def test_missing_credentials_rejected(self, client: AsyncClient) -> None:
        """Verify protected routes reject anonymous callers."""
        response = await client.get(f"{AUTH_URL}/api-keys")
        assert response.status_code == 401

    async def test_garbage_bearer_rejected(self, client: AsyncClient) -> None:
        """Verify malformed bearer tokens are rejected."""
        headers = {"Authorization": "Bearer not-a-jwt"}
        response = await client.get(f"{AUTH_URL}/api-keys", headers=headers)
        assert response.status_code == 401

    async def test_refresh_token_not_accepted_as_bearer(
        self, client: AsyncClient
    ) -> None:
        """Verify refresh tokens cannot authenticate protected routes."""
        first = (await client.post(f"{AUTH_URL}/token", json=ADMIN)).json()["data"]
        headers = {"Authorization": f"Bearer {first['refresh_token']}"}
        response = await client.get(f"{AUTH_URL}/api-keys", headers=headers)
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAPIKeyLifecycle:
    """Tests for admin-gated API key management."""

    async def test_admin_full_lifecycle(self, client: AsyncClient) -> None:
        """Verify create/list/revoke as admin with secret hygiene."""
        admin_headers = await _login(client, **ADMIN)

        created = await client.post(
            f"{AUTH_URL}/api-keys",
            json={
                "name": "ci-key",
                "owner": "team-a",
                "roles": ["service"],
                "ttl_days": 30,
            },
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()["data"]
        raw_key = body["api_key"]
        assert raw_key.startswith("qg_")
        key_id = body["key_id"]

        listed = await client.get(f"{AUTH_URL}/api-keys", headers=admin_headers)
        assert listed.status_code == 200
        entries = listed.json()["data"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["key_id"] == key_id
        assert entry["revoked"] is False
        serialized = json.dumps(entries)
        assert raw_key not in serialized
        assert "key_hash" not in serialized

        revoked = await client.delete(
            f"{AUTH_URL}/api-keys/{key_id}", headers=admin_headers
        )
        assert revoked.status_code == 200
        assert revoked.json()["data"]["revoked"] is True

        # The revoked key must no longer authenticate.
        rejected = await client.get(
            f"{AUTH_URL}/api-keys", headers={"X-API-Key": raw_key}
        )
        assert rejected.status_code == 401

    async def test_revocation_of_unknown_key_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Verify deleting a missing key id returns 404."""
        admin_headers = await _login(client, **ADMIN)
        response = await client.delete(
            f"{AUTH_URL}/api-keys/missing-id", headers=admin_headers
        )
        assert response.status_code == 404

    async def test_analyst_cannot_manage_keys(self, client: AsyncClient) -> None:
        """Verify non-admin roles receive 403 on key management."""
        analyst_headers = await _login(client, "analyst", "analyst-secret-pass")

        create_response = await client.post(
            f"{AUTH_URL}/api-keys",
            json={"name": "k", "owner": "o"},
            headers=analyst_headers,
        )
        assert create_response.status_code == 403

        list_response = await client.get(
            f"{AUTH_URL}/api-keys", headers=analyst_headers
        )
        assert list_response.status_code == 403

    async def test_admin_api_key_grants_key_management(
        self, client: AsyncClient
    ) -> None:
        """Verify an admin-scoped API key authenticates via X-API-Key."""
        admin_headers = await _login(client, **ADMIN)
        created = await client.post(
            f"{AUTH_URL}/api-keys",
            json={"name": "svc-admin", "owner": "ops", "roles": ["admin"]},
            headers=admin_headers,
        )
        raw_key = created.json()["data"]["api_key"]

        # Use the raw API key (not JWT) to manage keys.
        key_headers = {"X-API-Key": raw_key}
        second = await client.post(
            f"{AUTH_URL}/api-keys",
            json={"name": "via-key", "owner": "ops"},
            headers=key_headers,
        )
        assert second.status_code == 201
        other_id = second.json()["data"]["key_id"]

        deleted = await client.delete(
            f"{AUTH_URL}/api-keys/{other_id}", headers=key_headers
        )
        assert deleted.status_code == 200
