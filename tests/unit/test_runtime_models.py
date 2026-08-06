"""Tests for runtime domain models."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from q_guardian.runtime.enums import (
    AgentStatus,
    MemoryOperation,
    MemoryType,
    SessionStatus,
    ThreatSeverity,
    ThreatType,
    ToolType,
)
from q_guardian.runtime.models import (
    Agent,
    AgentRequest,
    AgentResponse,
    AgentSession,
    MemoryAccess,
    RiskContext,
    SecurityContext,
    ThreatContext,
    TokenUsage,
    ToolInvocation,
)

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class TestAgent:
    def test_defaults(self) -> None:
        agent = Agent(name="test-agent")
        assert agent.name == "test-agent"
        assert agent.framework == "unknown"
        assert agent.version == "1.0.0"
        assert agent.status == AgentStatus.INACTIVE
        assert isinstance(agent.id, str)
        assert len(agent.id) > 0

    def test_activate(self) -> None:
        agent = Agent(name="test-agent")
        agent.activate()
        assert agent.status == AgentStatus.ACTIVE

    def test_deactivate(self) -> None:
        agent = Agent(name="test-agent")
        agent.activate()
        agent.deactivate()
        assert agent.status == AgentStatus.INACTIVE

    def test_heartbeat(self) -> None:
        agent = Agent(name="test-agent")
        before = datetime.now(UTC)
        result = agent.heartbeat()
        after = datetime.now(UTC)
        assert result >= before
        assert result <= after

    def test_json_roundtrip(self) -> None:
        agent = Agent(name="test-agent", framework="langgraph", capabilities=["scan"])
        data = agent.model_dump()
        restored = Agent.model_validate(data)
        assert restored.name == agent.name
        assert restored.framework == agent.framework
        assert restored.capabilities == agent.capabilities

    def test_equality(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        a = Agent(name="x", id="fixed-id", created_at=ts, updated_at=ts)
        b = Agent(name="x", id="fixed-id", created_at=ts, updated_at=ts)
        assert a == b

    def test_not_equal_different_id(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        a = Agent(name="x", id="id-1", created_at=ts, updated_at=ts)
        b = Agent(name="x", id="id-2", created_at=ts, updated_at=ts)
        assert a != b

    def test_deep_copy(self) -> None:
        agent = Agent(name="test", capabilities=["a"])
        copied = copy.deepcopy(agent)
        copied.name = "changed"
        assert agent.name == "test"

    def test_custom_metadata(self) -> None:
        agent = Agent(name="test", metadata={"key": "value"})
        assert agent.metadata["key"] == "value"


# ---------------------------------------------------------------------------
# AgentSession
# ---------------------------------------------------------------------------


class TestAgentSession:
    def test_defaults(self) -> None:
        session = AgentSession(agent_id="agent-1")
        assert session.agent_id == "agent-1"
        assert session.status == SessionStatus.OPEN
        assert session.request_count == 0
        assert session.response_count == 0

    def test_open_close(self) -> None:
        session = AgentSession(agent_id="agent-1")
        session.close()
        assert session.status == SessionStatus.CLOSED
        session.open()
        assert session.status == SessionStatus.OPEN

    def test_reset(self) -> None:
        session = AgentSession(agent_id="agent-1")
        session.request_count = 5
        session.response_count = 3
        session.reset()
        assert session.request_count == 0
        assert session.response_count == 0
        assert session.status == SessionStatus.OPEN

    def test_duration_open(self) -> None:
        session = AgentSession(agent_id="agent-1")
        dur = session.duration()
        assert dur >= 0.0

    def test_duration_closed(self) -> None:
        session = AgentSession(agent_id="agent-1")
        session.close()
        dur = session.duration()
        assert dur >= 0.0

    def test_increment_requests(self) -> None:
        session = AgentSession(agent_id="agent-1")
        result = session.increment_requests()
        assert result == 1
        assert session.request_count == 1

    def test_increment_responses(self) -> None:
        session = AgentSession(agent_id="agent-1")
        result = session.increment_responses()
        assert result == 1
        assert session.response_count == 1

    def test_json_roundtrip(self) -> None:
        session = AgentSession(agent_id="agent-1", user_id="user-1")
        data = session.model_dump()
        restored = AgentSession.model_validate(data)
        assert restored.agent_id == "agent-1"
        assert restored.user_id == "user-1"

    def test_equality(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        a = AgentSession(agent_id="a", session_id="sid", created_at=ts, updated_at=ts)
        b = AgentSession(agent_id="a", session_id="sid", created_at=ts, updated_at=ts)
        assert a == b

    def test_not_equal_different_id(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        a = AgentSession(agent_id="a", session_id="s1", created_at=ts, updated_at=ts)
        b = AgentSession(agent_id="a", session_id="s2", created_at=ts, updated_at=ts)
        assert a != b

    def test_deep_copy(self) -> None:
        s = AgentSession(agent_id="a", metadata={"k": "v"})
        copied = copy.deepcopy(s)
        copied.metadata["k"] = "changed"
        assert s.metadata["k"] == "v"


# ---------------------------------------------------------------------------
# AgentRequest
# ---------------------------------------------------------------------------


class TestAgentRequest:
    def test_defaults(self) -> None:
        req = AgentRequest(prompt="hello")
        assert req.prompt == "hello"
        assert req.source == "unknown"
        assert isinstance(req.request_id, str)
        assert len(req.attachments) == 0

    def test_custom_fields(self) -> None:
        req = AgentRequest(
            prompt="test",
            source="api",
            attachments=[{"type": "file", "name": "doc.pdf"}],
            metadata={"key": "val"},
        )
        assert req.source == "api"
        assert len(req.attachments) == 1
        assert req.metadata["key"] == "val"

    def test_json_roundtrip(self) -> None:
        req = AgentRequest(prompt="hello", source="test")
        data = req.model_dump()
        restored = AgentRequest.model_validate(data)
        assert restored.prompt == "hello"

    def test_equality(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        a = AgentRequest(prompt="x", request_id="r1", timestamp=ts)
        b = AgentRequest(prompt="x", request_id="r1", timestamp=ts)
        assert a == b

    def test_not_equal_different_id(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        a = AgentRequest(prompt="x", request_id="r1", timestamp=ts)
        b = AgentRequest(prompt="x", request_id="r2", timestamp=ts)
        assert a != b


# ---------------------------------------------------------------------------
# TokenUsage & AgentResponse
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_defaults(self) -> None:
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_custom(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        assert usage.total_tokens == 30


class TestAgentResponse:
    def test_defaults(self) -> None:
        resp = AgentResponse()
        assert resp.output == ""
        assert resp.execution_time == 0.0
        assert isinstance(resp.token_usage, TokenUsage)

    def test_json_roundtrip(self) -> None:
        resp = AgentResponse(output="hi", execution_time=0.5)
        data = resp.model_dump()
        restored = AgentResponse.model_validate(data)
        assert restored.output == "hi"
        assert restored.execution_time == 0.5


# ---------------------------------------------------------------------------
# ToolInvocation
# ---------------------------------------------------------------------------


class TestToolInvocation:
    def test_defaults(self) -> None:
        inv = ToolInvocation(tool_name="search")
        assert inv.tool_name == "search"
        assert inv.tool_type == ToolType.FUNCTION
        assert inv.success is True
        assert inv.duration == 0.0

    def test_custom(self) -> None:
        inv = ToolInvocation(
            tool_name="api_call",
            tool_type=ToolType.API,
            arguments={"url": "https://example.com"},
            result={"status": 200},
            success=True,
        )
        assert inv.tool_type == ToolType.API
        assert inv.arguments["url"] == "https://example.com"

    def test_json_roundtrip(self) -> None:
        inv = ToolInvocation(tool_name="test")
        data = inv.model_dump()
        restored = ToolInvocation.model_validate(data)
        assert restored.tool_name == "test"


# ---------------------------------------------------------------------------
# MemoryAccess
# ---------------------------------------------------------------------------


class TestMemoryAccess:
    def test_defaults(self) -> None:
        access = MemoryAccess(
            memory_type=MemoryType.SHORT_TERM,
            operation=MemoryOperation.READ,
            key="context",
        )
        assert access.memory_type == MemoryType.SHORT_TERM
        assert access.operation == MemoryOperation.READ
        assert access.key == "context"

    def test_json_roundtrip(self) -> None:
        access = MemoryAccess(
            memory_type=MemoryType.LONG_TERM,
            operation=MemoryOperation.WRITE,
            key="fact",
            value={"data": "important"},
        )
        data = access.model_dump()
        restored = MemoryAccess.model_validate(data)
        assert restored.key == "fact"


# ---------------------------------------------------------------------------
# SecurityContext
# ---------------------------------------------------------------------------


class TestSecurityContext:
    def test_defaults(self) -> None:
        ctx = SecurityContext()
        assert ctx.trust_score == 1.0
        assert ctx.risk_score == 0.0
        assert ctx.blocked is False
        assert len(ctx.alerts) == 0

    def test_update_trust(self) -> None:
        ctx = SecurityContext()
        ctx.update_trust(0.5)
        assert ctx.trust_score == 0.5

    def test_update_trust_clamp(self) -> None:
        ctx = SecurityContext()
        ctx.update_trust(2.0)
        assert ctx.trust_score == 1.0
        ctx.update_trust(-1.0)
        assert ctx.trust_score == 0.0

    def test_update_risk(self) -> None:
        ctx = SecurityContext()
        ctx.update_risk(0.8)
        assert ctx.risk_score == 0.8

    def test_add_alert(self) -> None:
        ctx = SecurityContext()
        ctx.add_alert("suspicious")
        assert "suspicious" in ctx.alerts
        ctx.add_alert("suspicious")
        assert len(ctx.alerts) == 1

    def test_add_violation(self) -> None:
        ctx = SecurityContext()
        ctx.add_violation("policy1")
        assert "policy1" in ctx.violations
        ctx.add_violation("policy1")
        assert len(ctx.violations) == 1

    def test_block_unblock(self) -> None:
        ctx = SecurityContext()
        ctx.block()
        assert ctx.blocked is True
        ctx.unblock()
        assert ctx.blocked is False


# ---------------------------------------------------------------------------
# ThreatContext
# ---------------------------------------------------------------------------


class TestThreatContext:
    def test_defaults(self) -> None:
        tc = ThreatContext()
        assert tc.threat_type == ThreatType.UNKNOWN
        assert tc.severity == ThreatSeverity.LOW
        assert tc.confidence == 0.0
        assert isinstance(tc.threat_id, str)

    def test_custom(self) -> None:
        tc = ThreatContext(
            threat_type=ThreatType.PROMPT_INJECTION,
            severity=ThreatSeverity.HIGH,
            confidence=0.95,
            indicators=["ignore previous instructions"],
        )
        assert tc.threat_type == ThreatType.PROMPT_INJECTION
        assert tc.severity == ThreatSeverity.HIGH
        assert tc.confidence == 0.95


# ---------------------------------------------------------------------------
# RiskContext
# ---------------------------------------------------------------------------


class TestRiskContext:
    def test_defaults(self) -> None:
        rc = RiskContext()
        assert rc.score == 0.0
        assert len(rc.factors) == 0
        assert rc.explanation == ""

    def test_custom(self) -> None:
        rc = RiskContext(
            score=0.7,
            factors=["sensitive_data", "external_api"],
            explanation="Moderate risk",
            recommendation="Review manually",
        )
        assert rc.score == 0.7
        assert len(rc.factors) == 2


# ---------------------------------------------------------------------------
# Enum completeness
# ---------------------------------------------------------------------------


class TestEnums:
    def test_agent_status_values(self) -> None:
        assert AgentStatus.INACTIVE == "inactive"
        assert AgentStatus.ACTIVE == "active"
        assert AgentStatus.ERROR == "error"
        assert AgentStatus.DISABLED == "disabled"

    def test_session_status_values(self) -> None:
        assert SessionStatus.OPEN == "open"
        assert SessionStatus.CLOSED == "closed"
        assert SessionStatus.EXPIRED == "expired"

    def test_memory_type_all(self) -> None:
        types = [m.value for m in MemoryType]
        assert "short_term" in types
        assert "long_term" in types
        assert "vector" in types

    def test_memory_operation_all(self) -> None:
        ops = [m.value for m in MemoryOperation]
        assert "read" in ops
        assert "write" in ops
        assert "delete" in ops
        assert "search" in ops

    def test_tool_type_all(self) -> None:
        types = [t.value for t in ToolType]
        assert "function" in types
        assert "api" in types
        assert "custom" in types

    def test_threat_severity_all(self) -> None:
        sevs = [s.value for s in ThreatSeverity]
        assert "low" in sevs
        assert "critical" in sevs

    def test_threat_type_all(self) -> None:
        types = [t.value for t in ThreatType]
        assert "prompt_injection" in types
        assert "jailbreak" in types
        assert "unknown" in types
