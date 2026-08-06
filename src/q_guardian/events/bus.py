"""Asynchronous event bus for Q-Guardian.

Provides a publish/subscribe event system that enables loose coupling
between framework components. Supports typed events, wildcard
subscriptions, and handler priority ordering.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import structlog

from q_guardian.events.base import Event, EventHandler

logger = structlog.get_logger("events.bus")

WILDCARD = "*"


@dataclass
class _Subscription:
    """Internal subscription record."""

    event_type: str
    handler: EventHandler
    subscription_id: int
    priority: int = 0


class EventBus:
    """Asynchronous publish/subscribe event bus.

    Enables loose coupling between components by allowing them to
    communicate through events. Handlers can subscribe to specific
    event types or use '*' to receive all events.

    Example::

        bus = EventBus()
        await bus.subscribe("threat.detected", my_handler)
        await bus.publish(ThreatDetected(data={"severity": "high"}))
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, list[_Subscription]] = {}
        self._subscription_map: dict[int, _Subscription] = {}
        self._next_id: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        priority: int = 0,
    ) -> int:
        """Subscribe a handler to an event type.

        Args:
            event_type: The event type to subscribe to, or '*' for all events.
            handler: The async callable to invoke when the event fires.
            priority: Handler execution priority (lower = earlier).

        Returns:
            A subscription ID for later unsubscribe.
        """
        async with self._lock:
            self._next_id += 1
            sub_id = self._next_id

            subscription = _Subscription(
                event_type=event_type,
                handler=handler,
                subscription_id=sub_id,
                priority=priority,
            )

            if event_type not in self._subscriptions:
                self._subscriptions[event_type] = []
            self._subscriptions[event_type].append(subscription)
            self._subscriptions[event_type].sort(key=lambda s: s.priority)
            self._subscription_map[sub_id] = subscription

            logger.debug(
                "event_subscribed",
                event_type=event_type,
                subscription_id=sub_id,
                priority=priority,
            )
            return sub_id

    async def unsubscribe(self, subscription_id: int) -> bool:
        """Remove a subscription by its ID.

        Args:
            subscription_id: The ID returned by subscribe().

        Returns:
            True if the subscription was found and removed.
        """
        async with self._lock:
            sub = self._subscription_map.pop(subscription_id, None)
            if sub is None:
                return False

            subs = self._subscriptions.get(sub.event_type, [])
            self._subscriptions[sub.event_type] = [
                s for s in subs if s.subscription_id != subscription_id
            ]

            logger.debug(
                "event_unsubscribed",
                event_type=sub.event_type,
                subscription_id=subscription_id,
            )
            return True

    async def publish(self, event: Event) -> Event:
        """Publish an event to all matching subscribers.

        Specific handlers execute before wildcard handlers. If a handler
        raises an exception, it is logged and does not prevent other
        handlers from executing. If event.propagation_stopped is set,
        no further handlers are called.

        Args:
            event: The event to publish.

        Returns:
            The event after all handlers have processed it.
        """
        specific_subs = list(self._subscriptions.get(event.event_type, []))
        wildcard_subs = list(self._subscriptions.get(WILDCARD, []))
        all_subs = specific_subs + wildcard_subs

        for sub in all_subs:
            if event.propagation_stopped:
                break
            try:
                await sub.handler(event)
            except Exception:
                logger.error(
                    "event_handler_error",
                    event_type=event.event_type,
                    subscription_id=sub.subscription_id,
                    exc_info=True,
                )

        return event

    async def broadcast(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        source: str = "system",
    ) -> Event:
        """Create and publish an event by type name.

        Convenience method that creates an anonymous Event subclass
        instance and publishes it.

        Args:
            event_type: The event type string.
            data: Event payload data.
            source: The component publishing the event.

        Returns:
            The published Event instance.
        """
        event = _GenericEvent(
            event_type=event_type,
            data=data or {},
            source=source,
        )
        await self.publish(event)
        return event

    def subscriber_count(self, event_type: str | None = None) -> int:
        """Count subscribers for a specific event type or all.

        Args:
            event_type: Count for this type, or None for total count.

        Returns:
            Number of matching subscribers.
        """
        if event_type is not None:
            return len(self._subscriptions.get(event_type, []))
        return sum(len(subs) for subs in self._subscriptions.values())

    async def clear(self) -> None:
        """Remove all subscriptions. Used in testing and shutdown."""
        async with self._lock:
            self._subscriptions.clear()
            self._subscription_map.clear()
            self._next_id = 0


class _GenericEvent(Event):
    """Generic event used by EventBus.broadcast()."""
