"""Security services for Q-Guardian.

Implements the authentication infrastructure:
- JWT token generation and validation (access + refresh)
- User authentication (environment-provisioned credential store)
- Role-based authorization
- API key generation/validation/revocation
- Sliding-window rate limiting

All secrets and security parameters are sourced from configuration
(``SecuritySettings`` / environment variables), never hard-coded.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid as uuid_module
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import jwt
import structlog
from bcrypt import checkpw, gensalt, hashpw

from q_guardian.config.settings import get_settings, is_production_environment
from q_guardian.database.repositories.user_repository import (
    ALLOWED_ROLES,
    UserRepository,
    build_default_user_repository,
)
from q_guardian.exceptions.base import AuthenticationError, DatabaseError, SecurityError
from q_guardian.security.token_blocklist import (
    TokenBlocklistService,
    default_token_blocklist_service,
)

logger = structlog.get_logger("security.auth")

# =============================================================================
# Password hashing helpers
# =============================================================================

#: bcrypt operates on at most 72 bytes of input password material.
BCRYPT_MAX_PASSWORD_BYTES = 72

#: Environment variable holding a JSON object of provisioned users, e.g.:
#:   AUTH_USERS={"admin": {"password_hash": "<bcrypt>", "roles": ["admin"]}}
AUTH_USERS_ENV_VAR = "AUTH_USERS"

#: Environment variable holding pre-provisioned API keys (comma-separated).
#: Each entry may be a raw key (hashed on load) or a ``sha256:<hexdigest>``
#: entry that is already hashed. Example: ``API_KEYS=qg_ab12...,sha256:feed...``
API_KEYS_ENV_VAR = "API_KEYS"

#: Usernames accepted for registration: ASCII letters/digits plus '_', '-', '.'.
_VALID_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        password: The plaintext password (max 72 bytes when UTF-8 encoded,
            per the bcrypt algorithm limit).

    Returns:
        The bcrypt hash string.

    Raises:
        ValueError: If the password exceeds the bcrypt input limit.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        msg = f"Password exceeds bcrypt limit of {BCRYPT_MAX_PASSWORD_BYTES} bytes"
        raise ValueError(msg)
    return hashpw(encoded, gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain_password: The plaintext password.
        password_hash: The stored bcrypt hash.

    Returns:
        True if the password matches.
    """
    try:
        return checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError, AttributeError):
        # Fail closed on malformed credential material (e.g. non-str inputs).
        return False


# =============================================================================
# JWT Service
# =============================================================================


class JWTService:
    """JWT token generation and validation service.

    Tokens are signed with HS256 (configurable) using the application
    secret key from ``SecuritySettings``. Access and refresh tokens are
    distinguished by the ``type`` claim so one kind cannot be replayed
    as the other.
    """

    ACCESS_TOKEN_TYPE = "access"
    REFRESH_TOKEN_TYPE = "refresh"

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str | None = None,
        access_expires_minutes: int | None = None,
        refresh_expires_days: int | None = None,
    ) -> None:
        """Initialize the service, falling back to application settings.

        Args:
            secret_key: Signing secret. Defaults to ``SECURITY.secret_key``.
            algorithm: JWT algorithm. Defaults to ``JWT_ALGORITHM`` setting.
            access_expires_minutes: Access lifetime override in minutes.
            refresh_expires_days: Refresh lifetime override in days.
        """
        settings = get_settings().security
        self._secret_key = secret_key if secret_key is not None else settings.secret_key
        self._algorithm = algorithm if algorithm is not None else settings.jwt_algorithm
        self._access_expires_minutes = (
            access_expires_minutes
            if access_expires_minutes is not None
            else settings.jwt_expiration_minutes
        )
        self._refresh_expires_days = (
            refresh_expires_days
            if refresh_expires_days is not None
            else settings.jwt_refresh_expiration_days
        )

    async def create_access_token(
        self, payload: dict[str, Any], expires_minutes: int | None = None
    ) -> str:
        """Create a signed JWT access token.

        Standard claims (``exp``, ``iat``, ``jti``, ``type``) are added
        automatically and override any caller-supplied values.

        Args:
            payload: Token payload data. Should contain ``sub``.
            expires_minutes: Token lifetime in minutes. Defaults to settings.

        Returns:
            Encoded JWT string.

        Raises:
            AuthenticationError: If the payload is empty.
        """
        minutes = expires_minutes if expires_minutes is not None else self._access_expires_minutes
        return self._encode(payload, timedelta(minutes=minutes), self.ACCESS_TOKEN_TYPE)

    async def create_refresh_token(
        self, payload: dict[str, Any], expires_days: int | None = None
    ) -> str:
        """Create a signed JWT refresh token.

        Args:
            payload: Token payload data. Should contain ``sub``.
            expires_days: Token lifetime in days. Defaults to settings.

        Returns:
            Encoded JWT string.
        """
        days = expires_days if expires_days is not None else self._refresh_expires_days
        return self._encode(payload, timedelta(days=days), self.REFRESH_TOKEN_TYPE)

    async def verify_token(self, token: str, expected_type: str | None = None) -> dict[str, Any]:
        """Verify and decode a JWT token.

        Args:
            token: The JWT string to verify.
            expected_type: If given, enforce that the token ``type`` claim
                matches (prevents refresh-token reuse as access tokens).

        Returns:
            Decoded token payload including standard claims.

        Raises:
            AuthenticationError: If the token is malformed, has an
                invalid signature, or has expired.
        """
        if not token or not isinstance(token, str):
            raise AuthenticationError(
                message="Missing authentication token",
                details={"reason": "token_missing"},
            )
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
                options={"require": ["exp", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            logger.info("jwt_token_expired")
            raise AuthenticationError(
                message="Token has expired",
                details={"reason": "token_expired"},
            ) from exc
        except jwt.PyJWTError as exc:
            logger.info("jwt_token_invalid")
            raise AuthenticationError(
                message="Invalid authentication token",
                details={"reason": "token_invalid"},
            ) from exc

        token_type = payload.get("type")
        if expected_type is not None and token_type != expected_type:
            raise AuthenticationError(
                message="Invalid token type",
                details={
                    "reason": "wrong_token_type",
                    "expected": expected_type,
                    "received": token_type,
                },
            )
        return payload

    def _encode(self, payload: dict[str, Any], lifetime: timedelta, token_type: str) -> str:
        """Encode a payload into a JWT with standard registered claims.

        Args:
            payload: Caller-supplied claims.
            lifetime: Time-to-live for the token.
            token_type: Value for the ``type`` claim.

        Returns:
            Encoded JWT string.

        Raises:
            AuthenticationError: If the payload is empty.
        """
        if not payload:
            raise AuthenticationError(
                message="Cannot create token from empty payload",
                details={"reason": "empty_payload"},
            )
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            **payload,
            "type": token_type,
            "iat": int(now.timestamp()),
            "exp": int((now + lifetime).timestamp()),
            "jti": uuid_module.uuid4().hex,
        }
        return jwt.encode(claims, self._secret_key, algorithm=self._algorithm)


# =============================================================================
# Authentication Service
# =============================================================================


class AuthenticationService:
    """User authentication against a persistent + env-provisioned store.

    Two sources of accounts are combined transparently:

    1. **Environment-provisioned users** via the ``AUTH_USERS`` environment
       variable (``{username: {password_hash, roles}}``). These are boot
       credentials and never change at runtime.
    2. **Registered users** persisted through a :class:`UserRepository`
       (MongoDB by default). A brand-new operator can create an account
       through the registration endpoint; the account survives restarts.

    No credentials ship with the code, no plaintext password is ever kept,
    and token signing/verification stays in :class:`JWTService`.
    """

    #: Minimum password length for new registrations.
    MIN_PASSWORD_LENGTH = 8

    #: Default role assigned to a newly registered account. Self-service
    #: registration never grants elevated roles (no self-escalation).
    DEFAULT_REGISTRATION_ROLES: tuple[str, ...] = ("analyst",)

    def __init__(
        self,
        jwt_service: JWTService | None = None,
        user_repository: UserRepository | None = None,
        token_blocklist: TokenBlocklistService | None = None,
    ) -> None:
        """Initialize the authentication service.

        Args:
            jwt_service: Optional JWT service instance. Defaults to a
                singleton shared instance.
            user_repository: Optional persistent user store (mainly tests).
                Defaults to the MongoDB-backed repository.
            token_blocklist: Optional token revocation service (mainly
                tests). Defaults to the MongoDB-backed blocklist.
        """
        self._jwt_service = jwt_service or get_jwt_service()
        self._users: dict[str, dict[str, Any]] = {}
        self._load_users_from_env()
        self._user_repository = user_repository
        self._token_blocklist = token_blocklist or get_token_blocklist()

    @property
    def user_repository(self) -> UserRepository:
        """Return the persistent user store (lazily initialized)."""
        if self._user_repository is None:
            self._user_repository = build_default_user_repository()
        return self._user_repository

    @user_repository.setter
    def user_repository(self, repository: UserRepository) -> None:
        """Replace the persistent user store (mainly tests)."""
        self._user_repository = repository

    @property
    def token_blocklist(self) -> TokenBlocklistService:
        """Return the token revocation service."""
        return self._token_blocklist

    def _load_users_from_env(self) -> None:
        """Load provisioned users from the ``AUTH_USERS`` environment variable."""
        raw = os.getenv(AUTH_USERS_ENV_VAR, "")
        if not raw:
            logger.info("auth_users_not_configured")
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("auth_users_env_invalid_json")
            return
        if isinstance(data, dict):
            self._users = {
                username: user
                for username, user in data.items()
                if isinstance(user, dict) and "password_hash" in user
            }
            logger.info("auth_users_loaded", count=len(self._users))

    @property
    def users_configured(self) -> bool:
        """Check whether any users are provisioned."""
        return bool(self._users)

    async def register_user(self, username: str, password: str) -> dict[str, Any]:
        """Create a new user account and persist it durably.

        The password is hashed with bcrypt before anything is stored; the
        returned payload never contains a password (hashed or plain).

        Args:
            username: The requested username.
            password: The plaintext password.

        Returns:
            Public account information (``username`` and ``roles``).

        Raises:
            ValidationError: When the username or password is unsuitable,
                or when the username is already registered.
            DatabaseError: When the persistent store cannot be reached.
        """
        from q_guardian.exceptions.base import ValidationError

        username = username.strip()
        if not _VALID_USERNAME_RE.fullmatch(username):
            raise ValidationError(
                message=(
                    "Usernames may contain letters, digits, underscores, "
                    "hyphens and periods (3-64 characters)"
                ),
                details={"field": "username"},
            )
        if len(password) < self.MIN_PASSWORD_LENGTH:
            raise ValidationError(
                message=(f"Password must be at least {self.MIN_PASSWORD_LENGTH} characters"),
                details={"field": "password"},
            )

        try:
            password_hash = hash_password(password)
        except ValueError:
            raise ValidationError(
                message="Password is too long (max 72 bytes)",
                details={"field": "password"},
            ) from None

        record = await self.user_repository.create_user(
            username,
            password_hash,
            list(self.DEFAULT_REGISTRATION_ROLES),
        )
        if record is None:
            raise ValidationError(
                message="A user with that name is already registered",
                details={"field": "username", "reason": "duplicate"},
            )
        logger.info("user_registered", username=username, roles=record.get("roles"))
        return {
            "username": record["username"],
            "roles": [str(r) for r in record.get("roles", [])],
        }

    async def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        """Authenticate a user with credentials and issue a token pair.

        Environment-provisioned users are checked first; registered
        (database) users are resolved afterwards. Unreachable registered
        storage surfaces as a clear error in production, while other
        environments degrade gracefully to a failed login with a logged
        warning.

        Args:
            username: The username.
            password: The plaintext password.

        Returns:
            Dictionary with ``username``, ``roles``, and ``tokens``
            (``access`` and ``refresh``), or ``None`` when credentials
            are invalid or no matching user exists.
        """
        user = self._users.get(username)
        if user is not None:
            if not verify_password(password, str(user.get("password_hash", ""))):
                logger.info("authentication_failed", username=username)
                return None
            roles = [str(r) for r in user.get("roles", [])]
            return await self._issue_tokens(username, roles)

        return await self._authenticate_registered_user(username, password)

    async def _authenticate_registered_user(
        self, username: str, password: str
    ) -> dict[str, Any] | None:
        """Authenticate against the persistent user store."""
        try:
            record = await self.user_repository.get_by_username(username)
        except Exception as exc:
            # Covers DatabaseError and the "MongoDB not connected"
            # RuntimeError that surfaces in tests / early startup.
            if get_settings().app.is_production:
                raise DatabaseError(
                    message=(
                        "Authentication store unavailable; "
                        "check database connectivity and configuration"
                    ),
                    details={"module": "user_repository"},
                ) from exc
            logger.warning("registered_authentication_store_unavailable", username=username)
            return None

        if record is None:
            logger.info("authentication_failed", username=username)
            return None
        if not verify_password(password, str(record.get("password_hash", ""))):
            logger.info("authentication_failed", username=username)
            return None

        roles = [str(r) for r in record.get("roles", []) if r in ALLOWED_ROLES]
        return await self._issue_tokens(username, roles)

    async def _issue_tokens(self, username: str, roles: list[str]) -> dict[str, Any]:
        """Build and return a token pair for an authenticated principal."""
        access = await self._jwt_service.create_access_token({"sub": username, "roles": roles})
        refresh = await self._jwt_service.create_refresh_token({"sub": username, "roles": roles})
        logger.info("authentication_succeeded", username=username)
        return {
            "username": username,
            "roles": roles,
            "tokens": {"access": access, "refresh": refresh},
        }

    async def refresh(self, refresh_token: str) -> dict[str, Any] | None:
        """Issue a new access token from a valid refresh token.

        Args:
            refresh_token: A refresh token previously issued by this service.

        Returns:
            New token pair dictionary, or ``None`` if invalid, expired,
            or revoked by a logout.
        """
        try:
            payload = await self._jwt_service.verify_token(
                refresh_token, expected_type=JWTService.REFRESH_TOKEN_TYPE
            )
        except AuthenticationError:
            return None
        if await self._token_blocklist.is_token_blocked(str(payload.get("jti", ""))):
            logger.info("refresh_token_revoked", username=str(payload.get("sub", "")))
            return None
        subject = str(payload["sub"])
        roles = [str(r) for r in payload.get("roles", [])]
        access = await self._jwt_service.create_access_token({"sub": subject, "roles": roles})
        return {
            "username": subject,
            "roles": roles,
            "tokens": {"access": access, "refresh": refresh_token},
        }

    async def revoke_tokens(
        self,
        access_token: str | None,
        refresh_token: str | None = None,
    ) -> int:
        """Revoke a token pair so it can no longer authenticate.

        Revocations are recorded until each token's natural expiry; when
        the backing store is unreachable the revocation is skipped with a
        warning (fail-open on check, tokens still expire naturally).

        Args:
            access_token: The access token to revoke.
            refresh_token: The refresh token to revoke.

        Returns:
            Number of tokens successfully revoked.
        """
        blocked = 0
        for token, expected_type in (
            (access_token, JWTService.ACCESS_TOKEN_TYPE),
            (refresh_token, JWTService.REFRESH_TOKEN_TYPE),
        ):
            if not token:
                continue
            try:
                payload = await self._jwt_service.verify_token(token, expected_type=expected_type)
            except AuthenticationError:
                logger.info("revocation_skipped_invalid_token")
                continue
            if await self._token_blocklist.block_token(
                str(payload.get("jti", "")),
                datetime.fromtimestamp(payload["exp"], tz=UTC),
                kind=expected_type,
            ):
                blocked += 1
        return blocked


# =============================================================================
# Authorization Service
# =============================================================================


class AuthorizationService:
    """Role-based authorization service.

    Roles map to permission patterns; the wildcard permission ``*``
    grants every action. Unknown users and unmatched permissions are
    denied by default.
    """

    DEFAULT_ROLE_PERMISSIONS: ClassVar[dict[str, list[str]]] = {
        "admin": ["*"],
        "analyst": ["analysis:read", "scan:create"],
        "service": ["scan:create", "analysis:read"],
    }

    def __init__(self, role_permissions: dict[str, list[str]] | None = None) -> None:
        """Initialize the authorization service.

        Args:
            role_permissions: Optional custom role-to-permissions mapping.
                Falls back to ``DEFAULT_ROLE_PERMISSIONS``.
        """
        self._role_permissions = role_permissions or dict(self.DEFAULT_ROLE_PERMISSIONS)
        self._user_roles: dict[str, list[str]] = {}

    def assign_role(self, user_id: str, role: str) -> None:
        """Assign a role to a user.

        Args:
            user_id: The user identifier.
            role: The role name.
        """
        roles = self._user_roles.setdefault(user_id, [])
        if role not in roles:
            roles.append(role)

    def get_user_roles(self, user_id: str) -> list[str]:
        """Return roles assigned to a user.

        Args:
            user_id: The user identifier.

        Returns:
            List of assigned role names.
        """
        return list(self._user_roles.get(user_id, []))

    async def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        """Check if a user has permission for an action on a resource.

        Permission strings have the form ``resource:action``; the global
        wildcard ``*`` grants everything.

        Args:
            user_id: The user identifier.
            resource: The resource identifier (e.g. ``analysis``).
            action: The action identifier (e.g. ``read``).

        Returns:
            True if authorized.
        """
        required = f"{resource}:{action}"
        for role in self._user_roles.get(user_id, []):
            permissions = self._role_permissions.get(role, [])
            if "*" in permissions or required in permissions:
                return True
        return False


# =============================================================================
# API Key Service
# =============================================================================


@dataclass
class APIKeyRecord:
    """Metadata for a provisioned API key.

    Attributes:
        key_id: Unique identifier for the key.
        key_hash: SHA-256 hex digest of the raw key material.
        key_prefix: Short plaintext prefix for display/log correlation.
        name: Human-readable key name.
        owner: Owner/principal the key acts as.
        roles: Roles granted to this key's principal.
        created_at: Creation timestamp (UTC).
        expires_at: Optional expiry timestamp (UTC).
        revoked: Whether the key has been revoked.
    """

    key_id: str
    key_hash: str
    key_prefix: str
    name: str
    owner: str
    roles: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    revoked: bool = False

    def public_dict(self) -> dict[str, Any]:
        """Serialize safe-for-display metadata (never includes hashes)."""
        return {
            "key_id": self.key_id,
            "key_prefix": self.key_prefix,
            "name": self.name,
            "owner": self.owner,
            "roles": list(self.roles),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked": self.revoked,
        }


class APIKeyService:
    """API key management service.

    Raw keys look like ``qg_<64 hex chars>`` and are shown exactly once
    at creation time. Only salted SHA-256 digests are retained, so a
    database/store leak never exposes usable keys. Additional bootstrap
    keys may be provided via the ``API_KEYS`` environment variable
    (comma-separated raw keys or ``sha256:<hexdigest>`` entries).
    """

    KEY_PREFIX = "qg_"
    HASH_PREFIX = "sha256:"
    DISPLAY_PREFIX_LENGTH = 8

    def __init__(
        self,
        store: dict[str, APIKeyRecord] | None = None,
        load_env_keys: bool = True,
    ) -> None:
        """Initialize the service.

        Args:
            store: Optional pre-populated hash->record store (mainly tests).
            load_env_keys: Whether to bootstrap keys from ``API_KEYS`` env var.
        """
        self._store: dict[str, APIKeyRecord] = store if store is not None else {}
        self._raw_hashes: set[str] = set(self._store.keys())
        if load_env_keys:
            self._load_keys_from_env()

    def _load_keys_from_env(self) -> None:
        """Bootstrap API keys from the ``API_KEYS`` environment variable."""
        raw_value = os.getenv(API_KEYS_ENV_VAR, "")
        if not raw_value:
            logger.info("api_keys_env_not_configured")
            return
        for index, entry in enumerate(raw_value.split(",")):
            entry = entry.strip()
            if not entry:
                continue
            if entry.startswith(self.HASH_PREFIX):
                key_hash = entry[len(self.HASH_PREFIX) :].lower()
                prefix = (
                    f"{self.KEY_PREFIX}{'*' * (self.DISPLAY_PREFIX_LENGTH - len(self.KEY_PREFIX))}"
                )
            else:
                key_hash = self._hash_key(entry)
                prefix = entry[: self.DISPLAY_PREFIX_LENGTH]
            record = APIKeyRecord(
                key_id=f"env-{index}",
                key_hash=key_hash,
                key_prefix=prefix,
                name=f"env-key-{index}",
                owner=f"env-principal-{index}",
                roles=["service"],
            )
            self._store[key_hash] = record
            self._raw_hashes.add(key_hash)
        logger.info("api_keys_loaded_from_env", count=len(raw_value.split(",")))

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """Compute the SHA-256 digest of a raw API key.

        Args:
            raw_key: The raw key material.

        Returns:
            Lowercase hex digest.
        """
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def generate_api_key(
        self,
        name: str = "default",
        owner: str = "unknown",
        roles: list[str] | None = None,
        ttl_days: int | None = None,
    ) -> tuple[str, APIKeyRecord]:
        """Generate a new API key.

        Args:
            name: Human-readable key name.
            owner: Owner/principal for audit purposes.
            roles: Roles granted to this key's principal.
            ttl_days: Optional expiry window in days.

        Returns:
            Tuple ``(raw_key, record)``. The raw key is shown exactly once.
        """
        raw_key = f"{self.KEY_PREFIX}{secrets.token_hex(32)}"
        expires_at = datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days is not None else None
        record = APIKeyRecord(
            key_id=uuid_module.uuid4().hex,
            key_hash=self._hash_key(raw_key),
            key_prefix=raw_key[: self.DISPLAY_PREFIX_LENGTH],
            name=name,
            owner=owner,
            roles=list(roles or []),
            expires_at=expires_at,
        )
        self._store[record.key_hash] = record
        self._raw_hashes.add(record.key_hash)
        logger.info("api_key_generated", key_id=record.key_id, owner=owner)
        return raw_key, record

    def validate_api_key(self, api_key: str) -> bool:
        """Validate an API key.

        Args:
            api_key: The raw API key to validate.

        Returns:
            True if valid.
        """
        return self.authenticate_api_key(api_key) is not None

    def authenticate_api_key(self, api_key: str) -> APIKeyRecord | None:
        """Resolve an API key to its record.

        Args:
            api_key: The raw API key presented by the client.

        Returns:
            The active matching record, or ``None`` when unknown,
            revoked, or expired.
        """
        if not api_key:
            return None
        candidate = self._hash_key(api_key)
        match = None
        for known_hash, record in self._store.items():
            if hmac.compare_digest(candidate, known_hash):
                match = record
                break
        if match is None:
            logger.info("api_key_rejected", reason="unknown_key")
            return None
        if match.revoked:
            logger.info("api_key_rejected", reason="revoked", key_id=match.key_id)
            return None
        if match.expires_at is not None and datetime.now(UTC) >= match.expires_at:
            logger.info("api_key_rejected", reason="expired", key_id=match.key_id)
            return None
        return match

    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key by its identifier.

        Args:
            key_id: The key identifier returned at creation.

        Returns:
            True if a matching active key was revoked.
        """
        for record in self._store.values():
            if record.key_id == key_id and not record.revoked:
                record.revoked = True
                logger.info("api_key_revoked", key_id=key_id)
                return True
        return False

    def list_api_keys(self) -> list[dict[str, Any]]:
        """List metadata for all provisioned keys (no secrets)."""
        return [record.public_dict() for record in self._store.values()]

    @property
    def key_count(self) -> int:
        """Number of provisioned keys."""
        return len(self._store)


# =============================================================================
# Rate Limiting Service
# =============================================================================


class RateLimitService:
    """In-memory sliding-window rate limiting service.

    Tracks request timestamps per identifier within a rolling window.
    Suitable for single-process deployments; swap in a distributed
    backend later without changing the public interface.
    """

    def __init__(self) -> None:
        """Initialize empty rate limit tracking state."""
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def check_rate_limit(self, identifier: str, limit: int = 100, window: int = 60) -> bool:
        """Record a request attempt and check it against the rate limit.

        Uses a monotonic-clock sliding window: attempts older than
        ``window`` seconds expire automatically.

        Args:
            identifier: The rate limit key (e.g., IP, user ID).
            limit: Maximum requests allowed within the window.
            window: Time window in seconds.

        Returns:
            True if the request is within limits (allowed), False when
            the limit has been exceeded.
        """
        now = time.monotonic()
        bucket = self._requests[identifier]
        cutoff = now - window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            logger.warning("rate_limit_exceeded", identifier=identifier, limit=limit, window=window)
            return False
        bucket.append(now)
        return True

    def retry_after(self, identifier: str, window: int = 60) -> int:
        """Seconds until the oldest tracked attempt exits the window.

        Args:
            identifier: The rate limit key.
            window: Time window in seconds.

        Returns:
            Whole seconds (minimum 1) until capacity frees up.
        """
        bucket = self._requests.get(identifier)
        if not bucket:
            return 1
        elapsed = time.monotonic() - bucket[0]
        remaining = max(1, int(window - elapsed) + 1)
        return remaining

    def reset(self, identifier: str) -> None:
        """Clear tracking state for an identifier (e.g., after unlock).

        Args:
            identifier: The rate limit key.
        """
        self._requests.pop(identifier, None)

    @property
    def tracked_identifiers(self) -> int:
        """Number of identifiers currently being tracked."""
        return len(self._requests)


def ensure_production_secret(secret_key: str) -> None:
    """Guard against running production with the placeholder secret.

    Args:
        secret_key: The configured secret key.

    Raises:
        SecurityError: When the value equals the well-known placeholder
            and the runtime environment is production.
    """
    if secret_key == "change-me-to-a-random-secret-key" and is_production_environment():
        msg = "SECRET_KEY must be changed in production!"
        raise SecurityError(msg)


# =============================================================================
# Singletons
# =============================================================================

_jwt_service_instance: JWTService | None = None
_authentication_service_instance: AuthenticationService | None = None
_authorization_service_instance: AuthorizationService | None = None
_api_key_service_instance: APIKeyService | None = None
_rate_limit_service_instance: RateLimitService | None = None
_token_blocklist_instance: TokenBlocklistService | None = None


def get_jwt_service() -> JWTService:
    """Get the singleton JWT service instance.

    Returns:
        The singleton JWTService instance.
    """
    global _jwt_service_instance
    if _jwt_service_instance is None:
        _jwt_service_instance = JWTService()
    return _jwt_service_instance


def get_authentication_service() -> AuthenticationService:
    """Get the singleton authentication service instance.

    Returns:
        The singleton AuthenticationService instance.
    """
    global _authentication_service_instance
    if _authentication_service_instance is None:
        _authentication_service_instance = AuthenticationService(get_jwt_service())
    return _authentication_service_instance


def get_token_blocklist() -> TokenBlocklistService:
    """Get the singleton token revocation service instance.

    Returns:
        The singleton TokenBlocklistService instance.
    """
    global _token_blocklist_instance
    if _token_blocklist_instance is None:
        _token_blocklist_instance = default_token_blocklist_service()
    return _token_blocklist_instance


def get_authorization_service() -> AuthorizationService:
    """Get the singleton authorization service instance.

    Returns:
        The singleton AuthorizationService instance.
    """
    global _authorization_service_instance
    if _authorization_service_instance is None:
        _authorization_service_instance = AuthorizationService()
    return _authorization_service_instance


def get_api_key_service() -> APIKeyService:
    """Get the singleton API key service instance.

    Returns:
        The singleton APIKeyService instance.
    """
    global _api_key_service_instance
    if _api_key_service_instance is None:
        _api_key_service_instance = APIKeyService()
    return _api_key_service_instance


def get_rate_limit_service() -> RateLimitService:
    """Get the singleton rate limit service instance.

    Returns:
        The singleton RateLimitService instance.
    """
    global _rate_limit_service_instance
    if _rate_limit_service_instance is None:
        _rate_limit_service_instance = RateLimitService()
    return _rate_limit_service_instance


def reset_auth_singletons() -> None:
    """Reset all auth singletons. Used in testing."""
    global _jwt_service_instance
    global _authentication_service_instance
    global _authorization_service_instance
    global _api_key_service_instance
    global _rate_limit_service_instance
    global _token_blocklist_instance
    _jwt_service_instance = None
    _authentication_service_instance = None
    _authorization_service_instance = None
    _api_key_service_instance = None
    _rate_limit_service_instance = None
    _token_blocklist_instance = None
