"""Tests for Guardian SDK runtime integration."""

from __future__ import annotations

import pytest

from q_guardian.runtime.enums import AgentStatus, SessionStatus
from q_guardian.runtime.events import (
    AgentActivated,
    AgentDeactivated,
    SessionEnded,
    SessionStarted,
)
from q_guardian.runtime.models import Agent
from q_guardian.sdk.guardian import Guardian


class TestGuardianRuntimeIntegration:
    @pytest.mark.asyncio
    async def test_runtime_none_before_start(self) -> None:
        guardian = Guardian()
        assert guardian.runtime is None
        assert guardian.current_agent is None
        assert guardian.current_session is None

    @pytest.mark.asyncio
    async def test_set_agent(self) -> None:
        guardian = Guardian()
        agent = Agent(name="test-bot", id="a1")
        guardian.set_agent(agent)
        assert guardian.current_agent is not None
        assert guardian.current_agent.name == "test-bot"
        assert guardian.current_agent.status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_set_agent_deactivates_previous(self) -> None:
        guardian = Guardian()
        agent1 = Agent(name="bot-1", id="a1")
        agent2 = Agent(name="bot-2", id="a2")
        guardian.set_agent(agent1)
        guardian.set_agent(agent2)
        assert agent1.status == AgentStatus.INACTIVE
        assert agent2.status == AgentStatus.ACTIVE
        assert guardian.current_agent is not None
        assert guardian.current_agent.id == "a2"

    @pytest.mark.asyncio
    async def test_create_session(self) -> None:
        guardian = Guardian()
        agent = Agent(name="bot", id="a1")
        guardian.set_agent(agent)
        session = await guardian.create_session()
        assert session.agent_id == "a1"
        assert session.status == SessionStatus.OPEN
        assert guardian.current_session is not None
        assert guardian.current_session.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_create_session_with_explicit_agent_id(self) -> None:
        guardian = Guardian()
        session = await guardian.create_session(agent_id="custom-agent")
        assert session.agent_id == "custom-agent"

    @pytest.mark.asyncio
    async def test_create_session_publishes_event(self) -> None:
        guardian = Guardian()
        events_received: list = []

        async def handler(event):
            events_received.append(event)

        await guardian.start()
        await guardian.subscribe("session.started", handler)
        session = await guardian.create_session(agent_id="a1")
        await guardian.shutdown()

        assert len(events_received) == 1
        assert events_received[0].data["session_id"] == session.session_id

    @pytest.mark.asyncio
    async def test_close_session(self) -> None:
        guardian = Guardian()
        await guardian.create_session(agent_id="a1")
        closed = await guardian.close_session()
        assert closed is True
        assert guardian.current_session is None

    @pytest.mark.asyncio
    async def test_close_session_no_active(self) -> None:
        guardian = Guardian()
        closed = await guardian.close_session()
        assert closed is False

    @pytest.mark.asyncio
    async def test_close_session_publishes_event(self) -> None:
        guardian = Guardian()
        events_received: list = []

        async def handler(event):
            events_received.append(event)

        await guardian.start()
        await guardian.subscribe("session.ended", handler)
        await guardian.create_session(agent_id="a1")
        await guardian.close_session()
        await guardian.shutdown()

        assert len(events_received) == 1

    @pytest.mark.asyncio
    async def test_runtime_context_updated(self) -> None:
        guardian = Guardian()
        agent = Agent(name="bot", id="a1")
        guardian.set_agent(agent)
        assert guardian.runtime is not None
        assert guardian.runtime.agent_id == "a1"

    @pytest.mark.asyncio
    async def test_session_manager_accessible(self) -> None:
        guardian = Guardian()
        assert guardian.session_manager is not None

    @pytest.mark.asyncio
    async def test_request_manager_accessible(self) -> None:
        guardian = Guardian()
        assert guardian.request_manager is not None

    @pytest.mark.asyncio
    async def test_tool_tracker_accessible(self) -> None:
        guardian = Guardian()
        assert guardian.tool_tracker is not None

    @pytest.mark.asyncio
    async def test_memory_tracker_accessible(self) -> None:
        guardian = Guardian()
        assert guardian.memory_tracker is not None

    @pytest.mark.asyncio
    async def test_get_runtime_context(self) -> None:
        guardian = Guardian()
        ctx = guardian.get_runtime_context()
        assert ctx is None
        await guardian.start()
        ctx = guardian.get_runtime_context()
        assert ctx is not None

    @pytest.mark.asyncio
    async def test_full_runtime_lifecycle(self) -> None:
        guardian = Guardian()
        await guardian.start()

        # Set agent
        agent = Agent(name="guardian-bot", id="g1", capabilities=["scan", "monitor"])
        guardian.set_agent(agent)
        assert guardian.current_agent is not None

        # Create session
        session = await guardian.create_session(user_id="user-1")
        assert guardian.current_session is not None

        # Runtime context is populated
        rt = guardian.runtime
        assert rt is not None
        assert rt.agent_id == "g1"
        assert rt.session_id == session.session_id

        # Close session and shutdown
        await guardian.close_session()
        assert guardian.current_session is None
        await guardian.shutdown()
