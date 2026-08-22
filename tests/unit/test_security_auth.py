"""Task 1 authentication tests.

Covers JWT creation/validation/expiration, API key
generation/validation/lifecycle, and the /auth HTTP endpoints.
"""

from __future__ import annotations

from typing import Any

import pytest

from q_guardian.api.dependencies import require_auth
from q_guardian.dependencies.container import get_api_key_service, get_jwt_service
from q_guardian.exceptions.base import AuthenticationError
from q_guardian.security.auth import APIKeyService, AuthenticationService, JWTService

# =============================================================================
# JWT unit tests
# =============================================================================


async def test_jwt_valid_token_roundtrip() -> None:
    """A valid access token verifies and returns its claims."""
    service = JWTService(secret_key="unit-test-secret", algorithm="HS256")
    token = await service.create_access_token({"sub": "user-1", "roles": ["admin"]})
    claims = await service.verify_token(token, expected_type="access")
    assert claims["sub"] == "user-1"
    assert claims["roles"] == ["admin"]
    assert claims["type"] == "access"


async def test_jwt_invalid_token_rejected() -> None:
    """A malformed/garbage token is rejected with AuthenticationError."""
    service = JWTService(secret_key="unit-test-secret", algorithm="HS256")
    with pytest.raises(AuthenticationError):
        await service.verify_token("not-a-real-jwt")


async def test_jwt_wrong_signature_rejected() -> None:
    """A token signed with a different key is rejected."""
    signer = JWTService(secret_key="key-a", algorithm="HS256")
    verifier = JWTService(secret_key="key-b", algorithm="HS256")
    token = await signer.create_access_token({"sub": "user-1"})
    with pytest.raises(AuthenticationError):
        await verifier.verify_token(token)


async def test_jwt_expired_token_rejected() -> None:
    """An expired token is rejected with AuthenticationError."""
    service = JWTService(secret_key="unit-test-secret", algorithm="HS256")
    token = await service.create_access_token({"sub": "user-1"}, expires_minutes=-1)
    with pytest.raises(AuthenticationError, match="expired"):
        await service.verify_token(token)


async def test_jwt_missing_sub_rejected() -> None:
    """Token creation without a 'sub' claim fails."""
    service = JWTService(secret_key="unit-test-secret", algorithm="HS256")
    with pytest.raises(AuthenticationError):
        await service.create_access_token({})


async def test_jwt_refresh_token_type_mismatch_rejected() -> None:
    """A refresh token does not pass access-token verification."""
    service = JWTService(secret_key="unit-test-secret", algorithm="HS256")
    refresh = await service.create_refresh_token("user-1")
    with pytest.raises(AuthenticationError, match="token type"):
        await service.verify_token(refresh, expected_type="access")


async def test_authentication_service_valid_credentials() -> None:
    """Configured admin credentials authenticate successfully."""
    service = AuthenticationService()
    principal = await service.authenticate("admin", "change-me-admin-password")
    assert principal is not None
    assert principal["sub"] == "admin"
    assert "admin" in principal["roles"]


async def test_authentication_service_invalid_credentials() -> None:
    """Wrong credentials return None instead of a principal."""
    service = AuthenticationService()
    assert await service.authenticate("admin", "wrong-password") is None
    assert await service.authenticate("nobody", "change-me-admin-password") is None


# =============================================================================
# API key unit tests
# =============================================================================


async def test_api_key_valid() -> None:
    """A freshly generated key validates and authenticates."""
    service = APIKeyService()
    record, raw_key = await service.generate_api_key(name="valid-key-test")
    assert raw_key.startswith("qg_")
    assert await service.validate_api_key(raw_key) is True
    authenticated = await service.authenticate_api_key(raw_key)
    assert authenticated is not None
    assert authenticated.key_id == record.key_id


async def test_api_key_invalid() -> None:
    """Unknown keys fail validation."""
    service = APIKeyService()
    assert await service.validate_api_key("qg_totally-invalid-key") is False
    assert await service.authenticate_api_key("qg_totally-invalid-key") is None


async def test_api_key_inactive_rejected() -> None:
    """Deactivated keys fail validation until reactivated."""
    service = APIKeyService()
    record, raw_key = await service.generate_api_key(name="inactive-key-test")
    assert await service.deactivate_api_key(record.key_id) is True
    assert await service.validate_api_key(raw_key) is False
    assert await service.authenticate_api_key(raw_key) is None
    # Reactivation restores access.
    assert await service.activate_api_key(record.key_id) is True
    assert await service.validate_api_key(raw_key) is True


async def test_api_key_raw_secret_never_stored_or_exposed() -> None:
    """Only the hash and prefix are stored; public dict excludes secrets."""
    service = APIKeyService()
    record, raw_key = await service.generate_api_key(name="secret-hygiene-test")
    assert record.key_hash != raw_key
    assert raw_key not in record.key_hash
    public = record.to_public_dict()
    assert "key_hash" not in public
    assert raw_key not in str(public)


async def test_api_key_expiration_in_past_rejected() -> None:
    """Keys created with a past expiration are rejected immediately."""
    from datetime import UTC, datetime, timedelta

    service = APIKeyService()
    _, raw_key = await service.generate_api_key(
        name="expired-key-test",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert await service.validate_api_key(raw_key) is False


# =============================================================================
# HTTP endpoint tests (/api/v1/auth/*)
# =============================================================================


def _admin_credentials(settings: Any) -> dict[str, str]:
    """Build a token request body from configured settings (no hardcoding)."""
    security = settings.security
    return {"username": security.admin_username, "password": security.admin_password}


async def test_token_endpoint_valid_credentials(client: Any, settings: Any) -> None:
    """POST /auth/token issues a JWT for valid credentials."""
    response = await client.post("/api/v1/auth/token", json=_admin_credentials(settings))
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["access_token"]
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["expires_in"] == settings.security.jwt_expiration_minutes * 60


async def test_token_endpoint_invalid_credentials(client: Any) -> None:
    """POST /auth/token returns 401 for wrong credentials."""
    response = await client.post(
        "/api/v1/auth/token",
        json={"username": "admin", "password": "definitely-wrong"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


async def test_protected_endpoint_missing_authentication(client: Any) -> None:
    """GET /auth/api-keys without any credentials returns 401."""
    response = await client.get("/api/v1/auth/api-keys")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


async def test_protected_endpoint_with_valid_jwt(client: Any, settings: Any) -> None:
    """A Bearer JWT obtained from /auth/token grants access."""
    token_response = await client.post(
        "/api/v1/auth/token", json=_admin_credentials(settings)
    )
    token = token_response.json()["data"]["access_token"]
    response = await client.get(
        "/api/v1/auth/api-keys",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


async def test_protected_endpoint_with_invalid_jwt(client: Any) -> None:
    """A garbage Bearer token returns 401."""
    response = await client.get(
        "/api/v1/auth/api-keys",
        headers={"Authorization": "Bearer garbage.token.value"},
    )
    assert response.status_code == 401


async def test_api_key_lifecycle_over_http(client: Any, settings: Any) -> None:
    """Full lifecycle: token -> create key -> use key -> revoke -> rejected."""
    token_response = await client.post(
        "/api/v1/auth/token", json=_admin_credentials(settings)
    )
    assert token_response.status_code == 200
    bearer = {"Authorization": f"Bearer {token_response.json()['data']['access_token']}"}

    create_response = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "http-lifecycle-test"},
        headers=bearer,
    )
    assert create_response.status_code == 201
    created = create_response.json()["data"]
    raw_key = created["api_key"]
    assert raw_key.startswith("qg_")

    # The raw key authenticates (403 = valid key, non-admin role;
    # an invalid key would yield 401 instead).
    key_headers = {settings.security.api_key_header: raw_key}
    forbidden = await client.get("/api/v1/auth/api-keys", headers=key_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "SECURITY_ERROR"

    # Listing via admin JWT never exposes raw secrets or hashes.
    listed_response = await client.get("/api/v1/auth/api-keys", headers=bearer)
    assert listed_response.status_code == 200
    listed = listed_response.json()["data"]
    assert all("api_key" not in entry and "key_hash" not in entry for entry in listed)

    # Revoke by id; the key must stop working afterwards.
    revoke_response = await client.delete(
        f"/api/v1/auth/api-keys/{created['key_id']}", headers=bearer
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["data"]["revoked"] is True

    rejected = await client.get("/api/v1/auth/api-keys", headers=key_headers)
    assert rejected.status_code == 401


async def test_revoked_jwt_still_verifiable_but_service_key_isolated() -> None:
    """JWT and API key services resolve independently via the container."""
    jwt_service = get_jwt_service()
    api_key_service = get_api_key_service()
    token = await jwt_service.create_access_token({"sub": "container-check"})
    claims = await jwt_service.verify_token(token)
    assert claims["sub"] == "container-check"
    record, raw_key = await api_key_service.generate_api_key(name="container-check")
    assert await api_key_service.validate_api_key(raw_key) is True
    assert record.active is True


async def test_require_auth_raises_without_credentials() -> None:
    """require_auth raises AuthenticationError when no credentials exist."""

    class _FakeRequest:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

    with pytest.raises(AuthenticationError):
        await require_auth(_FakeRequest())  # type: ignore[arg-type]
