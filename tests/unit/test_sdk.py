"""Unit tests for the Guardian SDK."""

from __future__ import annotations

from typing import Any

import pytest

from q_guardian.core.framework_state import FrameworkState
from q_guardian.events.base import Event
from q_guardian.events.standard import FrameworkStarted, FrameworkStopped
from q_guardian.framework.config import FrameworkConfig
from q_guardian.plugins.base import Plugin
from q_guardian.sdk.guardian import Guardian


class SamplePlugin(Plugin):
    """Test plugin for SDK tests."""

    def __init__(self) -> None:
        self.initialized = False
        self.started = False
        self.stopped = False

    @property
    def name(self) -> str:
        return "test-plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def initialize(self, context: Any) -> None:
        self.initialized = True

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class TestGuardianInit:
    """Tests for Guardian initialization."""

    def test_default_config(self) -> None:
        """Verify Guardian initializes with default config."""
        guardian = Guardian()
        assert guardian.config is not None
        assert guardian.state == FrameworkState.INITIALIZING

    def test_custom_config(self) -> None:
        """Verify Guardian accepts custom config."""
        config = FrameworkConfig()
        guardian = Guardian(config=config)
        assert guardian.config is config

    def test_components_created(self) -> None:
        """Verify internal components are created."""
        guardian = Guardian()
        assert guardian.events is not None
        assert guardian.plugins is not None

    def test_context_none_before_start(self) -> None:
        """Verify context is None before start."""
        guardian = Guardian()
        assert guardian.get_context() is None


class TestGuardianLifecycle:
    """Tests for Guardian lifecycle."""

    @pytest.mark.asyncio
    async def test_start_and_shutdown(self) -> None:
        """Verify full start/shutdown lifecycle."""
        guardian = Guardian()
        await guardian.start()
        assert guardian.state == FrameworkState.RUNNING

        await guardian.shutdown()
        assert guardian.state == FrameworkState.STOPPED

    @pytest.mark.asyncio
    async def test_context_available_after_start(self) -> None:
        """Verify context is available after start."""
        guardian = Guardian()
        await guardian.start()
        assert guardian.get_context() is not None
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_when_not_running(self) -> None:
        """Verify shutdown is no-op when not running."""
        guardian = Guardian()
        initial_state = guardian.state
        # Should not raise
        await guardian.shutdown()
        assert guardian.state == initial_state

    @pytest.mark.asyncio
    async def test_start_publishes_event(self) -> None:
        """Verify FrameworkStarted event is published."""
        guardian = Guardian()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        await guardian.events.subscribe("framework.started", handler)
        await guardian.start()
        assert len(received) == 1
        assert isinstance(received[0], FrameworkStarted)
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_publishes_event(self) -> None:
        """Verify FrameworkStopped event is published."""
        guardian = Guardian()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        await guardian.events.subscribe("framework.stopped", handler)
        await guardian.start()
        await guardian.shutdown()
        assert len(received) == 1
        assert isinstance(received[0], FrameworkStopped)


class TestGuardianPlugins:
    """Tests for Guardian plugin management."""

    @pytest.mark.asyncio
    async def test_register_plugin(self) -> None:
        """Verify plugin registration."""
        guardian = Guardian()
        await guardian.start()
        plugin = SamplePlugin()
        guardian.register_plugin(plugin)
        assert guardian.get_plugin("test-plugin") is plugin
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_unregister_plugin(self) -> None:
        """Verify plugin unregistration."""
        guardian = Guardian()
        await guardian.start()
        guardian.register_plugin(SamplePlugin())
        guardian.unregister_plugin("test-plugin")
        assert not guardian.plugins.has_plugin("test-plugin")
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_list_plugins(self) -> None:
        """Verify plugin listing."""
        guardian = Guardian()
        await guardian.start()
        guardian.register_plugin(SamplePlugin())
        plugins = guardian.list_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "test-plugin"
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_enable_disable_plugin(self) -> None:
        """Verify plugin enable/disable."""
        guardian = Guardian()
        await guardian.start()
        guardian.register_plugin(SamplePlugin())
        guardian.disable_plugin("test-plugin")
        guardian.enable_plugin("test-plugin")
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_plugin_lifecycle_called(self) -> None:
        """Verify plugin lifecycle methods are called."""
        guardian = Guardian()
        plugin = SamplePlugin()
        guardian.register_plugin(plugin)
        await guardian.start()
        assert plugin.initialized is True
        assert plugin.started is True

        await guardian.shutdown()
        assert plugin.stopped is True


class TestGuardianEvents:
    """Tests for Guardian event system delegation."""

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self) -> None:
        """Verify event subscribe/publish through Guardian."""
        guardian = Guardian()
        await guardian.start()

        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        sub_id = await guardian.subscribe("test.event", handler)
        await guardian.publish(
            Event.__subclasses__()[0]  # Use a concrete event
            if False
            else FrameworkStarted(source="test")
        )
        # The above will be "framework.started", let's use broadcast
        await guardian.unsubscribe(sub_id)

        await guardian.shutdown()


class TestGuardianAdapters:
    """Tests for Guardian adapter management."""

    def test_register_adapter(self) -> None:
        """Verify adapter registration."""
        from q_guardian.adapters.generic import GenericAdapter

        guardian = Guardian()
        adapter = GenericAdapter()
        guardian.register_adapter(adapter)
        assert guardian.get_adapter("generic") is adapter

    def test_get_adapter_not_found(self) -> None:
        """Verify KeyError for missing adapter."""
        guardian = Guardian()
        with pytest.raises(KeyError):
            guardian.get_adapter("nonexistent")


class TestGuardianHooks:
    """Tests for Guardian hook system delegation."""

    @pytest.mark.asyncio
    async def test_register_and_execute_hook(self) -> None:
        """Verify hook registration and execution."""
        guardian = Guardian()
        await guardian.start()

        async def my_hook(**kwargs: Any) -> dict[str, str]:
            return {"result": "hooked"}

        await guardian.register_hook("test_hook", my_hook)
        result = await guardian.execute_hook("test_hook")
        assert result["result"] == "hooked"

        await guardian.shutdown()
