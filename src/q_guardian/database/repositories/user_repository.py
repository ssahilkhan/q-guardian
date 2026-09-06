"""Persistent user account repository.

Stores registered user accounts (username, bcrypt password hash, roles and
bookkeeping timestamps) in MongoDB. Mirrors the analysis-history repository
pattern: a lazy, connect-time-safe design that resolves the collection
through the shared MongoDB client on every operation, plus an in-memory
test double that is never wired into the production application.

Only bcrypt hashes are ever persisted; plaintext passwords never touch
storage or logs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import structlog

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection

logger = structlog.get_logger("database.repositories.user_repository")

#: Fields written internally for bookkeeping but never returned to callers.
_INTERNAL_FIELDS = ("_id",)

ALLOWED_ROLES = frozenset({"admin", "analyst", "service"})


@runtime_checkable
class UserRepository(Protocol):
    """Persistence interface for registered user accounts."""

    async def ensure_indexes(self) -> None:
        """Create supporting indexes (best-effort, idempotent)."""
        ...

    async def create_user(
        self,
        username: str,
        password_hash: str,
        roles: list[str],
    ) -> dict[str, Any] | None:
        """Persist a new user; return the stored record or None on duplicate."""
        ...

    async def get_by_username(self, username: str) -> dict[str, Any] | None:
        """Return the stored user record (including ``password_hash``), or None."""
        ...

    async def find_by_username(self, username: str) -> dict[str, Any] | None:
        """Return a public view of a stored user record, or None."""
        ...

    async def delete_user(self, username: str) -> bool:
        """Delete a user account; return True when a record was removed."""
        ...


def _strip_internal(document: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the document without internal bookkeeping fields."""
    return {key: value for key, value in document.items() if key not in _INTERNAL_FIELDS}


def _public_view(document: dict[str, Any]) -> dict[str, Any]:
    """Return a safe-for-display record (never includes the password hash)."""
    return {
        key: value for key, value in _strip_internal(document).items() if key != "password_hash"
    }


class MongoUserRepository:
    """MongoDB-backed user account repository.

    The ``username`` field carries a unique index so concurrent registration
    attempts for the same account cannot silently overwrite each other.
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
                operation, keeping the repository valid across client
                reconnects.
            collection_name: Target collection name. Defaults to the
                ``MONGODB_USER_COLLECTION`` setting.
        """
        self._explicit_collection = collection
        if collection is None:
            from q_guardian.config.settings import get_settings

            self._collection_name = (
                collection_name
                if collection_name is not None
                else get_settings().database.user_collection
            )

    @property
    def collection(self) -> AsyncIOMotorCollection[Any]:
        """Return the backing Motor collection for the current connection."""
        if self._explicit_collection is not None:
            return self._explicit_collection
        from q_guardian.database.client import get_db_client

        return get_db_client().get_collection(self._collection_name)

    async def ensure_indexes(self) -> None:
        """Create the unique username index (best-effort, idempotent)."""
        try:
            await self.collection.create_index(
                [("username", 1)],
                name="username_unique",
                unique=True,
            )
        except Exception as exc:
            logger.warning("user_index_creation_failed", error=str(exc))

    async def create_user(
        self,
        username: str,
        password_hash: str,
        roles: list[str],
    ) -> dict[str, Any] | None:
        """Persist a new user account.

        Returns:
            The stored record on success, or ``None`` when the username is
            already taken (unique index duplicate).

        Raises:
            DatabaseError: If the write fails for a non-duplicate reason.
        """
        from pymongo.errors import DuplicateKeyError, PyMongoError

        from q_guardian.exceptions.base import DatabaseError

        now = datetime.now(UTC)
        document = {
            "username": username,
            "password_hash": password_hash,
            "roles": [r for r in roles if r in ALLOWED_ROLES] or ["analyst"],
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
        }
        try:
            await self.collection.insert_one(document)
        except DuplicateKeyError:
            logger.info("user_duplicate_registration", username=username)
            return None
        except PyMongoError as exc:
            logger.error("user_insert_failed", username=username, error=str(exc))
            raise DatabaseError(
                message="Failed to persist user account",
                details={"operation": "insert"},
            ) from exc
        return dict(document)

    async def get_by_username(self, username: str) -> dict[str, Any] | None:
        """Return the stored record (including ``password_hash``), or None.

        Raises:
            DatabaseError: If the query fails.
        """
        from pymongo.errors import PyMongoError

        from q_guardian.exceptions.base import DatabaseError

        try:
            document = await self.collection.find_one(
                {"username": username},
                dict.fromkeys(_INTERNAL_FIELDS, False),
            )
        except PyMongoError as exc:
            logger.error("user_query_failed", username=username, error=str(exc))
            raise DatabaseError(
                message="Failed to load user account",
                details={"operation": "get"},
            ) from exc
        return _strip_internal(document) if document is not None else None

    async def find_by_username(self, username: str) -> dict[str, Any] | None:
        """Return a public view of a stored user record, or None.

        Raises:
            DatabaseError: If the query fails.
        """
        record = await self.get_by_username(username)
        return _public_view(record) if record is not None else None

    async def delete_user(self, username: str) -> bool:
        """Delete a user account; return True when a record was removed.

        Raises:
            DatabaseError: If the delete fails.
        """
        from pymongo.errors import PyMongoError

        from q_guardian.exceptions.base import DatabaseError

        try:
            result = await self.collection.delete_one({"username": username})
        except PyMongoError as exc:
            logger.error("user_delete_failed", username=username, error=str(exc))
            raise DatabaseError(
                message="Failed to delete user account",
                details={"operation": "delete"},
            ) from exc
        return result.deleted_count == 1


class InMemoryUserRepository:
    """In-memory user store — TEST DOUBLE ONLY.

    Implements the same interface with set semantics so unit and integration
    tests can exercise registration, deduplication and authentication
    without MongoDB. This class must NEVER be wired into the production
    application: Phase 4 requires durable, restart-surviving storage.
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory store."""
        self._records: dict[str, dict[str, Any]] = {}

    async def ensure_indexes(self) -> None:
        """No-op: an in-memory store needs no indexes."""
        return None

    async def create_user(
        self,
        username: str,
        password_hash: str,
        roles: list[str],
    ) -> dict[str, Any] | None:
        """Store a new user, or return None when the username is taken."""
        if username in self._records:
            return None
        now = datetime.now(UTC)
        record = {
            "username": username,
            "password_hash": password_hash,
            "roles": [r for r in roles if r in ALLOWED_ROLES] or ["analyst"],
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
        }
        self._records[username] = record
        return dict(record)

    async def get_by_username(self, username: str) -> dict[str, Any] | None:
        """Return a copy of the stored record, or None."""
        record = self._records.get(username)
        return dict(record) if record is not None else None

    async def find_by_username(self, username: str) -> dict[str, Any] | None:
        """Return a public view of the stored record, or None."""
        record = await self.get_by_username(username)
        return _public_view(record) if record is not None else None

    async def delete_user(self, username: str) -> bool:
        """Delete a user account; return True when a record was removed."""
        return self._records.pop(username, None) is not None


def build_default_user_repository() -> UserRepository:
    """Build the production user repository (MongoDB-backed).

    Returns:
        A repository persisting to the configured MongoDB user collection.
    """
    return MongoUserRepository()
