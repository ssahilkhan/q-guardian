"""Integration tests for the full Guardian lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from q_guardian.core.framework_state import FrameworkState
from q_guardian.plugins.base import Plugin
from q_guardian.sdk.guardian import Guardian

if TYPE_CHECKING:
    from q_guardian.events.base import Event


class LifecycleTrackerPlugin(Plugin):
    """Plugin that tracks lifecycle method calls."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self._context: Any = None

    @property
    def name(self) -> str:
        return "lifecycle-tracker"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def interfaces(self) -> list[str]:
        return ["prompt_scanner"]

    async def initialize(self, context: Any) -> None:
        self._context = context
        self.events.append("initialize")

    async def start(self) -> None:
        self.events.append("start")

    async def stop(self) -> None:
        self.events.append("stop")

    async def scan_prompt(self, prompt: str, **kwargs: Any) -> dict[str, str]:
        return {"scanned": prompt}


class TestGuardianLifecycleIntegration:
    """Integration tests for full Guardian lifecycle."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        """Verify complete lifecycle: create -> start -> register -> use -> shutdown."""
        guardian = Guardian()
        plugin = LifecycleTrackerPlugin()

        # Start
        await guardian.start()
        assert guardian.state == FrameworkState.RUNNING

        # Register plugin
        guardian.register_plugin(plugin)
        assert guardian.plugins.has_plugin("lifecycle-tracker")

        # Shutdown
        await guardian.shutdown()
        assert guardian.state == FrameworkState.STOPPED

    @pytest.mark.asyncio
    async def test_plugin_receives_context(self) -> None:
        """Verify plugin receives framework context during initialization."""
        guardian = Guardian()
        plugin = LifecycleTrackerPlugin()

        guardian.register_plugin(plugin)
        await guardian.start()

        assert plugin._context is not None
        assert plugin._context.event_bus is not None
        assert plugin._context.plugin_registry is not None
        assert plugin._context.hook_manager is not None

        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_event_published_during_start(self) -> None:
        """Verify FrameworkStarted event is received by subscriber."""
        guardian = Guardian()
        received: list[str] = []

        async def handler(event: Event) -> None:
            received.append(event.event_type)

        await guardian.events.subscribe("framework.started", handler)
        await guardian.start()

        assert "framework.started" in received
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_hook_executed_during_scan(self) -> None:
        """Verify hooks execute during scan_prompt."""
        guardian = Guardian()
        hook_called: list[str] = []

        async def before_prompt(**kwargs: Any) -> dict[str, str]:
            hook_called.append("before")
            return {"validated": True}

        async def after_prompt(**kwargs: Any) -> dict[str, str]:
            hook_called.append("after")
            return {}

        await guardian.start()
        await guardian.register_hook("before_prompt", before_prompt)
        await guardian.register_hook("after_prompt", after_prompt)

        plugin = LifecycleTrackerPlugin()
        guardian.register_plugin(plugin)

        result = await guardian.scan_prompt("test prompt")

        assert "before" in hook_called
        assert "after" in hook_called
        assert plugin.name in result

        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_scan_prompt_with_no_plugins(self) -> None:
        """Verify scan_prompt returns empty when no scanners registered."""
        guardian = Guardian()
        await guardian.start()

        result = await guardian.scan_prompt("test prompt")
        assert result == {}

        await guardian.shutdown()
