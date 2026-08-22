"""Analysis scan history repository.

Replaces the previous in-memory ``deque`` history with a persistent
MongoDB-backed store. Records are the JSON-safe analysis payloads
produced by :class:`q_guardian.ml.plugin.ThreatAnalysisPlugin`.

Ordering contract (preserved from the deque implementation): the most
recent record comes first, and at most :data:`MAX_HISTORY` records are
retained/returned.

An internal ``created_at`` timestamp is stored alongside each record to
provide stable sort order across process restarts; it is projected out
of every read so documents round-trip exactly as they were handed in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import structlog

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection

logger = structlog.get_logger("database.repositories.analysis_history")

#: Maximum number of history entries retained and returned (mirrors the
#: previous ``deque(maxlen=...)`` bound).
MAX_HISTORY = 200

#: Fields written internally for ordering/metadata but never returned.
_INTERNAL_FIELDS = ("_id", "created_at")


@runtime_checkable
class AnalysisHistoryRepository(Protocol):
    """Persistence interface for the bounded analysis scan history."""

    async def ensure_indexes(self) -> None:
        """Create supporting indexes (best-effort, idempotent)."""
        ...

    async def add(self, record: dict[str, Any]) -> None:
        """Persist a single analysis result (newest entry)."""
        ...

    async def list_recent(self) -> list[dict[str, Any]]:
        """Return up to MAX_HISTORY records, most recent first."""
        ...

    async def get_by_id(self, analysis_id: str) -> dict[str, Any] | None:
        """Return a single record by its analysis ID, or None."""
        ...


def _strip_internal(document: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the document without internal bookkeeping fields."""
    return {key: value for key, value in document.items() if key not in _INTERNAL_FIELDS}


class MongoAnalysisHistoryRepository:
    """MongoDB-backed analysis history repository.

    The collection is resolved lazily through the shared
    :class:`~q_guardian.database.client.MongoDBClient` singleton so this
    object can be constructed before the application lifespan has
    connected to MongoDB (e.g., at module import time).
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
                ``MONGODB_HISTORY_COLLECTION`` setting.
        """
        self._explicit_collection = collection
        if collection is None:
            from q_guardian.config.settings import get_settings

            self._collection_name = (
                collection_name
                if collection_name is not None
                else get_settings().database.history_collection
            )

    @property
    def collection(self) -> AsyncIOMotorCollection[Any]:
        """Return the backing Motor collection for the current connection."""
        if self._explicit_collection is not None:
            return self._explicit_collection
        from q_guardian.database.client import get_db_client

        return get_db_client().get_collection(self._collection_name)

    async def ensure_indexes(self) -> None:
        """Create supporting indexes (best-effort, idempotent).

        Called during application startup; failures are logged and do
        not prevent startup because queries remain correct without the
        index, just slower.
        """
        try:
            await self.collection.create_index(
                [("created_at", -1), ("_id", -1)], name="created_at_desc"
            )
        except Exception as exc:
            logger.warning("history_index_creation_failed", error=str(exc))

    async def add(self, record: dict[str, Any]) -> None:
        """Persist one analysis result.

        Args:
            record: The JSON-safe analysis payload produced by the scan
                pipeline.

        Raises:
            DatabaseError: If the write fails. Callers decide how to
                surface the failure — production never falls back to an
                in-memory store.
        """
        from pymongo.errors import PyMongoError

        from q_guardian.exceptions.base import DatabaseError

        document = {**record, "created_at": datetime.now(UTC)}
        try:
            await self.collection.insert_one(document)
        except PyMongoError as exc:
            logger.error("history_insert_failed", error=str(exc))
            raise DatabaseError(
                message="Failed to persist analysis history",
                details={"operation": "insert"},
            ) from exc

    async def list_recent(self) -> list[dict[str, Any]]:
        """Return up to MAX_HISTORY records, most recent first.

        Ordering uses ``created_at`` descending with ``_id`` descending
        as tiebreaker, which reproduces the previous newest-first deque
        behavior across restarts.

        Raises:
            DatabaseError: If the query fails.
        """
        from pymongo.errors import PyMongoError

        from q_guardian.exceptions.base import DatabaseError

        try:
            cursor = (
                self.collection.find({}, dict.fromkeys(_INTERNAL_FIELDS, False))
                .sort([("created_at", -1), ("_id", -1)])
                .limit(MAX_HISTORY)
            )
            documents = await cursor.to_list(length=MAX_HISTORY)
        except PyMongoError as exc:
            logger.error("history_query_failed", error=str(exc))
            raise DatabaseError(
                message="Failed to load analysis history",
                details={"operation": "list"},
            ) from exc
        return [_strip_internal(doc) for doc in documents]

    async def get_by_id(self, analysis_id: str) -> dict[str, Any] | None:
        """Return one record by analysis ID, or None when unknown.

        Raises:
            DatabaseError: If the query fails.
        """
        from pymongo.errors import PyMongoError

        from q_guardian.exceptions.base import DatabaseError

        try:
            document = await self.collection.find_one(
                {"analysis_id": analysis_id},
                dict.fromkeys(_INTERNAL_FIELDS, False),
            )
        except PyMongoError as exc:
            logger.error("history_get_failed", error=str(exc))
            raise DatabaseError(
                message="Failed to load analysis record",
                details={"operation": "get"},
            ) from exc
        return _strip_internal(document) if document is not None else None


class InMemoryAnalysisHistoryRepository:
    """Bounded in-memory history — TEST DOUBLE ONLY.

    Replicates the original ``deque(maxlen=MAX_HISTORY)`` semantics so
    unit tests can exercise service behavior without MongoDB. This class
    must NEVER be wired into the production application: Phase 3's goal
    is durable history.
    """

    def __init__(self, history_limit: int = MAX_HISTORY) -> None:
        """Initialize an empty bounded store.

        Args:
            history_limit: Maximum number of retained records.
        """
        self._records: list[dict[str, Any]] = []
        self._history_limit = history_limit

    async def ensure_indexes(self) -> None:
        """No-op: an in-memory store needs no indexes."""
        return None

    async def add(self, record: dict[str, Any]) -> None:
        """Store a record, evicting the oldest beyond the limit."""
        self._records.insert(0, dict(record))
        del self._records[self._history_limit :]

    async def list_recent(self) -> list[dict[str, Any]]:
        """Return the bounded history, most recent first."""
        return [dict(record) for record in self._records]

    async def get_by_id(self, analysis_id: str) -> dict[str, Any] | None:
        """Return one record by analysis ID, or None."""
        return next(
            (dict(r) for r in self._records if r.get("analysis_id") == analysis_id),
            None,
        )


def build_default_history_repository() -> AnalysisHistoryRepository:
    """Build the production history repository (MongoDB-backed).

    Returns:
        A repository persisting to the configured MongoDB collection.
    """
    return MongoAnalysisHistoryRepository()
