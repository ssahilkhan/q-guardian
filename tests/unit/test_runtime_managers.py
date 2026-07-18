"""Tests for runtime managers and trackers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from q_guardian.runtime.enums import MemoryOperation, MemoryType
from q_guardian.runtime.managers import (
    MemoryTracker,
    RequestManager,
    SessionManager,
    ToolExecutionTracker,
)
from q_guardian.runtime.models import (
    AgentRequest,
    AgentResponse,
    AgentSession,
    MemoryAccess,
    TokenUsage,
    ToolInvocation,
)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class TestSessionManager:
    @pytest.fixture
    def mgr(self) -> SessionManager:
        return SessionManager()

    @pytest.mark.asyncio
    async def test_create_session(self, mgr: SessionManager) -> None:
        session = await mgr.create_session(agent_id="agent-1")
        assert session.agent_id == "agent-1"
        assert session.status.value == "open"

    @pytest.mark.asyncio
    async def test_get_session(self, mgr: SessionManager) -> None:
        session = await mgr.create_session(agent_id="agent-1")
        found = await mgr.get_session(session.session_id)
        assert found is not None
        assert found.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, mgr: SessionManager) -> None:
        result = await mgr.get_session("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_session(self, mgr: SessionManager) -> None:
        session = await mgr.create_session(agent_id="agent-1")
        updated = await mgr.update_session(
            session.session_id, user_id="user-42"
        )
        assert updated is not None
        assert updated.user_id == "user-42"

    @pytest.mark.asyncio
    async def test_update_session_not_found(self, mgr: SessionManager) -> None:
        result = await mgr.update_session("nonexistent", user_id="x")
        assert result is None

    @pytest.mark.asyncio
    async def test_close_session(self, mgr: SessionManager) -> None:
        session = await mgr.create_session(agent_id="agent-1")
        closed = await mgr.close_session(session.session_id)
        assert closed is True
        found = await mgr.get_session(session.session_id)
        assert found is not None
        assert found.status.value == "closed"

    @pytest.mark.asyncio
    async def test_close_session_not_found(self, mgr: SessionManager) -> None:
        closed = await mgr.close_session("nonexistent")
        assert closed is False

    @pytest.mark.asyncio
    async def test_remove_expired(self) -> None:
        mgr = SessionManager(session_timeout_seconds=0)
        session = await mgr.create_session(agent_id="agent-1")
        import asyncio
        await asyncio.sleep(0.01)
        expired = await mgr.remove_expired_sessions()
        assert session.session_id in expired

    @pytest.mark.asyncio
    async def test_list_active_sessions(self, mgr: SessionManager) -> None:
        await mgr.create_session(agent_id="a1")
        await mgr.create_session(agent_id="a2")
        active = await mgr.list_active_sessions()
        assert len(active) == 2

    def test_session_count(self, mgr: SessionManager) -> None:
        assert mgr.session_count == 0

    @pytest.mark.asyncio
    async def test_clear(self, mgr: SessionManager) -> None:
        await mgr.create_session(agent_id="a1")
        await mgr.clear()
        assert mgr.session_count == 0


# ---------------------------------------------------------------------------
# RequestManager
# ---------------------------------------------------------------------------


class TestRequestManager:
    @pytest.fixture
    def mgr(self) -> RequestManager:
        return RequestManager()

    @pytest.mark.asyncio
    async def test_track_request(self, mgr: RequestManager) -> None:
        req = AgentRequest(prompt="hello", request_id="r1")
        await mgr.track_request(req)
        assert mgr.pending_count == 1

    @pytest.mark.asyncio
    async def test_complete_request(self, mgr: RequestManager) -> None:
        req = AgentRequest(prompt="hello", request_id="r1")
        await mgr.track_request(req)
        resp = AgentResponse(response_id="res1", output="world")
        await mgr.complete_request("r1", resp)
        assert mgr.pending_count == 0
        assert mgr.completed_count == 1

    @pytest.mark.asyncio
    async def test_fail_request(self, mgr: RequestManager) -> None:
        req = AgentRequest(prompt="hello", request_id="r1")
        await mgr.track_request(req)
        await mgr.fail_request("r1", error="timeout")
        assert mgr.pending_count == 0
        assert mgr.failed_count == 1

    @pytest.mark.asyncio
    async def test_get_request(self, mgr: RequestManager) -> None:
        req = AgentRequest(prompt="hello", request_id="r1")
        await mgr.track_request(req)
        found = await mgr.get_request("r1")
        assert found is not None
        assert found.prompt == "hello"

    @pytest.mark.asyncio
    async def test_get_request_not_found(self, mgr: RequestManager) -> None:
        result = await mgr.get_request("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_response(self, mgr: RequestManager) -> None:
        req = AgentRequest(prompt="hello", request_id="r1")
        await mgr.track_request(req)
        resp = AgentResponse(response_id="res1", output="world")
        await mgr.complete_request("r1", resp)
        found = await mgr.get_response("r1")
        assert found is not None
        assert found.output == "world"

    @pytest.mark.asyncio
    async def test_get_history(self, mgr: RequestManager) -> None:
        for i in range(5):
            req = AgentRequest(prompt=f"msg-{i}", request_id=f"r{i}")
            await mgr.track_request(req)
        history = await mgr.get_history(limit=3)
        assert len(history) == 3

    def test_total_tracked(self, mgr: RequestManager) -> None:
        assert mgr.total_tracked == 0

    @pytest.mark.asyncio
    async def test_clear(self, mgr: RequestManager) -> None:
        req = AgentRequest(prompt="hello", request_id="r1")
        await mgr.track_request(req)
        await mgr.clear()
        assert mgr.pending_count == 0


# ---------------------------------------------------------------------------
# ToolExecutionTracker
# ---------------------------------------------------------------------------


class TestToolExecutionTracker:
    @pytest.fixture
    def tracker(self) -> ToolExecutionTracker:
        return ToolExecutionTracker()

    def test_start_invocation(self, tracker: ToolExecutionTracker) -> None:
        inv = tracker.start_invocation("search", arguments={"q": "test"})
        assert inv.tool_name == "search"
        assert inv.arguments["q"] == "test"
        assert tracker.active_count == 1

    def test_finish_invocation(self, tracker: ToolExecutionTracker) -> None:
        inv = tracker.start_invocation("search")
        result = tracker.finish_invocation(
            inv.invocation_id, result={"found": True}, success=True
        )
        assert result is not None
        assert result.success is True
        assert result.result == {"found": True}
        assert tracker.active_count == 0
        assert tracker.history_count == 1

    def test_finish_not_found(self, tracker: ToolExecutionTracker) -> None:
        result = tracker.finish_invocation("nonexistent")
        assert result is None

    def test_get_invocation(self, tracker: ToolExecutionTracker) -> None:
        inv = tracker.start_invocation("search")
        found = tracker.get_invocation(inv.invocation_id)
        assert found is not None

    def test_get_invocation_not_found(self, tracker: ToolExecutionTracker) -> None:
        result = tracker.get_invocation("nonexistent")
        assert result is None

    def test_get_history(self, tracker: ToolExecutionTracker) -> None:
        for name in ["a", "b", "c"]:
            inv = tracker.start_invocation(name)
            tracker.finish_invocation(inv.invocation_id)
        loop = asyncio.new_event_loop()
        history = loop.run_until_complete(tracker.get_history(limit=2))
        assert len(history) == 2
        loop.close()

    def test_statistics(self, tracker: ToolExecutionTracker) -> None:
        inv1 = tracker.start_invocation("a")
        tracker.finish_invocation(inv1.invocation_id, success=True)
        inv2 = tracker.start_invocation("b")
        tracker.finish_invocation(inv2.invocation_id, success=False)
        stats = tracker.get_statistics()
        assert stats["total"] == 2
        assert stats["successful"] == 1
        assert stats["failed"] == 1

    def test_clear(self, tracker: ToolExecutionTracker) -> None:
        inv = tracker.start_invocation("a")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(tracker.clear())
        assert tracker.active_count == 0
        assert tracker.history_count == 0
        loop.close()


# ---------------------------------------------------------------------------
# MemoryTracker
# ---------------------------------------------------------------------------


class TestMemoryTracker:
    @pytest.fixture
    def tracker(self) -> MemoryTracker:
        return MemoryTracker()

    def test_record_access(self, tracker: MemoryTracker) -> None:
        access = tracker.record_access(
            memory_type=MemoryType.SHORT_TERM,
            operation=MemoryOperation.READ,
            key="context",
        )
        assert access.memory_type == MemoryType.SHORT_TERM
        assert tracker.total_accesses == 1

    def test_record_read(self, tracker: MemoryTracker) -> None:
        access = tracker.record_read(MemoryType.LONG_TERM, key="fact", value="data")
        assert access.operation == MemoryOperation.READ
        assert access.value == "data"

    def test_record_write(self, tracker: MemoryTracker) -> None:
        access = tracker.record_write(MemoryType.WORKING, key="state", value=42)
        assert access.operation == MemoryOperation.WRITE
        assert access.value == 42

    def test_record_delete(self, tracker: MemoryTracker) -> None:
        access = tracker.record_delete(MemoryType.EPISODIC, key="old-event")
        assert access.operation == MemoryOperation.DELETE

    def test_record_search(self, tracker: MemoryTracker) -> None:
        access = tracker.record_search(MemoryType.VECTOR, key="query", value=[1, 2, 3])
        assert access.operation == MemoryOperation.SEARCH

    def test_get_history(self, tracker: MemoryTracker) -> None:
        for i in range(5):
            tracker.record_read(MemoryType.SHORT_TERM, key=f"k{i}")
        loop = asyncio.new_event_loop()
        history = loop.run_until_complete(tracker.get_history(limit=3))
        assert len(history) == 3
        loop.close()

    def test_statistics(self, tracker: MemoryTracker) -> None:
        tracker.record_read(MemoryType.SHORT_TERM, key="a")
        tracker.record_read(MemoryType.SHORT_TERM, key="b")
        tracker.record_write(MemoryType.LONG_TERM, key="c")
        tracker.record_delete(MemoryType.EPISODIC, key="d")
        stats = tracker.get_statistics()
        assert stats["total"] == 4
        assert stats["reads"] == 2
        assert stats["writes"] == 1
        assert stats["deletes"] == 1

    def test_clear(self, tracker: MemoryTracker) -> None:
        tracker.record_read(MemoryType.SHORT_TERM, key="a")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(tracker.clear())
        assert tracker.total_accesses == 0
        loop.close()
