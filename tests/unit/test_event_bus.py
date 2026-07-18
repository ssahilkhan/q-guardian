"""Unit tests for the event bus."""

from __future__ import annotations

import asyncio

import pytest

from q_guardian.events.base import Event
from q_guardian.events.bus import EventBus
from q_guardian.events.standard import ThreatDetected


class ConcreteEvent(Event):
    """Test concrete event."""

    event_type: str = "test.event"


class TestEventBus:
    """Tests for EventBus."""

    @pytest.fixture
    def bus(self) -> EventBus:
        return EventBus()

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, bus: EventBus) -> None:
        """Verify basic subscribe and publish."""
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        await bus.subscribe("test.event", handler)
        event = ConcreteEvent(source="test")
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].event_type == "test.event"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, bus: EventBus) -> None:
        """Verify multiple handlers receive the same event."""
        received: list[str] = []

        async def handler_a(event: Event) -> None:
            received.append("a")

        async def handler_b(event: Event) -> None:
            received.append("b")

        await bus.subscribe("test.event", handler_a)
        await bus.subscribe("test.event", handler_b)
        await bus.publish(ConcreteEvent())

        assert received == ["a", "b"]

    @pytest.mark.asyncio
    async def test_wildcard_receives_all(self, bus: EventBus) -> None:
        """Verify wildcard subscription receives all events."""
        received: list[Event] = []

        async def wildcard_handler(event: Event) -> None:
            received.append(event)

        await bus.subscribe("*", wildcard_handler)
        await bus.publish(ConcreteEvent())
        await bus.publish(ThreatDetected(source="test", data={}))

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_specific_and_wildcard_both_fire(self, bus: EventBus) -> None:
        """Verify both specific and wildcard handlers fire."""
        received: list[str] = []

        async def specific(event: Event) -> None:
            received.append("specific")

        async def wildcard(event: Event) -> None:
            received.append("wildcard")

        await bus.subscribe("test.event", specific)
        await bus.subscribe("*", wildcard)
        await bus.publish(ConcreteEvent())

        assert "specific" in received
        assert "wildcard" in received

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus: EventBus) -> None:
        """Verify unsubscribe stops delivery."""
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        sub_id = await bus.subscribe("test.event", handler)
        await bus.publish(ConcreteEvent())
        assert len(received) == 1

        await bus.unsubscribe(sub_id)
        await bus.publish(ConcreteEvent())
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_propagation_stopped(self, bus: EventBus) -> None:
        """Verify propagation_stopped prevents further handlers."""
        received: list[str] = []

        async def stopper(event: Event) -> None:
            event.stop_propagation()
            received.append("stopper")

        async def after_stopper(event: Event) -> None:
            received.append("after")

        await bus.subscribe("test.event", stopper)
        await bus.subscribe("test.event", after_stopper)
        await bus.publish(ConcreteEvent())

        assert received == ["stopper"]

    @pytest.mark.asyncio
    async def test_handler_error_does_not_break_others(self, bus: EventBus) -> None:
        """Verify a failing handler doesn't prevent other handlers."""

        async def failing(event: Event) -> None:
            raise ValueError("test error")

        async def good(event: Event) -> None:
            pass

        await bus.subscribe("test.event", failing)
        await bus.subscribe("test.event", good)
        # Should not raise
        await bus.publish(ConcreteEvent())

    @pytest.mark.asyncio
    async def test_broadcast(self, bus: EventBus) -> None:
        """Verify broadcast creates and publishes event."""
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        await bus.subscribe("custom.event", handler)
        event = await bus.broadcast("custom.event", data={"key": "value"})

        assert len(received) == 1
        assert event.event_type == "custom.event"
        assert event.data == {"key": "value"}

    @pytest.mark.asyncio
    async def test_subscriber_count(self, bus: EventBus) -> None:
        """Verify subscriber counting."""
        assert bus.subscriber_count() == 0

        async def handler(event: Event) -> None:
            pass

        await bus.subscribe("a", handler)
        await bus.subscribe("a", handler)
        await bus.subscribe("b", handler)

        assert bus.subscriber_count("a") == 2
        assert bus.subscriber_count("b") == 1
        assert bus.subscriber_count() == 3

    @pytest.mark.asyncio
    async def test_clear(self, bus: EventBus) -> None:
        """Verify clear removes all subscriptions."""
        async def handler(event: Event) -> None:
            pass

        await bus.subscribe("a", handler)
        await bus.subscribe("b", handler)
        assert bus.subscriber_count() == 2

        await bus.clear()
        assert bus.subscriber_count() == 0
