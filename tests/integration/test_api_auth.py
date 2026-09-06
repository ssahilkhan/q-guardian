"""Integration tests for API authentication enforcement.

Verifies that protected v1 endpoints reject unauthenticated and invalid
credentials with a structured 401, accept valid JWT access tokens and API
keys, and that public routes (root, health, docs, console UI) remain open.

The health endpoint is intentionally public so orchestration platforms can
probe readiness without credentials; system/analysis/console endpoints are
protected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from q_guardian.security.auth import APIKeyService, JWTService, get_api_key_service

if TYPE_CHECKING:
    from httpx import AsyncClient

# Every protected operation exposed under /api/v1 (11 total; the root
# ``/`` and ``/api/v1/health`` routes are public by design).
ALL_ENDPOINTS: list[tuple[str, str]] = [
    ("GET", "/api/v1/analysis"),
    ("POST", "/api/v1/analysis/scan"),
    ("GET", "/api/v1/analysis/fake-id"),
    ("GET", "/api/v1/console/components"),
    ("GET", "/api/v1/console/configuration"),
    ("GET", "/api/v1/console/models"),
    ("GET", "/api/v1/console/research"),
    ("GET", "/api/v1/console/rules"),
    ("GET", "/api/v1/console/summary"),
    ("GET", "/api/v1/system/status"),
    ("GET", "/api/v1/system/version"),
]

ENDPOINT_IDS = [f"{method}_{path.replace('/', '_')}" for method, path in ALL_ENDPOINTS]

SCAN_BODY = {"prompt": "What is the weather like in Paris today?"}

#: A protected endpoint used to probe credential rejection behaviour.
PROBE_PATH = "/api/v1/system/version"


async def _request(client: AsyncClient, method: str, path: str) -> AsyncClient | object:
    if method == "POST":
        return await client.post(path, json=SCAN_BODY)
    return await client.get(path)


@pytest.fixture
def api_key_headers() -> dict[str, str]:
    """Headers carrying a freshly provisioned valid API key."""
    raw_key, _record = get_api_key_service().generate_api_key(
        name="auth-test", owner="auth-tests", roles=["service"]
    )
    return {"X-API-Key": raw_key}


@pytest.mark.asyncio
class TestUnauthenticatedRejected:
    """Every protected v1 endpoint must reject requests without credentials."""

    @pytest.mark.parametrize(("method", "path"), ALL_ENDPOINTS, ids=ENDPOINT_IDS)
    async def test_missing_credentials_returns_401(
        self,
        client: AsyncClient,
        method: str,
        path: str,
    ) -> None:
        response = await _request(client, method, path)
        assert response.status_code == 401
        body = response.json()
        assert body["error"]["code"] == "AUTHENTICATION_ERROR"
        assert body["error"]["details"]["reason"] == "missing_credentials"

    async def test_malformed_authorization_scheme_rejected(self, client: AsyncClient) -> None:
        response = await client.get(PROBE_PATH, headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert response.status_code == 401
        reason = response.json()["error"]["details"]["reason"]
        assert reason == "malformed_authorization_header"

    async def test_empty_bearer_token_rejected(self, client: AsyncClient) -> None:
        response = await client.get(PROBE_PATH, headers={"Authorization": "Bearer "})
        assert response.status_code == 401


@pytest.mark.asyncio
class TestInvalidCredentialsRejected:
    """Invalid credentials of every flavor are rejected."""

    async def test_garbage_jwt_rejected(self, client: AsyncClient) -> None:
        response = await client.get(PROBE_PATH, headers={"Authorization": "Bearer not-a-jwt"})
        assert response.status_code == 401
        reason = response.json()["error"]["details"]["reason"]
        assert reason == "token_invalid"

    async def test_expired_jwt_rejected(self, client: AsyncClient) -> None:
        token = await JWTService().create_access_token({"sub": "tester"}, expires_minutes=-1)
        response = await client.get(PROBE_PATH, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        reason = response.json()["error"]["details"]["reason"]
        assert reason == "token_expired"

    async def test_refresh_token_rejected_as_access_credential(self, client: AsyncClient) -> None:
        refresh_token = await JWTService().create_refresh_token({"sub": "tester"})
        response = await client.get(
            PROBE_PATH, headers={"Authorization": f"Bearer {refresh_token}"}
        )
        assert response.status_code == 401
        reason = response.json()["error"]["details"]["reason"]
        assert reason == "wrong_token_type"

    async def test_wrong_secret_jwt_rejected(self, client: AsyncClient) -> None:
        forged = await JWTService(secret_key="rogue-signing-secret").create_access_token(
            {"sub": "tester"}
        )
        response = await client.get(PROBE_PATH, headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401

    async def test_unknown_api_key_rejected(self, client: AsyncClient) -> None:
        headers = {"X-API-Key": f"{APIKeyService.KEY_PREFIX}{'0' * 64}"}
        response = await client.get(PROBE_PATH, headers=headers)
        assert response.status_code == 401
        reason = response.json()["error"]["details"]["reason"]
        assert reason == "invalid_api_key"

    async def test_revoked_api_key_rejected(self, client: AsyncClient) -> None:
        service = get_api_key_service()
        raw_key, record = service.generate_api_key(name="revoke-me")
        assert service.revoke_api_key(record.key_id) is True

        response = await client.get(PROBE_PATH, headers={"X-API-Key": raw_key})

        assert response.status_code == 401
        reason = response.json()["error"]["details"]["reason"]
        assert reason == "invalid_api_key"

    async def test_expired_api_key_rejected(self, client: AsyncClient) -> None:
        raw_key, _record = get_api_key_service().generate_api_key(ttl_days=-1)

        response = await client.get(PROBE_PATH, headers={"X-API-Key": raw_key})

        assert response.status_code == 401
        reason = response.json()["error"]["details"]["reason"]
        assert reason == "invalid_api_key"


@pytest.mark.asyncio
class TestValidAuthenticationAccepted:
    """Valid credentials authenticate every protected v1 endpoint."""

    @pytest.mark.parametrize(("method", "path"), ALL_ENDPOINTS, ids=ENDPOINT_IDS)
    async def test_valid_jwt_accepted_on_all_endpoints(
        self,
        authorized_client: AsyncClient,
        method: str,
        path: str,
    ) -> None:
        response = await _request(authorized_client, method, path)
        # Business logic may legitimately 404 unknown IDs; auth failures
        # would surface as 401/403.
        assert response.status_code not in {401, 403}, response.text

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", "/api/v1/analysis/scan"),
            ("GET", "/api/v1/analysis"),
            ("GET", "/api/v1/console/summary"),
            ("GET", "/api/v1/system/version"),
        ],
    )
    async def test_valid_api_key_accepted(
        self,
        client: AsyncClient,
        api_key_headers: dict[str, str],
        method: str,
        path: str,
    ) -> None:
        client.headers.update(api_key_headers)
        response = await _request(client, method, path)
        assert response.status_code == 200, response.text

    async def test_scan_with_valid_jwt_returns_decision(
        self, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.post("/api/v1/analysis/scan", json=SCAN_BODY)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["decision"].upper() == "ALLOW"


@pytest.mark.asyncio
class TestPublicRoutesRemainOpen:
    """Public surfaces stay accessible without credentials."""

    async def test_root_open(self, client: AsyncClient) -> None:
        assert (await client.get("/")).status_code == 200

    async def test_health_open(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"healthy", "degraded"}

    async def test_health_trailing_slash_open(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/health/")).status_code == 200

    async def test_openapi_schema_open(self, client: AsyncClient) -> None:
        assert (await client.get("/openapi.json")).status_code == 200

    async def test_docs_open(self, client: AsyncClient) -> None:
        assert (await client.get("/docs")).status_code in {200, 307}

    async def test_console_ui_mount_open(self, client: AsyncClient) -> None:
        assert (await client.get("/ui/index.html")).status_code == 200

    async def test_cors_preflight_unauthenticated_succeeds(self, client: AsyncClient) -> None:
        response = await client.options(
            "/api/v1/analysis/scan",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_error_paths_never_leak_credentials(client: AsyncClient) -> None:
    """Rejection responses never echo presented credential material."""
    secret_material = APIKeyService.KEY_PREFIX + "a" * 64
    response = await client.get(
        PROBE_PATH,
        headers={"X-API-Key": secret_material, "Authorization": "Bearer garbage"},
    )
    assert response.status_code == 401
    assert secret_material not in response.text
