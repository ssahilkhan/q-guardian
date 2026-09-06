"""Unit tests for self-service registration, persistent auth and logout.

Covers the Phase 3-6 additions to :mod:`q_guardian.security.auth`:

- ``register_user`` validation, bcrypt hashing, dedup and role assignment
- registered-user authentication against the persistent repository
- token revocation (logout) and blocklist enforcement
- the production vs testing store-unavailable error contract
"""

from __future__ import annotations

import json

import pytest

from q_guardian.database.repositories.user_repository import InMemoryUserRepository
from q_guardian.exceptions.base import (
    DatabaseError,
    ValidationError,
)
from q_guardian.security.auth import (
    AuthenticationService,
    JWTService,
    hash_password,
    reset_auth_singletons,
)
from q_guardian.security.token_blocklist import (
    InMemoryTokenBlocklistRepository,
    TokenBlocklistService,
)


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate auth environment variables and singletons per test."""
    monkeypatch.delenv("AUTH_USERS", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    reset_auth_singletons()
    yield
    reset_auth_singletons()


def _service(
    repo: InMemoryUserRepository, blocklist: TokenBlocklistService
) -> AuthenticationService:
    return AuthenticationService(
        jwt_service=JWTService(),
        user_repository=repo,
        token_blocklist=blocklist,
    )


@pytest.fixture
def repo() -> InMemoryUserRepository:
    """A fresh in-memory user store (test double)."""
    return InMemoryUserRepository()


@pytest.fixture
def blocklist() -> TokenBlocklistService:
    """A fresh in-memory blocklist (test double)."""
    return TokenBlocklistService(repository=InMemoryTokenBlocklistRepository())


class TestRegistration:
    """Tests for self-service account registration."""

    async def test_register_creates_persisted_analyst_account(self, repo) -> None:
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))
        account = await svc.register_user("operator", "correct-password")

        assert account["username"] == "operator"
        assert account["roles"] == ["analyst"]

        # Persisted record carries a bcrypt hash, never the plaintext.
        record = await repo.get_by_username("operator")
        assert record is not None
        assert record["password_hash"] != "correct-password"
        assert record["password_hash"].startswith("$2")
        assert record["roles"] == ["analyst"]

    async def test_register_duplicate_username_rejected(self, repo) -> None:
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))
        await svc.register_user("taken", "correct-password")

        with pytest.raises(ValidationError) as exc_info:
            await svc.register_user("taken", "another-password")
        assert exc_info.value.status_code == 422
        assert exc_info.value.details.get("reason") == "duplicate"

    async def test_register_short_password_rejected(self, repo) -> None:
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))

        with pytest.raises(ValidationError):
            await svc.register_user("newbie", "short")

    async def test_register_invalid_username_rejected(self, repo) -> None:
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))

        for bad in ("ab", "has space", "emoji😀", "a" * 65):
            with pytest.raises(ValidationError):
                await svc.register_user(bad, "correct-password")

    async def test_register_too_long_password_rejected(self, repo) -> None:
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))

        with pytest.raises(ValidationError):
            await svc.register_user("long", "x" * 200)

    async def test_register_never_grants_elevated_roles(self, repo) -> None:
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))
        # No role parameter is even exposed; registration is analyst-only.
        await svc.register_user("plain", "correct-password")
        record = await repo.get_by_username("plain")
        assert record["roles"] == ["analyst"]


class TestRegisteredAuthentication:
    """Tests for authenticating a persisted (registered) user."""

    async def test_valid_credentials_issue_tokens(self, repo) -> None:
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))
        await svc.register_user("alice", "correct-password")

        result = await svc.authenticate("alice", "correct-password")

        assert result is not None
        assert result["username"] == "alice"
        assert "analyst" in result["roles"]
        claims = await JWTService().verify_token(
            result["tokens"]["access"], expected_type=JWTService.ACCESS_TOKEN_TYPE
        )
        assert claims["sub"] == "alice"

    async def test_wrong_password_rejected(self, repo) -> None:
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))
        await svc.register_user("alice", "correct-password")

        assert await svc.authenticate("alice", "wrong-password") is None

    async def test_unknown_user_rejected(self, repo) -> None:
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))

        assert await svc.authenticate("ghost", "anything") is None

    async def test_env_users_still_authenticate(self, repo, monkeypatch) -> None:
        """Environment-provisioned users keep working alongside registered ones."""
        users = {"admin": {"password_hash": hash_password("adminpw"), "roles": ["admin"]}}
        monkeypatch.setenv("AUTH_USERS", json.dumps(users))
        svc = _service(repo, TokenBlocklistService(repository=InMemoryTokenBlocklistRepository()))

        result = await svc.authenticate("admin", "adminpw")

        assert result is not None
        assert result["roles"] == ["admin"]

    async def test_store_unavailable_is_clear_in_production(self, monkeypatch, blocklist) -> None:
        """Production surfaces a clear DatabaseError, not a silent fallback."""

        class BrokenRepo:
            async def get_by_username(self, username: str):
                msg = "cannot connect"
                raise RuntimeError(msg)

        class ProdApp:
            @property
            def is_production(self) -> bool:
                return True

        import q_guardian.security.auth as auth_module
        from q_guardian.config.settings import get_settings as real_get_settings

        real = real_get_settings()

        class ProdSettings:
            app = ProdApp()
            security = real.security

        monkeypatch.setattr(auth_module, "get_settings", lambda: ProdSettings())
        svc = AuthenticationService(
            jwt_service=JWTService(),
            user_repository=BrokenRepo(),  # type: ignore[arg-type]
            token_blocklist=blocklist,
        )

        with pytest.raises(DatabaseError):
            await svc.authenticate("anyone", "password")


class TestLogoutRevocation:
    """Tests for token revocation via logout and blocklist enforcement."""

    async def test_revoked_access_token_is_blocked(self, repo, blocklist) -> None:
        svc = _service(repo, blocklist)
        result = await svc.register_user("bob", "correct-password")
        assert result is not None
        login = await svc.authenticate("bob", "correct-password")
        assert login is not None

        revoked = await svc.revoke_tokens(login["tokens"]["access"])
        assert revoked == 1

        jti = (
            await JWTService().verify_token(
                login["tokens"]["access"], expected_type=JWTService.ACCESS_TOKEN_TYPE
            )
        )["jti"]
        assert await blocklist.is_token_blocked(jti) is True

    async def test_revoked_refresh_token_rejected_on_refresh(self, repo, blocklist) -> None:
        svc = _service(repo, blocklist)
        await svc.register_user("carol", "correct-password")
        login = await svc.authenticate("carol", "correct-password")
        assert login is not None

        await svc.revoke_tokens(None, login["tokens"]["refresh"])

        assert await svc.refresh(login["tokens"]["refresh"]) is None

    async def test_refresh_works_before_revocation(self, repo, blocklist) -> None:
        svc = _service(repo, blocklist)
        await svc.register_user("dave", "correct-password")
        login = await svc.authenticate("dave", "correct-password")
        assert login is not None

        refreshed = await svc.refresh(login["tokens"]["refresh"])
        assert refreshed is not None

    async def test_revoking_pair_returns_two(self, repo, blocklist) -> None:
        svc = _service(repo, blocklist)
        await svc.register_user("erin", "correct-password")
        login = await svc.authenticate("erin", "correct-password")
        assert login is not None

        revoked = await svc.revoke_tokens(login["tokens"]["access"], login["tokens"]["refresh"])
        assert revoked == 2

    async def test_revoking_invalid_token_never_raises(self, repo, blocklist) -> None:
        svc = _service(repo, blocklist)
        assert await svc.revoke_tokens("not-a-jwt") == 0


class TestTokenBlocklistService:
    """Tests for the blocklist facade semantics."""

    async def test_block_then_check(self, blocklist) -> None:
        from datetime import UTC, datetime, timedelta

        expires = datetime.now(UTC) + timedelta(minutes=5)
        assert await blocklist.block_token("jti-1", expires) is True
        assert await blocklist.is_token_blocked("jti-1") is True

    async def test_empty_jti_not_blocked(self, blocklist) -> None:
        from datetime import UTC, datetime, timedelta

        assert await blocklist.is_token_blocked("") is False
        assert await blocklist.block_token("", datetime.now(UTC) + timedelta(minutes=1)) is False

    async def test_expired_entries_dropped(self) -> None:
        from datetime import UTC, datetime, timedelta

        repo = InMemoryTokenBlocklistRepository()
        svc = TokenBlocklistService(repository=repo)
        assert await svc.block_token("past", datetime.now(UTC) - timedelta(minutes=1)) is True
        assert await svc.is_token_blocked("past") is False
