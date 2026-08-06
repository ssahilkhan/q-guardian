"""Runtime lifecycle events for Q-Guardian.

Defines events specific to the agent execution lifecycle. These events
are published by the runtime managers and consumed by monitoring,
security, and dashboard plugins.
"""

from __future__ import annotations

from pydantic import Field

from q_guardian.events.base import Event

# ---------------------------------------------------------------------------
# Session Events
# ---------------------------------------------------------------------------


class SessionStarted(Event):
    """Published when a new agent session is opened."""

    event_type: str = Field(default="session.started", init=False)


class SessionEnded(Event):
    """Published when an agent session is closed."""

    event_type: str = Field(default="session.ended", init=False)


# ---------------------------------------------------------------------------
# Request / Response Events
# ---------------------------------------------------------------------------


class RequestReceived(Event):
    """Published when an incoming request is received."""

    event_type: str = Field(default="request.received", init=False)


class ResponseGenerated(Event):
    """Published when a response is generated."""

    event_type: str = Field(default="response.generated", init=False)


# ---------------------------------------------------------------------------
# Tool Events
# ---------------------------------------------------------------------------


class ToolExecutionStarted(Event):
    """Published when a tool execution begins."""

    event_type: str = Field(default="tool.execution.started", init=False)


class ToolExecutionCompleted(Event):
    """Published when a tool execution finishes."""

    event_type: str = Field(default="tool.execution.completed", init=False)


# ---------------------------------------------------------------------------
# Memory Events
# ---------------------------------------------------------------------------


class MemoryRead(Event):
    """Published when a memory read occurs."""

    event_type: str = Field(default="memory.read", init=False)


class MemoryWritten(Event):
    """Published when a memory write occurs."""

    event_type: str = Field(default="memory.written", init=False)


class MemoryDeleted(Event):
    """Published when a memory delete occurs."""

    event_type: str = Field(default="memory.deleted", init=False)


# ---------------------------------------------------------------------------
# Agent Events
# ---------------------------------------------------------------------------


class AgentActivated(Event):
    """Published when an agent transitions to active status."""

    event_type: str = Field(default="agent.activated", init=False)


class AgentDeactivated(Event):
    """Published when an agent transitions to inactive status."""

    event_type: str = Field(default="agent.deactivated", init=False)
