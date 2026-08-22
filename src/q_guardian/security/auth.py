"""Security infrastructure for Q-Guardian.

Implements the framework's authentication and rate-limiting services:
- JWT token generation and validation (python-jose)
- Credential-based authentication
- Role-based access control primitives
- API key management (secure generation, hashed storage)
- Rate limiting (sliding window)

All secrets are sourced from application settings (environment/.env);
no credentials are hardcoded in this module.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field

from q_guardian.config.settings import get_settings
from q_guardian.exceptions.base import AuthenticationError
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("security.auth")

# =============================================================================
# JWT Service
# =============================================================================


class JWTService:
    """JWT token service backed by python-jose.

    Handles:
    - Access token generation and validation
    - Refresh token generation and validation
    - Token expiration enforcement

    Signing material is read from SecuritySettings (SECRET_KEY /
    JWT_ALGORITHM) and is never hardcoded here.
    """

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            secret_key: Optional explicit signing key. When omitted the
                key is resolved from application settings.
            algorithm: Optional explicit signing algorithm. When omitted
                the algorithm is resolved from application settings.
        """
        self._secret_key = secret_key
        self._algorithm = algorithm

    @property
    def _key(self) -> str:
        if self._secret_key is None:
            self._secret_key = get_settings().security.secret_key
        return self._secret_key

    @property
    def _alg(self) -> str:
        if self._algorithm is None:
            self._algorithm = get_settings().security.jwt_algorithm
        return self._algorithm

    async def create_access_token(self, payload: dict[str, Any], expires_minutes: int = 30) -> str:
        """Create a signed JWT access token.

        Args:
            payload: Token payload data. A ``sub`` claim identifies the
                principal.
            expires_minutes: Token lifetime in minutes.

        Returns:
            Encoded JWT string.

        Raises:
            AuthenticationError: If ``payload`` is missing a ``sub`` claim.
        """
        if not payload.get("sub"):
            msg = "JWT payload requires a 'sub' claim"
            raise AuthenticationError(msg)
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            **payload,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=expires_minutes),
            "jti": generate_uuid(),
        }
        return jwt.encode(claims, self._key, algorithm=self._alg)

    async def create_refresh_token(self, subject: str, expires_days: int | None = None) -> str:
        """Create a signed JWT refresh token.

        Args:
            subject: The principal identifier.
            expires_days: Optional lifetime override in days. Defaults to
                the configured refresh expiration.

        Returns:
            Encoded JWT string.
        """
        if expires_days is None:
            expires_days = get_settings().security.jwt_refresh_expiration_days
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            "sub": subject,
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=expires_days),
            "jti": generate_uuid(),
        }
        return jwt.encode(claims, self._key, algorithm=self._alg)

    async def verify_token(self, token: str, expected_type: str | None = None) -> dict[str, Any]:
        """Verify and decode a JWT token.

        Args:
            token: The JWT string to verify.
            expected_type: Optional token type assertion ("access" or
                "refresh"). When provided, mismatched tokens are rejected.

        Returns:
            Decoded token payload.

        Raises:
            AuthenticationError: If the token is expired, malformed,
                signed with an untrusted key, or of the wrong type.
        """
        try:
            claims = jwt.decode(token, self._key, algorithms=[self._alg])
        except ExpiredSignatureError as exc:
            msg = "Token has expired"
            raise AuthenticationError(msg) from exc
        except JWTError as exc:
            msg = "Invalid authentication token"
            raise AuthenticationError(msg) from exc

        if expected_type is not None and claims.get("type") != expected_type:
            msg = f"Invalid token type: expected '{expected_type}'"
            raise AuthenticationError(msg)
        return claims


# =============================================================================
# Authentication Service
# =============================================================================


class AuthenticationService:
    """Credential-based authentication service.

    Validates credentials against the admin identity configured through
    environment settings (ADMIN_USERNAME / ADMIN_PASSWORD). Password
    comparison uses constant-time equality to prevent timing attacks.
    """

    async def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        """Authenticate a user with credentials.

        Args:
            username: The username.
            password: The password.

        Returns:
            Principal dictionary (``sub``, ``roles``, ``auth_method``)
            on success, or None when credentials are invalid.
        """
        security = get_settings().security
        username_ok = hmac.compare_digest(
            username.encode("utf-8"), security.admin_username.encode("utf-8")
        )
        password_ok = hmac.compare_digest(
            password.encode("utf-8"), security.admin_password.encode("utf-8")
        )
        if not (username_ok and password_ok):
            logger.warning("authentication_failed", username=username)
            return None
        return {
            "sub": security.admin_username,
            "roles": ["admin"],
            "auth_method": "credentials",
        }


# =============================================================================
# Authorization Service
# =============================================================================


class AuthorizationService:
    """Role-based authorization service.

    Checks whether a principal's roles satisfy the permission
    requirements for an action on a resource. The default policy grants
    the ``admin`` role full access.
    """

    #: Actions granted per role. Admin implicitly holds every action.
    _ROLE_PERMISSIONS: dict[str, set[str]] = {
        "service": {"scan", "history:read"},
    }

    async def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        """Check if a user has permission for an action on a resource.

        Args:
            user_id: The user identifier.
            resource: The resource identifier.
            action: The action to check.

        Returns:
            True if authorized.
        """
        del resource  # Resource-level scoping reserved for future use.
        roles = self._roles_for(user_id)
        if "admin" in roles:
            return True
        granted = self._ROLE_PERMISSIONS.get(action, set())
        return bool(roles & granted)

    def _roles_for(self, user_id: str) -> set[str]:
        """Resolve roles for a principal id.

        Args:
            user_id: Principal identifier; the configured admin maps to
                the ``admin`` role.

        Returns:
            Set of role names.
        """
        if user_id == get_settings().security.admin_username:
            return {"admin"}
        return set()


# =============================================================================
# API Key Management
# =============================================================================


class APIKeyRecord(BaseModel):
    """Stored representation of an API key.

    The raw key material is never persisted — only its SHA-256 hash and
    a short display prefix used for identification in logs and listings.
    """

    model_config = ConfigDict(populate_by_name=True)

    key_id: str = Field(default_factory=generate_uuid, description="Public key identifier")
    name: str = Field(description="Human-readable key name")
    key_hash: str = Field(description="SHA-256 hash of the raw key")
    prefix: str = Field(description="First characters of the raw key for identification")
    active: bool = Field(default=True, description="Whether the key may authenticate")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )
    expires_at: datetime | None = Field(default=None, description="Optional expiration timestamp")
    last_used_at: datetime | None = Field(default=None, description="Last successful use")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize without sensitive material.

        Returns:
            Dictionary safe for API responses and logs.
        """
        data = self.model_dump(exclude={"key_hash"})
        return data


class APIKeyService:
    """API key generation, validation, and lifecycle management.

    Keys are generated with ``secrets.token_urlsafe`` (256 bits of
    entropy), stored only as SHA-256 hashes, and can be deactivated or
    expired. Raw key material is returned exactly once at creation.
    """

    #: Length of the identification prefix stored alongside the hash.
    PREFIX_LENGTH = 8

    def __init__(self) -> None:
        """Initialize the service with an empty in-memory key store."""
        # key_hash -> record. Swap for a repository-backed store when
        # multi-process persistence is required.
        self._keys: dict[str, APIKeyRecord] = {}

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """Hash a raw API key with SHA-256."""
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async def generate_api_key(
        self,
        name: str,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[APIKeyRecord, str]:
        """Generate a new API key.

        Args:
            name: Human-readable key name.
            expires_at: Optional expiration timestamp.
            metadata: Optional additional metadata.

        Returns:
            Tuple of (stored record, raw key). The raw key is shown
            only once and cannot be recovered later.
        """
        raw_key = f"qg_{secrets.token_urlsafe(32)}"
        record = APIKeyRecord(
            name=name,
            key_hash=self._hash_key(raw_key),
            prefix=raw_key[: self.PREFIX_LENGTH],
            expires_at=expires_at,
            metadata=metadata or {},
        )
        self._keys[record.key_hash] = record
        logger.info("api_key_created", key_id=record.key_id, prefix=record.prefix)
        return record, raw_key

    def _resolve(self, api_key: str) -> APIKeyRecord | None:
        """Resolve a raw key to its stored record, enforcing validity."""
        record = self._keys.get(self._hash_key(api_key))
        if record is None:
            return None
        if not record.active:
            return None
        if record.expires_at is not None and datetime.now(UTC) >= record.expires_at:
            return None
        return record

    async def validate_api_key(self, api_key: str) -> bool:
        """Validate an API key.

        Args:
            api_key: The raw API key to validate.

        Returns:
            True if the key exists, is active, and is unexpired.
        """
        return await self.authenticate_api_key(api_key) is not None

    async def authenticate_api_key(self, api_key: str) -> APIKeyRecord | None:
        """Authenticate a raw API key and return its record.

        Args:
            api_key: The raw API key.

        Returns:
            The active record on success, None otherwise.
        """
        record = self._resolve(api_key)
        if record is not None:
            record.last_used_at = datetime.now(UTC)
        return record

    async def deactivate_api_key(self, key_id: str) -> bool:
        """Deactivate (revoke) an API key by its public id.

        Args:
            key_id: The public key identifier.

        Returns:
            True if the key was found and deactivated.
        """
        for record in self._keys.values():
            if record.key_id == key_id:
                record.active = False
                logger.info("api_key_deactivated", key_id=key_id)
                return True
        return False

    async def activate_api_key(self, key_id: str) -> bool:
        """Reactivate a previously deactivated API key.

        Args:
            key_id: The public key identifier.

        Returns:
            True if the key was found and activated.
        """
        for record in self._keys.values():
            if record.key_id == key_id:
                record.active = True
                logger.info("api_key_activated", key_id=key_id)
                return True
        return False

    async def list_api_keys(self, include_inactive: bool = True) -> list[APIKeyRecord]:
        """List stored API keys.

        Args:
            include_inactive: Whether to include deactivated keys.

        Returns:
            List of records (hashes excluded by callers via
            ``to_public_dict``).
        """
        records = list(self._keys.values())
        if not include_inactive:
            records = [r for r in records if r.active]
        return records


# =============================================================================
# Rate Limiting
# =============================================================================


class RateLimitService:
    """In-process sliding-window rate limiter.

    Tracks request timestamps per identifier and admits requests while
    they remain within ``limit`` per ``window`` seconds. State is kept
    in memory; deploy behind a shared limiter for multi-process setups.
    """

    def __init__(self, max_identifiers: int = 10_000) -> None:
        """Initialize the limiter.

        Args:
            max_identifiers: Maximum tracked identifiers to bound memory;
                oldest entries are evicted beyond this cap.
        """
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._max_identifiers = max_identifiers

    def _prune(self, key: str, window: int, now: float) -> deque[float]:
        """Drop timestamps outside the window for one identifier."""
        hits = self._hits[key]
        cutoff = now - window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    async def check_rate_limit(self, identifier: str, limit: int = 100, window: int = 60) -> bool:
        """Check whether a request is within the rate limit.

        Records the request when admitted.

        Args:
            identifier: The rate limit key (e.g., client IP or user ID).
            limit: Maximum requests allowed within the window.
            window: Time window in seconds.

        Returns:
            True if within limits, False when the limit is exceeded.
        """
        if len(self._hits) > self._max_identifiers:
            self._evict_stale()
        now = time.monotonic()
        hits = self._prune(identifier, window, now)
        if len(hits) >= limit:
            logger.debug("rate_limit_exceeded", identifier=identifier, limit=limit)
            return False
        hits.append(now)
        return True

    def _evict_stale(self) -> None:
        """Evict identifiers with no recent activity to bound memory."""
        if not self._hits:
            return
        oldest = min(self._hits, key=lambda k: self._hits[k][0] if self._hits[k] else float("inf"))
        del self._hits[oldest]

    def reset(self, identifier: str | None = None) -> None:
        """Clear tracking state. Used in testing.

        Args:
            identifier: Clear only this identifier; None clears all.
        """
        if identifier is None:
            self._hits.clear()
        else:
            self._hits.pop(identifier, None)
