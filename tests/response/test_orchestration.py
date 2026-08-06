"""Tests for Orchestration Engine."""

from q_guardian.response.data import PlaybookDefinition, PlaybookStep
from q_guardian.response.engine.orchestration_engine import OrchestrationEngine
from q_guardian.response.enums import FailureStrategy, ResponseStatus


def _step(name: str, action: str = "test_action", **kw: object) -> PlaybookStep:
    return PlaybookStep(name=name, action=action, **kw)


def _playbook(name: str = "test", steps: list[PlaybookStep] | None = None) -> PlaybookDefinition:
    return PlaybookDefinition(name=name, steps=steps or [_step("s1")])


class TestOrchestrationEngine:
    def test_execute_single_step(self) -> None:
        eng = OrchestrationEngine()
        pb = _playbook(steps=[_step("s1", action="block")])
        result = eng.execute_playbook(pb, context={})
        assert result.status.value in ("completed", "failed")

    def test_execute_sequential_steps(self) -> None:
        eng = OrchestrationEngine()
        s1 = _step("s1", action="collect_evidence")
        s2 = _step("s2", action="block", depends_on=["s1"])
        pb = _playbook(steps=[s1, s2])
        result = eng.execute_playbook(pb, context={})
        assert len(result.step_results) == 2

    def test_execute_empty_steps(self) -> None:
        eng = OrchestrationEngine()
        pb = _playbook(steps=[])
        result = eng.execute_playbook(pb, context={})
        assert result.status.value == "completed"

    def test_execute_with_context(self) -> None:
        eng = OrchestrationEngine()
        pb = _playbook(steps=[_step("s1")])
        result = eng.execute_playbook(pb, context={"key": "value"})
        assert result.status.value in ("completed", "failed")

    def test_correlation_id_propagated(self) -> None:
        eng = OrchestrationEngine()
        pb = _playbook(steps=[_step("s1")])
        result = eng.execute_playbook(pb, context={}, correlation_id="corr-1")
        assert result.correlation_id == "corr-1"

    def test_list_executions(self) -> None:
        eng = OrchestrationEngine()
        pb = _playbook(steps=[_step("s1")])
        eng.execute_playbook(pb, context={})
        assert len(eng.list_executions()) == 1

    def test_get_execution(self) -> None:
        eng = OrchestrationEngine()
        pb = _playbook(steps=[_step("s1")])
        result = eng.execute_playbook(pb, context={})
        assert eng.get_execution(result.execution_id) is result

    def test_get_execution_nonexistent(self) -> None:
        eng = OrchestrationEngine()
        assert eng.get_execution("nope") is None

    def test_step_failure_stop(self) -> None:
        eng = OrchestrationEngine()

        def fail_handler(step, ctx):
            raise RuntimeError("step failed")

        eng.register_handler("action", fail_handler)
        s1 = _step("s1", action="fail_action", failure_strategy=FailureStrategy.STOP)
        s2 = _step("s2", action="block", depends_on=["s1"])
        pb = _playbook(steps=[s1, s2])
        result = eng.execute_playbook(pb, context={})
        assert result.status == ResponseStatus.FAILED

    def test_step_failure_skip(self) -> None:
        eng = OrchestrationEngine()
        call_count = {"n": 0}

        def selective_fail_handler(step, ctx):
            if step.name == "s1":
                raise RuntimeError("step failed")
            call_count["n"] += 1
            return {"ok": True}

        eng.register_handler("action", selective_fail_handler)
        s1 = _step("s1", action="fail_action", failure_strategy=FailureStrategy.SKIP)
        s2 = _step("s2", action="block")
        pb = _playbook(steps=[s1, s2])
        result = eng.execute_playbook(pb, context={})
        # s1 failed (SKIP) but s2 still ran
        assert call_count["n"] == 1
        assert len(result.step_results) == 2

    def test_disabled_step_skipped(self) -> None:
        eng = OrchestrationEngine()
        s1 = _step("s1", action="block", enabled=False)
        pb = _playbook(steps=[s1])
        result = eng.execute_playbook(pb, context={})
        assert len(result.step_results) == 0
