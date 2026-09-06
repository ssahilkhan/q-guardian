"""Token revocation (blocklist) service for Q-Guardian.

JWT access and refresh tokens are stateless by design, so "logout" must
actively revoke a token by recording its ``jti`` until it would naturally
expire. Revocations are persisted to MongoDB with a TTL index, which makes
them survive process restarts.

When the backing store is unreachable the check fails OPEN (treated as
not-revoked) and a warning is logged; every token still has a hard
expiry, so the worst case is the token living out its natural lifetime
rather than being revocable forever.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import structlog

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection

logger = structlog.get_logger("security.token_blocklist")


@runtime_checkable
class TokenBlocklistRepository(Protocol):
    """Persistence interface for revoked token identifiers (``jti``s)."""

    async def ensure_indexes(self) -> None:
        """Create any required indexes (no-op where not applicable)."""
        ...

    async def add(self, jti: str, kind: str, expires_at: datetime) -> None:
        """Record a revoked token identifier with its natural expiry."""
        ...

    async def is_blocked(self, jti: str) -> bool:
        """Return True when the token identifier has been revoked."""
        ...


class MongoTokenBlocklistRepository:
    """MongoDB-backed blocklist.

    Documents are keyed by ``jti`` and carry the token's ``expires_at``;
    a TTL index removes them automatically once the token would have
    expired anyway.
    """

    def __init__(
        self,
        collection: AsyncIOMotorCollection[Any] | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Initialize the repository.

        Args:
            collection: Explicit Motor collection (mainly tests). When
                omitted, the collection named ``collection_name`` is
                resolved through the shared MongoDB client on every
                operation.
            collection_name: Target collection name. Defaults to the
                ``MONGODB_TOKEN_BLOCKLIST_COLLECTION`` setting.
        """
        self._explicit_collection = collection
        if collection is None:
            from q_guardian.config.settings import get_settings

            self._collection_name = (
                collection_name
                if collection_name is not None
                else get_settings().database.token_blocklist_collection
            )

    @property
    def collection(self) -> AsyncIOMotorCollection[Any]:
        """Return the backing Motor collection for the current connection."""
        if self._explicit_collection is not None:
            return self._explicit_collection
        from q_guardian.database.client import get_db_client

        return get_db_client().get_collection(self._collection_name)

    async def ensure_indexes(self) -> None:
        """Create the jti + TTL indexes (best-effort, idempotent)."""
        try:
            await self.collection.create_index(
                [("expires_at", 1)],
                name="expires_at_ttl",
                expireAfterSeconds=0,
            )
        except Exception as exc:
            logger.warning("blocklist_index_creation_failed", error=str(exc))

    async def add(self, jti: str, kind: str, expires_at: datetime) -> None:
        """Record a revoked token identifier.

        Raises:
            DatabaseError: If the write fails.
        """
        from pymongo.errors import PyMongoError

        from q_guardian.exceptions.base import DatabaseError

        try:
            await self.collection.update_one(
                {"_id": jti},
                {"$set": {"kind": kind, "expires_at": expires_at}},
                upsert=True,
            )
        except PyMongoError as exc:
            logger.error("blocklist_write_failed", error=str(exc))
            raise DatabaseError(
                message="Failed to persist token revocation",
                details={"operation": "block"},
            ) from exc

    async def is_blocked(self, jti: str) -> bool:
        """Return True when the token identifier has been revoked.

        Raises:
            DatabaseError: If the query fails.
        """
        from pymongo.errors import PyMongoError

        from q_guardian.exceptions.base import DatabaseError

        try:
            document = await self.collection.find_one({"_id": jti})
        except PyMongoError as exc:
            logger.error("blocklist_query_failed", error=str(exc))
            raise DatabaseError(
                message="Failed to read token revocation state",
                details={"operation": "check"},
            ) from exc
        return document is not None


class InMemoryTokenBlocklistRepository:
    """In-memory blocklist — TEST DOUBLE ONLY.

    Never wired into the production application, which must revoke tokens
    persistently.
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory blocklist."""
        self._records: dict[str, datetime] = {}

    async def ensure_indexes(self) -> None:
        """No indexes needed for an in-memory store."""

    async def add(self, jti: str, kind: str, expires_at: datetime) -> None:
        """Record a revoked token identifier."""
        self._records[jti] = expires_at

    async def is_blocked(self, jti: str) -> bool:
        """Return True when the token identifier has been revoked."""
        now = datetime.now(UTC)
        self._records = {jti: exp for jti, exp in self._records.items() if exp > now}
        return jti in self._records


class TokenBlocklistService:
    """Token revocation facade with fail-open semantics.

    All lookups are best-effort: if the backing store cannot be reached the
    identifier is treated as not revoked (a warning is logged) so the
    application keeps serving while the database is unavailable. Tokens
    remain bounded by their natural ``exp`` claims regardless.
    """

    def __init__(self, repository: TokenBlocklistRepository | None = None) -> None:
        """Initialize the service.

        Args:
            repository: Backing store. Defaults to the production
                (MongoDB) repository resolved lazily.
        """
        self._repository = repository

    @property
    def repository(self) -> TokenBlocklistRepository:
        """Return the backing repository (defaults to Mongo)."""
        if self._repository is None:
            self._repository = MongoTokenBlocklistRepository()
        return self._repository

    async def block_token(
        self,
        jti: str,
        expires_at: datetime,
        kind: str = "token",
    ) -> bool:
        """Revoke a token identifier until its natural expiry.

        Args:
            jti: The token's unique identifier.
            expires_at: When the token would naturally expire.
            kind: Human-readable token kind (access/refresh) for debugging.

        Returns:
            True when the revocation was persisted, False when the store
            was unreachable (revocation not durable).
        """
        if not jti:
            return False
        if expires_at <= datetime.now(UTC):
            return True
        try:
            await self.repository.add(jti, kind, expires_at)
            return True
        except Exception as exc:
            logger.warning("blocklist_unavailable", error=str(exc))
            return False

    async def is_token_blocked(self, jti: str) -> bool:
        """Return True when a token identifier is revoked (fail-open)."""
        if not jti:
            return False
        try:
            return await self.repository.is_blocked(jti)
        except Exception as exc:
            logger.warning("blocklist_check_unavailable", error=str(exc))
            return False


def default_token_blocklist_service() -> TokenBlocklistService:
    """Build the production blocklist service (MongoDB-backed)."""
    return TokenBlocklistService()
