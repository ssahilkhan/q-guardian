"""Tests for RuntimeContext."""

from __future__ import annotations

import pytest

from q_guardian.runtime.context import RuntimeContext
from q_guardian.runtime.enums import ThreatSeverity, ThreatType
from q_guardian.runtime.models import (
    Agent,
    AgentRequest,
    AgentResponse,
    AgentSession,
    MemoryAccess,
    SecurityContext,
    ThreatContext,
    ToolInvocation,
)
from q_guardian.runtime.enums import MemoryOperation, MemoryType


class TestRuntimeContext:
    def test_defaults(self) -> None:
        ctx = RuntimeContext()
        assert ctx.current_agent is None
        assert ctx.current_session is None
        assert ctx.current_request is None
        assert ctx.current_response is None
        assert len(ctx.tool_invocations) == 0
        assert len(ctx.memory_accesses) == 0
        assert ctx.threats == []
        assert ctx.extra == {}

    def test_agent_id_shortcut(self) -> None:
        ctx = RuntimeContext(current_agent=Agent(name="test", id="a1"))
        assert ctx.agent_id == "a1"

    def test_agent_id_empty(self) -> None:
        ctx = RuntimeContext()
        assert ctx.agent_id == ""

    def test_agent_name_shortcut(self) -> None:
        ctx = RuntimeContext(current_agent=Agent(name="my-bot"))
        assert ctx.agent_name == "my-bot"

    def test_agent_name_empty(self) -> None:
        ctx = RuntimeContext()
        assert ctx.agent_name == ""

    def test_session_id_shortcut(self) -> None:
        ctx = RuntimeContext(current_session=AgentSession(agent_id="a", session_id="s1"))
        assert ctx.session_id == "s1"

    def test_session_id_empty(self) -> None:
        ctx = RuntimeContext()
        assert ctx.session_id == ""

    def test_prompt_shortcut(self) -> None:
        ctx = RuntimeContext(current_request=AgentRequest(prompt="hello"))
        assert ctx.prompt == "hello"

    def test_prompt_empty(self) -> None:
        ctx = RuntimeContext()
        assert ctx.prompt == ""

    def test_is_blocked(self) -> None:
        ctx = RuntimeContext()
        assert ctx.is_blocked is False
        ctx.security.block()
        assert ctx.is_blocked is True

    def test_add_tool_invocation(self) -> None:
        ctx = RuntimeContext()
        inv = ToolInvocation(tool_name="search")
        ctx.add_tool_invocation(inv)
        assert ctx.tool_count == 1
        assert ctx.failed_tool_count == 0

    def test_tool_count(self) -> None:
        ctx = RuntimeContext()
        ctx.add_tool_invocation(ToolInvocation(tool_name="a"))
        ctx.add_tool_invocation(ToolInvocation(tool_name="b", success=False))
        assert ctx.tool_count == 2
        assert ctx.failed_tool_count == 1

    def test_add_memory_access(self) -> None:
        ctx = RuntimeContext()
        access = MemoryAccess(
            memory_type=MemoryType.SHORT_TERM,
            operation=MemoryOperation.READ,
            key="k",
        )
        ctx.add_memory_access(access)
        assert ctx.memory_access_count == 1

    def test_add_threat(self) -> None:
        ctx = RuntimeContext()
        assert ctx.has_threats() is False
        threat = ThreatContext(threat_type=ThreatType.JAILBREAK, severity=ThreatSeverity.HIGH)
        ctx.add_threat(threat)
        assert ctx.has_threats() is True
        assert ctx.threat_count == 1

    def test_to_snapshot(self) -> None:
        agent = Agent(name="test", id="a1")
        session = AgentSession(agent_id="a1", session_id="s1")
        request = AgentRequest(prompt="hello world")
        ctx = RuntimeContext(
            current_agent=agent,
            current_session=session,
            current_request=request,
        )
        snap = ctx.to_snapshot()
        assert snap["agent_id"] == "a1"
        assert snap["session_id"] == "s1"
        assert snap["prompt"] == "hello world"
        assert snap["tool_count"] == 0
        assert snap["is_blocked"] is False

    def test_json_roundtrip(self) -> None:
        ctx = RuntimeContext(
            current_agent=Agent(name="test"),
            extra={"custom": "data"},
        )
        data = ctx.model_dump()
        restored = RuntimeContext.model_validate(data)
        assert restored.current_agent is not None
        assert restored.current_agent.name == "test"
        assert restored.extra["custom"] == "data"
