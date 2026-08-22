"""Unit tests for security authentication services (JWT, users, API keys).

Focused Phase 1 coverage:
- JWTService: creation, verification, expiry, tampering, token types
- AuthenticationService: credential flow via AUTH_USERS env provisioning
- AuthorizationService: role-based permission checks
- APIKeyService: generation, validation, revocation, expiry, env bootstrap
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from q_guardian.exceptions.base import AuthenticationError
from q_guardian.security.auth import (
    APIKeyRecord,
    APIKeyService,
    AuthenticationService,
    AuthorizationService,
    JWTService,
    hash_password,
    reset_auth_singletons,
)


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate auth environment variables and singletons per test."""
    monkeypatch.delenv("AUTH_USERS", raising=False)
    monkeypatch.delenv("API_KEYS", raising=False)
    reset_auth_singletons()
    yield
    reset_auth_singletons()


class TestJWTService:
    """Tests for JWT token creation and verification."""

    async def test_create_and_verify_access_token(self) -> None:
        service = JWTService()
        token = await service.create_access_token({"sub": "user-1", "roles": ["admin"]})
        payload = await service.verify_token(token, expected_type=JWTService.ACCESS_TOKEN_TYPE)

        assert payload["sub"] == "user-1"
        assert payload["roles"] == ["admin"]
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload

    async def test_create_refresh_token_has_refresh_type(self) -> None:
        service = JWTService()
        token = await service.create_refresh_token({"sub": "user-1"})
        payload = await service.verify_token(token)

        assert payload["type"] == "refresh"

    async def test_expired_token_raises_authentication_error(self) -> None:
        service = JWTService()
        token = await service.create_access_token({"sub": "user-1"}, expires_minutes=-1)

        with pytest.raises(AuthenticationError) as exc_info:
            await service.verify_token(token)
        assert exc_info.value.details.get("reason") == "token_expired"
        assert exc_info.value.status_code == 401

    async def test_tampered_token_rejected(self) -> None:
        service = JWTService()
        token = await service.create_access_token({"sub": "user-1"})
        tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")

        with pytest.raises(AuthenticationError):
            await service.verify_token(tampered)

    async def test_garbage_token_rejected(self) -> None:
        service = JWTService()

        with pytest.raises(AuthenticationError):
            await service.verify_token("not-a-jwt")

    async def test_missing_token_rejected(self) -> None:
        service = JWTService()

        with pytest.raises(AuthenticationError):
            await service.verify_token("")

    async def test_wrong_token_type_enforced(self) -> None:
        service = JWTService()
        refresh = await service.create_refresh_token({"sub": "user-1"})

        with pytest.raises(AuthenticationError) as exc_info:
            await service.verify_token(refresh, expected_type=JWTService.ACCESS_TOKEN_TYPE)
        assert exc_info.value.details.get("reason") == "wrong_token_type"

    async def test_empty_payload_rejected(self) -> None:
        service = JWTService()

        with pytest.raises(AuthenticationError):
            await service.create_access_token({})

    async def test_custom_expiry_respected(self) -> None:
        service = JWTService()
        token = await service.create_access_token({"sub": "u"}, expires_minutes=5)
        payload = await service.verify_token(token)

        issued_at = datetime.fromtimestamp(payload["iat"], tz=UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        delta = expires_at - issued_at
        assert timedelta(minutes=4) < delta <= timedelta(minutes=5, seconds=5)


class TestAuthenticationService:
    """Tests for username/password authentication."""

    def _provision_user(
        self, monkeypatch: pytest.MonkeyPatch, username: str, password: str, roles: list[str]
    ) -> None:
        import json

        users = {username: {"password_hash": hash_password(password), "roles": roles}}
        monkeypatch.setenv("AUTH_USERS", json.dumps(users))

    async def test_no_users_configured_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUTH_USERS", raising=False)
        service = AuthenticationService()

        assert service.users_configured is False
        result = await service.authenticate("admin", "whatever")
        assert result is None

    async def test_valid_credentials_return_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._provision_user(monkeypatch, "analyst", "s3cret-password", ["analyst"])
        service = AuthenticationService()

        result = await service.authenticate("analyst", "s3cret-password")

        assert result is not None
        assert result["username"] == "analyst"
        assert result["roles"] == ["analyst"]
        tokens = result["tokens"]
        assert set(tokens) == {"access", "refresh"}

        access_claims = await JWTService().verify_token(
            tokens["access"], expected_type=JWTService.ACCESS_TOKEN_TYPE
        )
        assert access_claims["sub"] == "analyst"

    async def test_invalid_password_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._provision_user(monkeypatch, "analyst", "s3cret-password", [])
        service = AuthenticationService()

        assert await service.authenticate("analyst", "wrong-password") is None

    async def test_unknown_user_returns_none(self) -> None:
        service = AuthenticationService()

        assert await service.authenticate("ghost", "nope") is None

    async def test_invalid_auth_users_json_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTH_USERS", "{not valid json")
        service = AuthenticationService()

        assert service.users_configured is False
        assert await service.authenticate("x", "y") is None

    async def test_refresh_flow_issues_new_access_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._provision_user(monkeypatch, "svc", "pw", ["service"])
        service = AuthenticationService()
        first = await service.authenticate("svc", "pw")
        assert first is not None

        refreshed = await service.refresh(first["tokens"]["refresh"])

        assert refreshed is not None
        new_claims = await JWTService().verify_token(
            refreshed["tokens"]["access"], expected_type=JWTService.ACCESS_TOKEN_TYPE
        )
        assert new_claims["sub"] == "svc"

    async def test_refresh_with_access_token_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._provision_user(monkeypatch, "svc", "pw", [])
        service = AuthenticationService()
        first = await service.authenticate("svc", "pw")
        assert first is not None

        assert await service.refresh(first["tokens"]["access"]) is None


class TestAuthorizationService:
    """Tests for role-based authorization."""

    async def test_admin_wildcard_allows_everything(self) -> None:
        service = AuthorizationService()
        service.assign_role("u1", "admin")

        assert await service.check_permission("u1", "analysis", "delete") is True
        assert await service.check_permission("u1", "anything", "anyaction") is True

    async def test_specific_role_permission_allowed(self) -> None:
        service = AuthorizationService()
        service.assign_role("u2", "analyst")

        assert await service.check_permission("u2", "analysis", "read") is True
        assert await service.check_permission("u2", "scan", "create") is True

    async def test_unmatched_permission_denied(self) -> None:
        service = AuthorizationService()
        service.assign_role("u3", "analyst")

        assert await service.check_permission("u3", "analysis", "delete") is False

    async def test_unknown_user_denied(self) -> None:
        service = AuthorizationService()

        assert await service.check_permission("nobody", "analysis", "read") is False


class TestAPIKeyService:
    """Tests for API key generation and validation."""

    async def test_generate_and_validate_key(self) -> None:
        service = APIKeyService(load_env_keys=False)
        raw_key, record = service.generate_api_key(name="ci", owner="team-a", roles=["service"])

        assert raw_key.startswith(APIKeyService.KEY_PREFIX)
        assert record.key_prefix == raw_key[: APIKeyService.DISPLAY_PREFIX_LENGTH]
        assert service.validate_api_key(raw_key) is True

        resolved = service.authenticate_api_key(raw_key)
        assert resolved is not None
        assert resolved.key_id == record.key_id
        assert resolved.roles == ["service"]

    async def test_unknown_key_rejected(self) -> None:
        service = APIKeyService(load_env_keys=False)

        assert service.validate_api_key("qg_" + "0" * 64) is False
        assert service.validate_api_key("") is False

    async def test_revoked_key_rejected(self) -> None:
        service = APIKeyService(load_env_keys=False)
        raw_key, record = service.generate_api_key()

        assert service.revoke_api_key(record.key_id) is True
        assert record.revoked is True
        assert service.validate_api_key(raw_key) is False

    async def test_revocation_of_unknown_id_returns_false(self) -> None:
        service = APIKeyService(load_env_keys=False)

        assert service.revoke_api_key("missing-id") is False

    async def test_expired_key_rejected(self) -> None:
        service = APIKeyService(load_env_keys=False)
        raw_key, _record = service.generate_api_key(ttl_days=1)
        # Force expiry directly on the stored record.
        record_obj = next(iter(service._store.values()))
        record_obj.expires_at = datetime.now(UTC) - timedelta(days=1)

        assert service.validate_api_key(raw_key) is False

    async def test_list_keys_never_exposes_hashes(self) -> None:
        service = APIKeyService(load_env_keys=False)
        service.generate_api_key(name="k1", owner="o1")

        listed = service.list_api_keys()

        assert len(listed) == 1
        entry = listed[0]
        assert "key_hash" not in entry
        assert entry["name"] == "k1"

    async def test_env_bootstrap_raw_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bootstrap = f"{APIKeyService.KEY_PREFIX}{'ab' * 32}"
        monkeypatch.setenv("API_KEYS", bootstrap)
        service = APIKeyService()

        assert service.validate_api_key(bootstrap) is True
        assert service.key_count == 1

    async def test_env_bootstrap_sha256_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import hashlib

        digest = hashlib.sha256(b"pre-hashed-key").hexdigest()
        monkeypatch.setenv("API_KEYS", f"{APIKeyService.HASH_PREFIX}{digest}")
        service = APIKeyService()

        assert service.validate_api_key("pre-hashed-key") is True

    async def test_record_public_dict_shape(self) -> None:
        record = APIKeyRecord(
            key_id="id-1",
            key_hash="hash",
            key_prefix="qg_abcd",
            name="n",
            owner="o",
            roles=["service"],
        )

        data = record.public_dict()

        assert data["key_id"] == "id-1"
        assert data["expires_at"] is None
        assert data["revoked"] is False
        assert "key_hash" not in data


class TestAuthSingletons:
    """Tests for singleton accessors."""

    def test_singletons_are_shared(self) -> None:
        from q_guardian.security.auth import (
            get_api_key_service,
            get_authentication_service,
            get_authorization_service,
            get_jwt_service,
            get_rate_limit_service,
        )

        assert get_jwt_service() is get_jwt_service()
        assert get_authentication_service() is get_authentication_service()
        assert get_authorization_service() is get_authorization_service()
        assert get_api_key_service() is get_api_key_service()
        assert get_rate_limit_service() is get_rate_limit_service()

    def test_reset_clears_singletons(self) -> None:
        from q_guardian.security.auth import (
            get_jwt_service,
            reset_auth_singletons,
        )

        first = get_jwt_service()
        reset_auth_singletons()
        second = get_jwt_service()

        assert first is not second
