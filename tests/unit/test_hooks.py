"""Unit tests for the hook manager."""

from __future__ import annotations

import pytest

from q_guardian.hooks.manager import HookManager


class TestHookManager:
    """Tests for HookManager."""

    @pytest.fixture
    def manager(self) -> HookManager:
        return HookManager()

    @pytest.mark.asyncio
    async def test_register_and_execute(self, manager: HookManager) -> None:
        """Verify basic hook registration and execution."""
        received: list[str] = []

        async def my_hook(prompt: str = "") -> None:
            received.append(prompt)

        await manager.register_hook("before_prompt", my_hook)
        await manager.execute_hook("before_prompt", prompt="hello")

        assert received == ["hello"]

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, manager: HookManager) -> None:
        """Verify multiple handlers execute for same hook."""
        order: list[str] = []

        async def first(**kwargs: object) -> None:
            order.append("first")

        async def second(**kwargs: object) -> None:
            order.append("second")

        await manager.register_hook("test_hook", first)
        await manager.register_hook("test_hook", second)
        await manager.execute_hook("test_hook")

        assert order == ["first", "second"]

    @pytest.mark.asyncio
    async def test_handler_modifies_context(self, manager: HookManager) -> None:
        """Verify handlers can modify the context."""
        async def add_field(field: str = "") -> dict[str, str]:
            return {"added": "value"}

        await manager.register_hook("test_hook", add_field)
        result = await manager.execute_hook("test_hook", field="input")

        assert result["added"] == "value"
        assert result["field"] == "input"

    @pytest.mark.asyncio
    async def test_unregister(self, manager: HookManager) -> None:
        """Verify handler removal."""
        call_count = 0

        async def counter(**kwargs: object) -> None:
            nonlocal call_count
            call_count += 1

        await manager.register_hook("test", counter)
        await manager.execute_hook("test")
        assert call_count == 1

        removed = await manager.unregister_hook("test", counter)
        assert removed is True

        await manager.execute_hook("test")
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_returns_false(self, manager: HookManager) -> None:
        """Verify unregistering nonexistent handler returns False."""

        async def handler(**kwargs: object) -> None:
            pass

        result = await manager.unregister_hook("nonexistent", handler)
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_hook_returns_context(self, manager: HookManager) -> None:
        """Verify execute_hook returns merged context."""
        result = await manager.execute_hook("empty_hook")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_list_hooks(self, manager: HookManager) -> None:
        """Verify hook listing."""
        async def handler(**kwargs: object) -> None:
            pass

        await manager.register_hook("hook_a", handler)
        await manager.register_hook("hook_a", handler)
        await manager.register_hook("hook_b", handler)

        hooks = manager.list_hooks()
        assert hooks["hook_a"] == 2
        assert hooks["hook_b"] == 1

    @pytest.mark.asyncio
    async def test_clear(self, manager: HookManager) -> None:
        """Verify clear removes all hooks."""
        async def handler(**kwargs: object) -> None:
            pass

        await manager.register_hook("a", handler)
        await manager.register_hook("b", handler)

        await manager.clear()
        assert manager.list_hooks() == {}

    @pytest.mark.asyncio
    async def test_sync_handler(self, manager: HookManager) -> None:
        """Verify synchronous handlers are supported."""
        def sync_hook(**kwargs: object) -> dict[str, str]:
            return {"sync": "result"}

        await manager.register_hook("sync_hook", sync_hook)
        result = await manager.execute_hook("sync_hook")
        assert result["sync"] == "result"

    @pytest.mark.asyncio
    async def test_handler_error_logged_not_raised(self, manager: HookManager) -> None:
        """Verify handler errors are caught and logged."""

        async def bad_handler(**kwargs: object) -> None:
            raise ValueError("hook error")

        async def good_handler(**kwargs: object) -> dict[str, str]:
            return {"good": "ok"}

        await manager.register_hook("test", bad_handler)
        await manager.register_hook("test", good_handler)
        result = await manager.execute_hook("test")

        assert result["good"] == "ok"
