"""End-to-end authentication flow against a real MongoDB.

Exercises the full lifecycle with the production persistence path:

1. register a new account
2. simulate a restart by resetting the auth singletons (rebuilding the
   in-memory env store) while the account lives in MongoDB
3. log in with the registered credentials
4. access a protected endpoint
5. log out (revokes both tokens)
6. verify the revoked token is rejected and an invalid login is rejected

Requires a running MongoDB configured via :data:`MONGODB_URL` /
:data:`MONGODB_DATABASE`. Skipped when no server is reachable.
"""

from __future__ import annotations

import os
import uuid

import pytest

from q_guardian.security.auth import reset_auth_singletons

TEST_USER = "e2e_" + uuid.uuid4().hex[:8]
TEST_PASS = "e2e-strong-password"


async def _db_available() -> bool:
    from q_guardian.database import client as db_client_module

    db = db_client_module.get_db_client()
    try:
        await db.connect()
        ok = await db.ping()
        return bool(ok)
    except Exception:
        return False
    finally:
        await db.disconnect()
        db_client_module._client_instance = None


@pytest.fixture
def mongo_url() -> str:
    """Return the configured MongoDB URL with a unique e2e database."""
    return os.environ.get("MONGODB_URL", "mongodb://localhost:27017")


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_USERS", raising=False)
    reset_auth_singletons()
    yield
    reset_auth_singletons()


@pytest.mark.asyncio
async def test_full_auth_lifecycle(mongo_url: str) -> None:
    if not await _db_available():
        pytest.skip("MongoDB not reachable; skipping real-persistence E2E")

    from httpx import ASGITransport, AsyncClient

    from q_guardian.api.app import create_app
    from q_guardian.database import client as db_client_module

    # Connect the shared DB client on THIS test's event loop so the
    # repositories resolve a live connection during the requests.
    db_client_module._client_instance = None
    db = db_client_module.get_db_client()
    await db.connect()

    app = create_app()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 1. Register
            reg = await ac.post(
                "/api/v1/auth/register",
                json={"username": TEST_USER, "password": TEST_PASS},
            )
            assert reg.status_code == 201, reg.text

            # 2. Simulate a server restart: drop the in-memory auth singleton so
            #    a fresh AuthenticationService re-reads only durable state. The
            #    registered account lives in MongoDB and must survive.
            reset_auth_singletons()

            # 3. Login after "restart"
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": TEST_USER, "password": TEST_PASS},
            )
            assert login.status_code == 200, login.text
            tokens = login.json()["data"]["tokens"]
            access = tokens["access"]
            refresh = tokens["refresh"]

            # 4. Access a protected endpoint with the issued token
            protected = await ac.get(
                "/api/v1/system/version",
                headers={"Authorization": f"Bearer {access}"},
            )
            assert protected.status_code == 200, protected.text

            # 5. Log out (revokes access + refresh)
            logout = await ac.post(
                "/api/v1/auth/logout",
                json={"refresh_token": refresh},
                headers={"Authorization": f"Bearer {access}"},
            )
            assert logout.status_code == 200, logout.text
            assert logout.json()["data"]["revoked"] == 2

            # 6a. Revoked access token is now rejected
            denied = await ac.get(
                "/api/v1/system/version",
                headers={"Authorization": f"Bearer {access}"},
            )
            assert denied.status_code == 401, denied.text
            assert denied.json()["error"]["details"]["reason"] == "token_revoked"

            # 6b. Revoked refresh token can no longer mint new access tokens
            refresh_resp = await ac.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh},
            )
            assert refresh_resp.status_code == 401, refresh_resp.text

            # 6c. Invalid login is rejected
            bad = await ac.post(
                "/api/v1/auth/login",
                json={"username": TEST_USER, "password": "wrong-password"},
            )
            assert bad.status_code == 401, bad.text

            # Cleanup: remove the test account
            from q_guardian.database.repositories.user_repository import (
                build_default_user_repository,
            )

            deleted = await build_default_user_repository().delete_user(TEST_USER)
            assert deleted is True
    finally:
        await db.disconnect()
        db_client_module._client_instance = None
