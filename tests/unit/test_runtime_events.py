"""Tests for runtime events."""

from __future__ import annotations

from q_guardian.events.base import Event
from q_guardian.runtime.events import (
    AgentActivated,
    AgentDeactivated,
    MemoryDeleted,
    MemoryRead,
    MemoryWritten,
    RequestReceived,
    ResponseGenerated,
    SessionEnded,
    SessionStarted,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)


class TestRuntimeEvents:
    def test_session_started_type(self) -> None:
        e = SessionStarted(source="test", data={})
        assert e.event_type == "session.started"

    def test_session_ended_type(self) -> None:
        e = SessionEnded(source="test", data={})
        assert e.event_type == "session.ended"

    def test_request_received_type(self) -> None:
        e = RequestReceived(source="test", data={})
        assert e.event_type == "request.received"

    def test_response_generated_type(self) -> None:
        e = ResponseGenerated(source="test", data={})
        assert e.event_type == "response.generated"

    def test_tool_execution_started_type(self) -> None:
        e = ToolExecutionStarted(source="test", data={})
        assert e.event_type == "tool.execution.started"

    def test_tool_execution_completed_type(self) -> None:
        e = ToolExecutionCompleted(source="test", data={})
        assert e.event_type == "tool.execution.completed"

    def test_memory_read_type(self) -> None:
        e = MemoryRead(source="test", data={})
        assert e.event_type == "memory.read"

    def test_memory_written_type(self) -> None:
        e = MemoryWritten(source="test", data={})
        assert e.event_type == "memory.written"

    def test_memory_deleted_type(self) -> None:
        e = MemoryDeleted(source="test", data={})
        assert e.event_type == "memory.deleted"

    def test_agent_activated_type(self) -> None:
        e = AgentActivated(source="test", data={})
        assert e.event_type == "agent.activated"

    def test_agent_deactivated_type(self) -> None:
        e = AgentDeactivated(source="test", data={})
        assert e.event_type == "agent.deactivated"

    def test_all_events_are_event_subclass(self) -> None:
        events = [
            SessionStarted(source="t"),
            SessionEnded(source="t"),
            RequestReceived(source="t"),
            ResponseGenerated(source="t"),
            ToolExecutionStarted(source="t"),
            ToolExecutionCompleted(source="t"),
            MemoryRead(source="t"),
            MemoryWritten(source="t"),
            MemoryDeleted(source="t"),
            AgentActivated(source="t"),
            AgentDeactivated(source="t"),
        ]
        for e in events:
            assert isinstance(e, Event)

    def test_event_serialization(self) -> None:
        e = SessionStarted(
            source="guardian",
            data={"session_id": "s1", "agent_id": "a1"},
        )
        d = e.model_dump()
        assert d["event_type"] == "session.started"
        assert d["data"]["session_id"] == "s1"
