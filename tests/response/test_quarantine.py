"""Tests for Quarantine subsystem."""

import pytest
from q_guardian.response.enums import QuarantineType, QuarantineStatus
from q_guardian.response.exceptions import QuarantineError
from q_guardian.response.quarantine.quarantine_manager import QuarantineManager
from q_guardian.response.quarantine.session import SessionQuarantine
from q_guardian.response.quarantine.agent import AgentQuarantine
from q_guardian.response.quarantine.plugin import PluginQuarantine
from q_guardian.response.quarantine.memory import MemoryQuarantine


class TestQuarantineManager:
    def test_quarantine_and_release(self) -> None:
        mgr = QuarantineManager()
        rec = mgr.quarantine(QuarantineType.AGENT, "agent-1", reason="test")
        assert rec.status == QuarantineStatus.ACTIVE
        released = mgr.release(rec.quarantine_id)
        assert released.status == QuarantineStatus.MANUALLY_RELEASED

    def test_release_nonexistent_raises(self) -> None:
        mgr = QuarantineManager()
        with pytest.raises(QuarantineError, match="not found"):
            mgr.release("nonexistent")

    def test_release_inactive_raises(self) -> None:
        mgr = QuarantineManager()
        rec = mgr.quarantine(QuarantineType.AGENT, "a-1")
        mgr.release(rec.quarantine_id)
        with pytest.raises(QuarantineError, match="not active"):
            mgr.release(rec.quarantine_id)

    def test_is_quarantined(self) -> None:
        mgr = QuarantineManager()
        assert mgr.is_quarantined(QuarantineType.AGENT, "a-1") is False
        rec = mgr.quarantine(QuarantineType.AGENT, "a-1")
        assert mgr.is_quarantined(QuarantineType.AGENT, "a-1") is True
        mgr.release(rec.quarantine_id)
        assert mgr.is_quarantined(QuarantineType.AGENT, "a-1") is False

    def test_check_expired(self) -> None:
        mgr = QuarantineManager(default_duration_seconds=-1)  # instantly expired
        rec = mgr.quarantine(QuarantineType.SESSION, "s-1")
        expired = mgr.check_expired()
        assert len(expired) == 1
        assert expired[0].quarantine_id == rec.quarantine_id

    def test_get_active(self) -> None:
        mgr = QuarantineManager()
        mgr.quarantine(QuarantineType.AGENT, "a-1")
        mgr.quarantine(QuarantineType.AGENT, "a-2")
        assert len(mgr.get_active()) == 2

    def test_get_by_target(self) -> None:
        mgr = QuarantineManager()
        mgr.quarantine(QuarantineType.PLUGIN, "p-1")
        mgr.quarantine(QuarantineType.PLUGIN, "p-2")
        mgr.quarantine(QuarantineType.AGENT, "a-1")
        assert len(mgr.get_by_target(QuarantineType.PLUGIN, "p-1")) == 1

    def test_count_active(self) -> None:
        mgr = QuarantineManager()
        assert mgr.count_active() == 0
        mgr.quarantine(QuarantineType.AGENT, "a-1")
        assert mgr.count_active() == 1

    def test_list_all(self) -> None:
        mgr = QuarantineManager()
        mgr.quarantine(QuarantineType.AGENT, "a-1")
        mgr.quarantine(QuarantineType.SESSION, "s-1")
        assert len(mgr.list_all()) == 2

    def test_max_duration_cap(self) -> None:
        mgr = QuarantineManager(max_duration_seconds=10)
        rec = mgr.quarantine(QuarantineType.AGENT, "a-1", duration_seconds=999)
        assert rec.expires_at is not None


class TestSessionQuarantine:
    def test_quarantine_session(self) -> None:
        mgr = QuarantineManager()
        sq = SessionQuarantine(mgr)
        rec = sq.quarantine_session("s-1", reason="suspicious")
        assert rec.target_type == QuarantineType.SESSION
        assert sq.is_session_quarantined("s-1") is True

    def test_release_session(self) -> None:
        mgr = QuarantineManager()
        sq = SessionQuarantine(mgr)
        rec = sq.quarantine_session("s-1")
        released = sq.release_session(rec.quarantine_id)
        assert released.status == QuarantineStatus.MANUALLY_RELEASED


class TestAgentQuarantine:
    def test_quarantine_agent(self) -> None:
        mgr = QuarantineManager()
        aq = AgentQuarantine(mgr)
        rec = aq.quarantine_agent("a-1", reason="bad")
        assert rec.target_type == QuarantineType.AGENT
        assert aq.is_agent_quarantined("a-1") is True

    def test_release_agent(self) -> None:
        mgr = QuarantineManager()
        aq = AgentQuarantine(mgr)
        rec = aq.quarantine_agent("a-1")
        released = aq.release_agent(rec.quarantine_id)
        assert released.status == QuarantineStatus.MANUALLY_RELEASED


class TestPluginQuarantine:
    def test_quarantine_plugin(self) -> None:
        mgr = QuarantineManager()
        pq = PluginQuarantine(mgr)
        rec = pq.quarantine_plugin("p-1")
        assert rec.target_type == QuarantineType.PLUGIN
        assert pq.is_plugin_quarantined("p-1") is True

    def test_release_plugin(self) -> None:
        mgr = QuarantineManager()
        pq = PluginQuarantine(mgr)
        rec = pq.quarantine_plugin("p-1")
        released = pq.release_plugin(rec.quarantine_id)
        assert released.status == QuarantineStatus.MANUALLY_RELEASED


class TestMemoryQuarantine:
    def test_quarantine_memory(self) -> None:
        mgr = QuarantineManager()
        mq = MemoryQuarantine(mgr)
        rec = mq.quarantine_memory("m-1")
        assert rec.target_type == QuarantineType.MEMORY
        assert mq.is_memory_quarantined("m-1") is True

    def test_release_memory(self) -> None:
        mgr = QuarantineManager()
        mq = MemoryQuarantine(mgr)
        rec = mq.quarantine_memory("m-1")
        released = mq.release_memory(rec.quarantine_id)
        assert released.status == QuarantineStatus.MANUALLY_RELEASED
