"""Tests for Playbook subsystem."""

import pytest

from q_guardian.response.data import PlaybookDefinition, PlaybookStep
from q_guardian.response.enums import StepType
from q_guardian.response.exceptions import PlaybookError, PlaybookValidationError
from q_guardian.response.playbooks.executor import PlaybookExecutor
from q_guardian.response.playbooks.parser import PlaybookParser
from q_guardian.response.playbooks.registry import PlaybookRegistry
from q_guardian.response.playbooks.templates import (
    BUILTIN_PLAYBOOKS,
    create_block_threat_playbook,
    create_escalation_playbook,
    create_quarantine_playbook,
    create_rollback_playbook,
)
from q_guardian.response.playbooks.validator import PlaybookValidator


def _make_step(name: str = "test-step", action: str = "test_action", **kw: object) -> PlaybookStep:
    return PlaybookStep(name=name, action=action, **kw)


def _make_playbook(
    name: str = "test-playbook", steps: list[PlaybookStep] | None = None, **kw: object
) -> PlaybookDefinition:
    return PlaybookDefinition(name=name, steps=steps or [_make_step()], **kw)


class TestPlaybookRegistry:
    def test_register_and_get(self) -> None:
        reg = PlaybookRegistry()
        pb = _make_playbook()
        reg.register(pb)
        assert reg.get(pb.playbook_id) is pb

    def test_register_duplicate_raises(self) -> None:
        reg = PlaybookRegistry()
        pb = _make_playbook()
        reg.register(pb)
        with pytest.raises(PlaybookError, match="already registered"):
            reg.register(pb)

    def test_unregister(self) -> None:
        reg = PlaybookRegistry()
        pb = _make_playbook()
        reg.register(pb)
        assert reg.unregister(pb.playbook_id) is True
        assert reg.get(pb.playbook_id) is None

    def test_unregister_nonexistent(self) -> None:
        reg = PlaybookRegistry()
        assert reg.unregister("nonexistent") is False

    def test_get_by_name(self) -> None:
        reg = PlaybookRegistry()
        pb = _make_playbook(name="my-playbook")
        reg.register(pb)
        assert reg.get_by_name("my-playbook") is pb
        assert reg.get_by_name("other") is None

    def test_get_by_trigger(self) -> None:
        reg = PlaybookRegistry()
        pb = _make_playbook(triggers=["threat_detected"])
        reg.register(pb)
        assert reg.get_by_trigger("threat_detected") is pb
        assert reg.get_by_trigger("other_trigger") is None

    def test_get_by_trigger_disabled_not_returned(self) -> None:
        reg = PlaybookRegistry()
        pb = _make_playbook(triggers=["threat_detected"], enabled=False)
        reg.register(pb)
        assert reg.get_by_trigger("threat_detected") is None

    def test_list_playbooks(self) -> None:
        reg = PlaybookRegistry()
        reg.register(_make_playbook(name="a"))
        reg.register(_make_playbook(name="b"))
        assert len(reg.list_playbooks()) == 2

    def test_list_enabled(self) -> None:
        reg = PlaybookRegistry()
        reg.register(_make_playbook(name="a", enabled=True))
        reg.register(_make_playbook(name="b", enabled=False))
        assert len(reg.list_enabled()) == 1

    def test_has(self) -> None:
        reg = PlaybookRegistry()
        pb = _make_playbook()
        reg.register(pb)
        assert reg.has(pb.playbook_id) is True
        assert reg.has("no") is False

    def test_count(self) -> None:
        reg = PlaybookRegistry()
        assert reg.count() == 0
        reg.register(_make_playbook())
        assert reg.count() == 1

    def test_clear(self) -> None:
        reg = PlaybookRegistry()
        reg.register(_make_playbook())
        reg.clear()
        assert reg.count() == 0


class TestPlaybookParser:
    def test_parse_dict(self) -> None:
        parser = PlaybookParser()
        pb = parser.parse_dict(
            {
                "name": "parsed",
                "steps": [{"name": "s1", "action": "act1"}],
            }
        )
        assert pb.name == "parsed"
        assert len(pb.steps) == 1
        assert pb.steps[0].name == "s1"

    def test_parse_json(self) -> None:
        parser = PlaybookParser()
        pb = parser.parse_json('{"name":"j","steps":[{"name":"s","action":"a"}]}')
        assert pb.name == "j"

    def test_parse_json_invalid(self) -> None:
        parser = PlaybookParser()
        with pytest.raises(PlaybookError, match="Invalid JSON"):
            parser.parse_json("not json")

    def test_parse_yaml_like(self) -> None:
        parser = PlaybookParser()
        yaml_str = """
name: test
description: A test playbook
steps:
- name: step1
  action: do_something
  type: action
"""
        pb = parser.parse_yaml_like(yaml_str)
        assert pb.name == "test"
        assert len(pb.steps) == 1
        assert pb.steps[0].name == "step1"

    def test_parse_dict_defaults(self) -> None:
        parser = PlaybookParser()
        pb = parser.parse_dict({})
        assert pb.name == "unnamed"
        assert pb.version == "1.0.0"


class TestPlaybookValidator:
    def test_valid_playbook(self) -> None:
        v = PlaybookValidator()
        pb = _make_playbook(steps=[_make_step(name="s1")])
        assert v.is_valid(pb) is True

    def test_empty_name(self) -> None:
        v = PlaybookValidator()
        pb = _make_playbook(name="")
        errors = v.validate(pb)
        assert any("name is required" in e for e in errors)

    def test_no_steps(self) -> None:
        v = PlaybookValidator()
        pb = PlaybookDefinition(name="test", steps=[])
        errors = v.validate(pb)
        assert any("at least one step" in e for e in errors)

    def test_duplicate_step_names(self) -> None:
        v = PlaybookValidator()
        pb = _make_playbook(steps=[_make_step(name="dup"), _make_step(name="dup")])
        errors = v.validate(pb)
        assert any("duplicate name" in e for e in errors)

    def test_unknown_dependency(self) -> None:
        v = PlaybookValidator()
        s1 = _make_step(name="s1", depends_on=["nonexistent"])
        pb = _make_playbook(steps=[s1])
        errors = v.validate(pb)
        assert any("depends_on" in e for e in errors)

    def test_negative_timeout(self) -> None:
        v = PlaybookValidator()
        s = PlaybookStep(name="s", action="a", timeout_seconds=-1.0)
        pb = _make_playbook(steps=[s])
        errors = v.validate(pb)
        assert any("timeout" in e and "negative" in e for e in errors)

    def test_negative_retry(self) -> None:
        v = PlaybookValidator()
        s = PlaybookStep(name="s", action="a", retry_count=-1)
        pb = _make_playbook(steps=[s])
        errors = v.validate(pb)
        assert any("retry_count" in e for e in errors)

    def test_require_valid_raises(self) -> None:
        v = PlaybookValidator()
        pb = _make_playbook(name="")
        with pytest.raises(PlaybookValidationError):
            v.require_valid(pb)


class TestPlaybookExecutor:
    def test_execute(self) -> None:
        executor = PlaybookExecutor()
        pb = _make_playbook(name="test", steps=[_make_step(name="s1")])
        result = executor.execute(pb, context={})
        assert result.status.value in ("completed", "failed", "in_progress")

    def test_execute_disabled_raises(self) -> None:
        executor = PlaybookExecutor()
        pb = _make_playbook(enabled=False)
        with pytest.raises(PlaybookError, match="disabled"):
            executor.execute(pb, context={})

    def test_execute_empty_steps_raises(self) -> None:
        executor = PlaybookExecutor()
        pb = PlaybookDefinition(name="empty", steps=[])
        with pytest.raises(PlaybookError, match="no steps"):
            executor.execute(pb, context={})

    def test_list_executions(self) -> None:
        executor = PlaybookExecutor()
        pb = _make_playbook(name="t", steps=[_make_step(name="s1")])
        executor.execute(pb, context={})
        assert len(executor.list_executions()) == 1


class TestPlaybookTemplates:
    def test_block_threat(self) -> None:
        pb = create_block_threat_playbook()
        assert pb.name == "block-threat"
        assert "threat_detected" in pb.triggers
        assert len(pb.steps) == 5

    def test_quarantine(self) -> None:
        pb = create_quarantine_playbook()
        assert pb.name == "quarantine-agent"
        assert any(s.step_type == StepType.APPROVAL for s in pb.steps)

    def test_escalation(self) -> None:
        pb = create_escalation_playbook()
        assert pb.name == "escalate-incident"
        assert len(pb.steps) >= 3

    def test_rollback(self) -> None:
        pb = create_rollback_playbook()
        assert pb.name == "rollback-operation"
        assert len(pb.steps) >= 3

    def test_all_builtin_playbooks_callable(self) -> None:
        for _name, factory in BUILTIN_PLAYBOOKS.items():
            pb = factory()
            assert pb.name
            assert len(pb.steps) > 0
