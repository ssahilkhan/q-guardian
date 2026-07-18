"""Base service interface for Q-Guardian.

Provides the abstract service layer pattern that all business
logic services must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class BaseService(ABC, Generic[T]):
    """Abstract base service defining business operation contracts.

    All service implementations must inherit from this class
    and implement the abstract methods.

    Type Parameters:
        T: The domain model type this service manages.
    """

    @abstractmethod
    async def get_by_id(self, id: str) -> T | None:
        """Retrieve an entity by its ID.

        Args:
            id: The entity identifier.

        Returns:
            The entity if found, None otherwise.
        """

    @abstractmethod
    async def get_all(
        self,
        filters: dict[str, Any] | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[T]:
        """Retrieve multiple entities.

        Args:
            filters: Filter criteria.
            skip: Pagination offset.
            limit: Maximum results.

        Returns:
            List of matching entities.
        """

    @abstractmethod
    async def create(self, data: dict[str, Any]) -> T:
        """Create a new entity.

        Args:
            data: Entity data.

        Returns:
            The created entity.
        """

    @abstractmethod
    async def update(self, id: str, data: dict[str, Any]) -> T | None:
        """Update an existing entity.

        Args:
            id: The entity identifier.
            data: Fields to update.

        Returns:
            The updated entity, or None if not found.
        """

    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete an entity.

        Args:
            id: The entity identifier.

        Returns:
            True if deleted successfully.
        """
