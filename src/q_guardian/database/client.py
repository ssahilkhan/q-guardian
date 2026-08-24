"""MongoDB async client manager for Q-Guardian.

Uses Motor (async MongoDB driver) with connection pooling,
lifecycle management, and health checking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from q_guardian.config.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from motor.motor_asyncio import AsyncIOMotorCollection

logger = structlog.get_logger("database.client")


def _redact_url(url: str) -> str:
    """Return a URL with any embedded credentials replaced.

    Args:
        url: The raw connection URL.

    Returns:
        A log-safe URL; credentials never reach logs or errors.
    """
    if "://" not in url:
        return "<redacted>"
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        _, host = rest.rsplit("@", 1)
        return f"{scheme}://***@{host}"
    return f"{scheme}://{rest}"


class MongoDBClient:
    """Async MongoDB client wrapper with connection pooling.

    Manages the lifecycle of a Motor async client and provides
    convenient access to databases and collections.
    """

    def __init__(self) -> None:
        """Initialize the MongoDB client from application settings."""
        self._client: AsyncIOMotorClient[Any] | None = None
        self._database: AsyncIOMotorDatabase[Any] | None = None
        self._settings = get_settings()

    async def connect(self) -> None:
        """Establish connection to MongoDB."""
        if self._client is not None:
            logger.info("mongodb_already_connected")
            return

        logger.info(
            "mongodb_connecting",
            url=_redact_url(self._settings.database.url),
            database=self._settings.database.database,
        )

        self._client = AsyncIOMotorClient(
            self._settings.database.url,
            **self._settings.database.client_kwargs,
        )
        self._database = self._client[self._settings.database.database]

        await self._client.admin.command("ping")
        logger.info("mongodb_connected", database=self._settings.database.database)

    async def disconnect(self) -> None:
        """Close the MongoDB connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._database = None
            logger.info("mongodb_disconnected")

    @property
    def client(self) -> AsyncIOMotorClient[Any]:
        """Return the raw Motor client.

        Raises:
            RuntimeError: If the client is not connected.
        """
        if self._client is None:
            msg = "MongoDB client is not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._client

    @property
    def database(self) -> AsyncIOMotorDatabase[Any]:
        """Return the application database instance.

        Raises:
            RuntimeError: If the client is not connected.
        """
        if self._database is None:
            msg = "MongoDB client is not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._database

    def get_collection(self, name: str) -> AsyncIOMotorCollection[Any]:
        """Get a collection by name from the application database.

        Args:
            name: The collection name.

        Returns:
            The Motor collection object.
        """
        return self.database[name]

    async def ping(self) -> bool:
        """Ping the MongoDB server to verify connectivity.

        Returns:
            True if the server responds, False otherwise.
        """
        try:
            await self.client.admin.command("ping")
            return True
        except Exception:
            return False


_client_instance: MongoDBClient | None = None


def get_db_client() -> MongoDBClient:
    """Get or create the singleton MongoDB client instance.

    Returns:
        The singleton MongoDBClient instance.
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = MongoDBClient()
    return _client_instance


async def get_database() -> AsyncGenerator[AsyncIOMotorDatabase[Any], None]:
    """FastAPI dependency that provides the database instance.

    Yields:
        The application database.
    """
    client = get_db_client()
    yield client.database
