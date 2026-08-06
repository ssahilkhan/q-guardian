"""Base repository interface for Q-Guardian.

Provides the abstract repository pattern that all data access
layers must implement. Supports both MongoDB and future data stores.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

T = TypeVar("T")


class BaseRepository[T](ABC):
    """Abstract base repository defining CRUD operations.

    All repository implementations must inherit from this class
    and implement the abstract methods.

    Type Parameters:
        T: The domain model type this repository manages.
    """

    @abstractmethod
    async def find_by_id(self, entity_id: str) -> T | None:
        """Find a single entity by its ID.

        Args:
            entity_id: The entity identifier.

        Returns:
            The entity if found, None otherwise.
        """

    @abstractmethod
    async def find_many(
        self,
        filters: dict[str, Any] | None = None,
        skip: int = 0,
        limit: int = 100,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[T]:
        """Find multiple entities matching the given filters.

        Args:
            filters: MongoDB-style filter dictionary.
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            sort: List of (field, direction) tuples for sorting.

        Returns:
            List of matching entities.
        """

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create a new entity.

        Args:
            entity: The entity to create.

        Returns:
            The created entity.
        """

    @abstractmethod
    async def update(self, entity_id: str, data: dict[str, Any]) -> T | None:
        """Update an existing entity.

        Args:
            entity_id: The entity identifier.
            data: Fields to update.

        Returns:
            The updated entity, or None if not found.
        """

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """Delete an entity by ID.

        Args:
            entity_id: The entity identifier.

        Returns:
            True if deleted, False if not found.
        """

    @abstractmethod
    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count entities matching the given filters.

        Args:
            filters: MongoDB-style filter dictionary.

        Returns:
            The count of matching entities.
        """

    @abstractmethod
    async def exists(self, entity_id: str) -> bool:
        """Check if an entity exists by ID.

        Args:
            entity_id: The entity identifier.

        Returns:
            True if the entity exists.
        """
