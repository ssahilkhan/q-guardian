"""Base models for Q-Guardian.

Provides abstract base classes that all domain models should inherit from.
Enforces consistent model structure across all future modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.utils.datetime_utils import get_utc_now
from q_guardian.utils.uuid_utils import generate_uuid

if TYPE_CHECKING:
    from datetime import datetime


class TimestampMixin(BaseModel):
    """Mixin that adds created_at and updated_at timestamps."""

    created_at: datetime = Field(
        default_factory=get_utc_now,
        description="Timestamp when the record was created",
    )
    updated_at: datetime = Field(
        default_factory=get_utc_now,
        description="Timestamp when the record was last updated",
    )


class BaseModelConfig(BaseModel):
    """Base model with common Pydantic configuration."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=True,
        frozen=False,
    )


class BaseDocument(BaseModelConfig, TimestampMixin):
    """Base document model for MongoDB documents.

    Provides common fields and configuration for all MongoDB documents.
    """

    id: str = Field(
        default_factory=generate_uuid,
        description="Unique document identifier",
        alias="_id",
    )

    def model_dump_mongo(self) -> dict[str, Any]:
        """Dump model for MongoDB storage.

        Uses '_id' as the primary key field.

        Returns:
            Dictionary suitable for MongoDB insertion.
        """
        return self.model_dump(by_alias=True)


class AbstractEntity(ABC):
    """Abstract base class for domain entities.

    Defines the interface that all domain entities must implement.
    """

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert entity to dictionary representation.

        Returns:
            Dictionary representation of the entity.
        """

    @abstractmethod
    def get_id(self) -> str:
        """Get the entity's unique identifier.

        Returns:
            The entity ID string.
        """
