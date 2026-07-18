"""Base event classes and handler types for Q-Guardian.

Defines the Event abstraction that all framework events inherit from,
and the EventHandler type used by the EventBus.
"""

from __future__ import annotations

from abc import ABC
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.utils.uuid_utils import generate_uuid

EventHandler = Callable[..., Awaitable[None]]


class Event(BaseModel, ABC):
    """Base class for all framework events.

    All events in the Q-Guardian framework inherit from this class.
    Events carry typed data between components through the EventBus.

    Attributes:
        id: Unique event identifier.
        event_type: The type name of the event.
        timestamp: When the event was created.
        source: The component that originated the event.
        data: Event payload data.
        metadata: Additional event metadata.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        frozen=False,
    )

    id: str = Field(default_factory=generate_uuid, description="Unique event ID")
    event_type: str = Field(description="Event type identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event creation timestamp",
    )
    source: str = Field(default="system", description="Event source component")
    data: dict[str, Any] = Field(default_factory=dict, description="Event payload")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Event metadata"
    )
    propagation_stopped: bool = Field(
        default=False, description="Flag to stop event propagation"
    )

    def stop_propagation(self) -> None:
        """Stop this event from being delivered to further handlers."""
        self.propagation_stopped = True
