"""Unit tests for the plugin system."""

from __future__ import annotations

from typing import Any

import pytest

from q_guardian.exceptions.base import ValidationException
from q_guardian.framework.context import FrameworkContext
from q_guardian.plugins.base import Plugin, PluginMetadata, PluginStatus
from q_guardian.plugins.registry import PluginRegistry


class SimplePlugin(Plugin):
    """Concrete test plugin."""

    @property
    def name(self) -> str:
        return "test-plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def author(self) -> str:
        return "Tester"

    @property
    def description(self) -> str:
        return "A test plugin"

    @property
    def interfaces(self) -> list[str]:
        return ["prompt_scanner"]

    async def initialize(self, context: Any) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class AnotherPlugin(Plugin):
    """Another test plugin."""

    @property
    def name(self) -> str:
        return "another-plugin"

    @property
    def version(self) -> str:
        return "2.0.0"

    async def initialize(self, context: Any) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class FailingInitPlugin(Plugin):
    """Plugin that fails during initialization."""

    @property
    def name(self) -> str:
        return "failing-init"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def initialize(self, context: Any) -> None:
        raise RuntimeError("init failed")

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class TestPluginMetadata:
    """Tests for PluginMetadata."""

    def test_metadata_from_plugin(self) -> None:
        """Verify metadata is built from plugin properties."""
        plugin = SimplePlugin()
        meta = plugin.metadata()
        assert meta.name == "test-plugin"
        assert meta.version == "1.0.0"
        assert meta.author == "Tester"
        assert meta.status == PluginStatus.REGISTERED

    def test_metadata_defaults(self) -> None:
        """Verify default metadata values."""
        meta = PluginMetadata(name="test", version="1.0.0")
        assert meta.author == ""
        assert meta.dependencies == []
        assert meta.interfaces == []


class TestPluginStatus:
    """Tests for PluginStatus enum."""

    def test_all_statuses(self) -> None:
        """Verify all expected statuses exist."""
        statuses = {s.value for s in PluginStatus}
        assert "registered" in statuses
        assert "running" in statuses
        assert "stopped" in statuses
        assert "error" in statuses
        assert "disabled" in statuses


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    @pytest.fixture
    def registry(self) -> PluginRegistry:
        return PluginRegistry()

    def test_register_plugin(self, registry: PluginRegistry) -> None:
        """Verify plugin registration."""
        registry.register_plugin(SimplePlugin())
        assert registry.has_plugin("test-plugin")

    def test_register_duplicate_raises(self, registry: PluginRegistry) -> None:
        """Verify duplicate registration raises error."""
        registry.register_plugin(SimplePlugin())
        with pytest.raises(ValidationException):
            registry.register_plugin(SimplePlugin())

    def test_unregister_plugin(self, registry: PluginRegistry) -> None:
        """Verify plugin unregistration."""
        registry.register_plugin(SimplePlugin())
        registry.unregister_plugin("test-plugin")
        assert not registry.has_plugin("test-plugin")

    def test_get_plugin(self, registry: PluginRegistry) -> None:
        """Verify plugin retrieval."""
        registry.register_plugin(SimplePlugin())
        plugin = registry.get_plugin("test-plugin")
        assert plugin.name == "test-plugin"

    def test_get_plugin_not_found(self, registry: PluginRegistry) -> None:
        """Verify KeyError for missing plugin."""
        with pytest.raises(KeyError):
            registry.get_plugin("nonexistent")

    def test_get_plugins_by_interface(self, registry: PluginRegistry) -> None:
        """Verify interface-based plugin lookup."""
        registry.register_plugin(SimplePlugin())
        registry.register_plugin(AnotherPlugin())

        scanners = registry.get_plugins_by_interface("prompt_scanner")
        assert len(scanners) == 1
        assert scanners[0].name == "test-plugin"

    def test_list_plugins_all(self, registry: PluginRegistry) -> None:
        """Verify listing all plugins."""
        registry.register_plugin(SimplePlugin())
        registry.register_plugin(AnotherPlugin())
        plugins = registry.list_plugins()
        assert len(plugins) == 2

    def test_list_plugins_by_status(self, registry: PluginRegistry) -> None:
        """Verify listing plugins filtered by status."""
        registry.register_plugin(SimplePlugin())
        registry.disable_plugin("test-plugin")
        plugins = registry.list_plugins(status=PluginStatus.DISABLED)
        assert len(plugins) == 1

    def test_enable_disable(self, registry: PluginRegistry) -> None:
        """Verify enable/disable toggling."""
        registry.register_plugin(SimplePlugin())
        registry.disable_plugin("test-plugin")
        meta = registry.list_plugins()[0]
        assert meta.status == PluginStatus.DISABLED

        registry.enable_plugin("test-plugin")
        meta = registry.list_plugins()[0]
        assert meta.status == PluginStatus.REGISTERED

    def test_disable_nonexistent_raises(self, registry: PluginRegistry) -> None:
        """Verify KeyError when disabling non-existent plugin."""
        with pytest.raises(KeyError):
            registry.disable_plugin("nonexistent")

    @pytest.mark.asyncio
    async def test_initialize_all(self, registry: PluginRegistry) -> None:
        """Verify all plugins are initialized."""
        registry.register_plugin(SimplePlugin())
        registry.register_plugin(AnotherPlugin())

        # Create a minimal context
        from q_guardian.events.bus import EventBus
        from q_guardian.hooks.manager import HookManager

        context = FrameworkContext(
            logger=None,
            config=None,
            event_bus=EventBus(),
            plugin_registry=registry,
            hook_manager=HookManager(),
        )
        await registry.initialize_all(context)

        plugins = registry.list_plugins()
        assert all(p.status == PluginStatus.REGISTERED for p in plugins)

    @pytest.mark.asyncio
    async def test_initialize_failure_marks_error(self, registry: PluginRegistry) -> None:
        """Verify failing plugin gets ERROR status."""
        registry.register_plugin(FailingInitPlugin())

        from q_guardian.events.bus import EventBus
        from q_guardian.hooks.manager import HookManager

        context = FrameworkContext(
            logger=None,
            config=None,
            event_bus=EventBus(),
            plugin_registry=registry,
            hook_manager=HookManager(),
        )
        await registry.initialize_all(context)

        meta = registry.list_plugins()[0]
        assert meta.status == PluginStatus.ERROR

    @pytest.mark.asyncio
    async def test_start_all(self, registry: PluginRegistry) -> None:
        """Verify all initialized plugins are started."""
        registry.register_plugin(SimplePlugin())
        await registry.start_all()

        meta = registry.list_plugins()[0]
        assert meta.status == PluginStatus.RUNNING

    @pytest.mark.asyncio
    async def test_stop_all(self, registry: PluginRegistry) -> None:
        """Verify all running plugins are stopped."""
        registry.register_plugin(SimplePlugin())
        await registry.start_all()
        await registry.stop_all()

        meta = registry.list_plugins()[0]
        assert meta.status == PluginStatus.STOPPED

    @pytest.mark.asyncio
    async def test_health_check(self, registry: PluginRegistry) -> None:
        """Verify health check aggregation."""
        registry.register_plugin(SimplePlugin())
        registry.register_plugin(AnotherPlugin())

        health = await registry.health_check()
        assert "test-plugin" in health
        assert "another-plugin" in health
        assert health["test-plugin"]["status"] == "healthy"
