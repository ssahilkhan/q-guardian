"""Tests for Plugin and Storage."""

import pytest
from pathlib import Path

from q_guardian.response.enums import ResponseAction, ResponseStatus
from q_guardian.response.plugin import ResponsePlugin, PluginRegistry
from q_guardian.response.storage import ResponseStorage


class TestResponsePlugin:
    def test_base_plugin_cannot_handle(self) -> None:
        p = ResponsePlugin()
        assert p.can_handle(ResponseAction.BLOCK) is False

    def test_initialize_and_shutdown(self) -> None:
        p = ResponsePlugin()
        assert p.is_initialized is False
        p.initialize()
        assert p.is_initialized is True
        p.shutdown()
        assert p.is_initialized is False

    def test_execute_raises(self) -> None:
        p = ResponsePlugin()
        with pytest.raises(NotImplementedError):
            p.execute(ResponseAction.BLOCK, {})


class TestPluginRegistry:
    def test_register_and_get(self) -> None:
        reg = PluginRegistry()
        p = ResponsePlugin()
        p.name = "test-plugin"
        reg.register(p)
        assert reg.get("test-plugin") is p
        assert p.is_initialized is True

    def test_unregister(self) -> None:
        reg = PluginRegistry()
        p = ResponsePlugin()
        p.name = "test-plugin"
        reg.register(p)
        assert reg.unregister("test-plugin") is True
        assert reg.get("test-plugin") is None

    def test_unregister_nonexistent(self) -> None:
        reg = PluginRegistry()
        assert reg.unregister("nope") is False

    def test_bind_action(self) -> None:
        reg = PluginRegistry()
        p = ResponsePlugin()
        p.name = "bp"
        reg.register(p)
        reg.bind_action(ResponseAction.BLOCK, "bp")
        assert reg.get_handler(ResponseAction.BLOCK) is p

    def test_bind_action_missing_plugin(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(ValueError, match="Plugin not found"):
            reg.bind_action(ResponseAction.BLOCK, "nonexistent")

    def test_list_plugins(self) -> None:
        reg = PluginRegistry()
        p1 = ResponsePlugin(); p1.name = "p1"
        p2 = ResponsePlugin(); p2.name = "p2"
        reg.register(p1)
        reg.register(p2)
        assert reg.count() == 2

    def test_shutdown_all(self) -> None:
        reg = PluginRegistry()
        p = ResponsePlugin(); p.name = "p1"
        reg.register(p)
        reg.shutdown_all()
        assert reg.count() == 0


class TestResponseStorage:
    def test_save_and_load_response(self, tmp_path: Path) -> None:
        storage = ResponseStorage(str(tmp_path / "store"))
        from q_guardian.response.data import ResponseResult
        result = ResponseResult(
            status=ResponseStatus.COMPLETED,
        )
        storage.save_response(result)
        loaded = storage.load_response(result.result_id)
        assert loaded is not None

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        storage = ResponseStorage(str(tmp_path / "store"))
        assert storage.load_response("nope") is None

    def test_list_responses(self, tmp_path: Path) -> None:
        storage = ResponseStorage(str(tmp_path / "store"))
        from q_guardian.response.data import ResponseResult
        r = ResponseResult(status=ResponseStatus.COMPLETED)
        storage.save_response(r)
        assert len(storage.list_responses()) == 1

    def test_save_and_load_quarantine(self, tmp_path: Path) -> None:
        storage = ResponseStorage(str(tmp_path / "store"))
        from q_guardian.response.data import QuarantineRecord
        from q_guardian.response.enums import QuarantineType, QuarantineStatus
        rec = QuarantineRecord(
            target_type=QuarantineType.AGENT,
            target_id="a-1",
            status=QuarantineStatus.ACTIVE,
        )
        storage.save_quarantine(rec)
        loaded = storage.load_quarantine(rec.quarantine_id)
        assert loaded is not None

    def test_delete(self, tmp_path: Path) -> None:
        storage = ResponseStorage(str(tmp_path / "store"))
        from q_guardian.response.data import ResponseResult
        r = ResponseResult(status=ResponseStatus.COMPLETED)
        storage.save_response(r)
        assert storage.delete("response", r.result_id) is True
        assert storage.delete("response", r.result_id) is False

    def test_delete_unknown_category(self, tmp_path: Path) -> None:
        storage = ResponseStorage(str(tmp_path / "store"))
        assert storage.delete("unknown", "id") is False

    def test_save_playbook_execution(self, tmp_path: Path) -> None:
        storage = ResponseStorage(str(tmp_path / "store"))
        from q_guardian.response.data import PlaybookExecution
        ex = PlaybookExecution(playbook_name="test")
        storage.save_playbook_execution(ex)
        assert len(storage.list_playbook_executions()) == 1

    def test_save_rollback(self, tmp_path: Path) -> None:
        storage = ResponseStorage(str(tmp_path / "store"))
        from q_guardian.response.data import RollbackResult
        r = RollbackResult(success=True)
        storage.save_rollback(r)

    def test_save_recovery(self, tmp_path: Path) -> None:
        storage = ResponseStorage(str(tmp_path / "store"))
        from q_guardian.response.data import RecoveryResult
        r = RecoveryResult(success=True)
        storage.save_recovery(r)
