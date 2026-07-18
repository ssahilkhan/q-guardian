"""Tests for Rollback, Recovery, and Approval Engines."""

import pytest
from q_guardian.response.data import RecoveryPlan
from q_guardian.response.enums import (
    RollbackTarget,
    RecoveryAction,
    ApprovalType,
    ApprovalStatus,
)
from q_guardian.response.engine.rollback_engine import RollbackEngine
from q_guardian.response.engine.recovery_engine import RecoveryEngine
from q_guardian.response.engine.approval_engine import ApprovalEngine


class TestRollbackEngine:
    def test_create_checkpoint(self) -> None:
        eng = RollbackEngine()
        cp = eng.create_checkpoint(
            target=RollbackTarget.SESSION,
            state={"key": "val"},
        )
        assert cp.target == RollbackTarget.SESSION

    def test_rollback(self) -> None:
        eng = RollbackEngine()
        cp = eng.create_checkpoint(target=RollbackTarget.SESSION, state={"v": 1})
        result = eng.rollback(cp.checkpoint_id)
        assert result.success is True
        assert result.restored_state == {"v": 1}

    def test_rollback_nonexistent(self) -> None:
        eng = RollbackEngine()
        result = eng.rollback("nope")
        assert result.success is False

    def test_max_checkpoints(self) -> None:
        eng = RollbackEngine(max_checkpoints=2)
        eng.create_checkpoint(target=RollbackTarget.SESSION, state={"s": 1})
        eng.create_checkpoint(target=RollbackTarget.SESSION, state={"s": 2})
        eng.create_checkpoint(target=RollbackTarget.SESSION, state={"s": 3})
        assert len(eng.list_checkpoints(target=RollbackTarget.SESSION)) <= 2

    def test_list_checkpoints(self) -> None:
        eng = RollbackEngine()
        eng.create_checkpoint(target=RollbackTarget.SESSION, state={})
        eng.create_checkpoint(target=RollbackTarget.PLUGIN, state={})
        assert len(eng.list_checkpoints()) == 2

    def test_list_checkpoints_by_target(self) -> None:
        eng = RollbackEngine()
        eng.create_checkpoint(target=RollbackTarget.SESSION, state={})
        eng.create_checkpoint(target=RollbackTarget.PLUGIN, state={})
        sessions = eng.list_checkpoints(target=RollbackTarget.SESSION)
        assert len(sessions) == 1

    def test_rollback_latest(self) -> None:
        eng = RollbackEngine()
        eng.create_checkpoint(target=RollbackTarget.SESSION, state={"v": 1})
        eng.create_checkpoint(target=RollbackTarget.SESSION, state={"v": 2})
        result = eng.rollback_latest(RollbackTarget.SESSION)
        assert result.success is True
        assert result.restored_state == {"v": 2}

    def test_rollback_latest_none(self) -> None:
        eng = RollbackEngine()
        result = eng.rollback_latest(RollbackTarget.SESSION)
        assert result.success is False

    def test_get_checkpoint(self) -> None:
        eng = RollbackEngine()
        cp = eng.create_checkpoint(target=RollbackTarget.SESSION, state={})
        assert eng.get_checkpoint(cp.checkpoint_id) is cp

    def test_get_checkpoint_nonexistent(self) -> None:
        eng = RollbackEngine()
        assert eng.get_checkpoint("nope") is None

    def test_clear(self) -> None:
        eng = RollbackEngine()
        eng.create_checkpoint(target=RollbackTarget.SESSION, state={})
        eng.clear(target=RollbackTarget.SESSION)
        assert len(eng.list_checkpoints(target=RollbackTarget.SESSION)) == 0


class TestRecoveryEngine:
    def test_execute_plan_resume_session(self) -> None:
        eng = RecoveryEngine()
        plan = RecoveryPlan(
            actions=[RecoveryAction.RESUME_SESSION],
            parameters={"session_id": "s-1"},
        )
        result = eng.execute_plan(plan, context={"session_id": "s-1"})
        assert result.success is True
        assert "resume_session" in result.actions_succeeded

    def test_execute_plan_restore_memory(self) -> None:
        eng = RecoveryEngine()
        plan = RecoveryPlan(actions=[RecoveryAction.RESTORE_MEMORY])
        result = eng.execute_plan(plan)
        assert result.success is True
        assert "restore_memory" in result.actions_succeeded

    def test_execute_plan_restart_agent(self) -> None:
        eng = RecoveryEngine()
        plan = RecoveryPlan(actions=[RecoveryAction.RESTART_AGENT])
        result = eng.execute_plan(plan, context={"agent_id": "a-1"})
        assert result.success is True
        assert "restart_agent" in result.actions_succeeded

    def test_execute_plan_multiple(self) -> None:
        eng = RecoveryEngine()
        plan = RecoveryPlan(
            actions=[
                RecoveryAction.RESUME_SESSION,
                RecoveryAction.RESTORE_MEMORY,
                RecoveryAction.RESTART_AGENT,
            ],
        )
        result = eng.execute_plan(plan, context={"session_id": "s", "agent_id": "a"})
        assert result.success is True
        assert len(result.actions_succeeded) == 3

    def test_execute_plan_missing_handler(self) -> None:
        eng = RecoveryEngine()
        plan = RecoveryPlan(actions=[RecoveryAction.CUSTOM])
        result = eng.execute_plan(plan)
        assert result.success is False

    def test_custom_handler(self) -> None:
        eng = RecoveryEngine()
        eng.register_handler("custom", lambda a, c: {"ok": True})
        plan = RecoveryPlan(actions=[RecoveryAction.CUSTOM])
        result = eng.execute_plan(plan)
        assert result.success is True

    def test_list_results(self) -> None:
        eng = RecoveryEngine()
        plan = RecoveryPlan(actions=[RecoveryAction.RESTORE_MEMORY])
        eng.execute_plan(plan)
        assert len(eng.list_results()) == 1

    def test_get_result(self) -> None:
        eng = RecoveryEngine()
        plan = RecoveryPlan(actions=[RecoveryAction.RESTORE_MEMORY])
        r = eng.execute_plan(plan)
        assert eng.get_result(r.result_id) is r


class TestApprovalEngine:
    def test_request_approval(self) -> None:
        eng = ApprovalEngine()
        req = eng.request_approval(
            action="block_agent",
            approval_type=ApprovalType.MANUAL,
            description="threat detected",
        )
        assert req.status == ApprovalStatus.PENDING

    def test_approve(self) -> None:
        eng = ApprovalEngine()
        req = eng.request_approval(
            action="quarantine",
            approval_type=ApprovalType.MANUAL,
            approvers=["admin"],
        )
        result = eng.approve(req.request_id, approver="admin")
        assert result.status == ApprovalStatus.APPROVED

    def test_reject(self) -> None:
        eng = ApprovalEngine()
        req = eng.request_approval(
            action="escalate",
            approval_type=ApprovalType.MANUAL,
            approvers=["admin"],
        )
        result = eng.reject(req.request_id, approver="admin", reason="not needed")
        assert result.status == ApprovalStatus.REJECTED

    def test_cancel(self) -> None:
        eng = ApprovalEngine()
        req = eng.request_approval(
            action="notify",
            approval_type=ApprovalType.MANUAL,
        )
        result = eng.cancel(req.request_id)
        assert result.status == ApprovalStatus.CANCELLED

    def test_approve_nonexistent(self) -> None:
        eng = ApprovalEngine()
        with pytest.raises(Exception):
            eng.approve("nope", approver="admin")

    def test_auto_approve(self) -> None:
        eng = ApprovalEngine()
        req = eng.request_approval(
            action="block",
            approval_type=ApprovalType.AUTOMATIC,
        )
        assert req.status == ApprovalStatus.APPROVED

    def test_multi_level_approval(self) -> None:
        eng = ApprovalEngine()
        req = eng.request_approval(
            action="terminate",
            approval_type=ApprovalType.MANUAL,
            approvers=["admin1", "admin2"],
            required_approvals=2,
        )
        eng.approve(req.request_id, approver="admin1")
        assert req.status == ApprovalStatus.PENDING
        eng.approve(req.request_id, approver="admin2")
        assert req.status == ApprovalStatus.APPROVED

    def test_list_pending(self) -> None:
        eng = ApprovalEngine()
        eng.request_approval(action="r1", approval_type=ApprovalType.MANUAL)
        eng.request_approval(action="r2", approval_type=ApprovalType.MANUAL)
        assert len(eng.list_pending()) == 2

    def test_get_request(self) -> None:
        eng = ApprovalEngine()
        req = eng.request_approval(action="r", approval_type=ApprovalType.MANUAL)
        assert eng.get_request(req.request_id) is req

    def test_get_request_nonexistent(self) -> None:
        eng = ApprovalEngine()
        assert eng.get_request("nope") is None

    def test_check_timeouts(self) -> None:
        eng = ApprovalEngine(default_timeout_seconds=-1)
        req = eng.request_approval(action="r", approval_type=ApprovalType.MANUAL)
        expired = eng.check_timeouts()
        assert len(expired) == 1
        assert req.status == ApprovalStatus.EXPIRED
