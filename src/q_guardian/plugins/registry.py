"""Plugin registry for Q-Guardian.

Manages the registration, lifecycle, and discovery of framework plugins.
Supports pip-installable plugin discovery via entry points.
"""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.exceptions.base import ValidationException
from q_guardian.plugins.base import Plugin, PluginMetadata, PluginStatus

if TYPE_CHECKING:
    from q_guardian.framework.context import FrameworkContext

logger = structlog.get_logger("plugins.registry")


class PluginRegistry:
    """Central registry for framework plugins.

    Manages the full lifecycle of plugins: registration, initialization,
    starting, stopping, and health checking. Supports plugin discovery
    through Python entry points for pip-installable plugins.

    Example::

        registry = PluginRegistry()
        registry.register_plugin(MyPlugin())
        await registry.initialize_all(context)
        await registry.start_all()
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._metadata: dict[str, PluginMetadata] = {}

    def register_plugin(self, plugin: Plugin) -> None:
        """Register a plugin with the registry.

        Args:
            plugin: The plugin instance to register.

        Raises:
            ValidationException: If a plugin with the same name is registered.
        """
        meta = plugin.metadata()
        if meta.name in self._plugins:
            raise ValidationException(
                message=f"Plugin '{meta.name}' is already registered",
                details={"plugin_name": meta.name},
            )

        self._plugins[meta.name] = plugin
        self._metadata[meta.name] = meta
        logger.info(
            "plugin_registered",
            plugin_name=meta.name,
            version=meta.version,
        )

    def unregister_plugin(self, name: str) -> None:
        """Remove a plugin from the registry.

        Args:
            name: The plugin name to remove.
        """
        self._plugins.pop(name, None)
        self._metadata.pop(name, None)
        logger.info("plugin_unregistered", plugin_name=name)

    def get_plugin(self, name: str) -> Plugin:
        """Get a registered plugin by name.

        Args:
            name: The plugin name.

        Returns:
            The plugin instance.

        Raises:
            KeyError: If the plugin is not registered.
        """
        if name not in self._plugins:
            msg = f"Plugin '{name}' is not registered"
            raise KeyError(msg)
        return self._plugins[name]

    def has_plugin(self, name: str) -> bool:
        """Check if a plugin is registered.

        Args:
            name: The plugin name.

        Returns:
            True if the plugin is registered.
        """
        return name in self._plugins

    def get_plugins_by_interface(self, interface: str) -> list[Plugin]:
        """Get all plugins that implement a specific interface.

        Args:
            interface: The interface identifier (e.g., "prompt_scanner").

        Returns:
            List of plugins implementing the interface.
        """
        return [
            plugin
            for plugin in self._plugins.values()
            if interface in plugin.interfaces
        ]

    def list_plugins(
        self, status: PluginStatus | None = None
    ) -> list[PluginMetadata]:
        """List registered plugins, optionally filtered by status.

        Args:
            status: If provided, only return plugins with this status.

        Returns:
            List of plugin metadata objects.
        """
        plugins = list(self._metadata.values())
        if status is not None:
            plugins = [p for p in plugins if p.status == status]
        return plugins

    def enable_plugin(self, name: str) -> None:
        """Enable a registered plugin.

        Args:
            name: The plugin name.

        Raises:
            KeyError: If the plugin is not registered.
        """
        if name not in self._metadata:
            msg = f"Plugin '{name}' is not registered"
            raise KeyError(msg)
        self._metadata[name].status = PluginStatus.REGISTERED
        logger.info("plugin_enabled", plugin_name=name)

    def disable_plugin(self, name: str) -> None:
        """Disable a registered plugin.

        Disabled plugins are not initialized or started.

        Args:
            name: The plugin name.

        Raises:
            KeyError: If the plugin is not registered.
        """
        if name not in self._metadata:
            msg = f"Plugin '{name}' is not registered"
            raise KeyError(msg)
        self._metadata[name].status = PluginStatus.DISABLED
        logger.info("plugin_disabled", plugin_name=name)

    async def initialize_all(self, context: FrameworkContext) -> None:
        """Initialize all registered and enabled plugins.

        Plugins are initialized in dependency order. If a plugin
        fails to initialize, it is marked as ERROR and remaining
        plugins continue.

        Args:
            context: The shared framework context.
        """
        for name, plugin in self._plugins.items():
            meta = self._metadata[name]
            if meta.status == PluginStatus.DISABLED:
                logger.debug("plugin_skip_disabled", plugin_name=name)
                continue

            meta.status = PluginStatus.INITIALIZING
            try:
                await plugin.initialize(context)
                meta.status = PluginStatus.REGISTERED
                logger.info("plugin_initialized", plugin_name=name)
            except Exception:
                meta.status = PluginStatus.ERROR
                logger.error(
                    "plugin_initialization_failed",
                    plugin_name=name,
                    exc_info=True,
                )

    async def start_all(self) -> None:
        """Start all initialized plugins.

        Plugins are started in registration order. If a plugin
        fails to start, it is marked as ERROR and remaining
        plugins continue.
        """
        for name, plugin in self._plugins.items():
            meta = self._metadata[name]
            if meta.status in (PluginStatus.DISABLED, PluginStatus.ERROR):
                continue

            try:
                await plugin.start()
                meta.status = PluginStatus.RUNNING
                logger.info("plugin_started", plugin_name=name)
            except Exception:
                meta.status = PluginStatus.ERROR
                logger.error(
                    "plugin_start_failed",
                    plugin_name=name,
                    exc_info=True,
                )

    async def stop_all(self) -> None:
        """Stop all running plugins in reverse registration order.

        Errors during stop are logged but do not prevent other
        plugins from stopping.
        """
        plugin_list = list(self._plugins.items())
        for name, plugin in reversed(plugin_list):
            meta = self._metadata[name]
            if meta.status != PluginStatus.RUNNING:
                continue

            try:
                await plugin.stop()
                meta.status = PluginStatus.STOPPED
                logger.info("plugin_stopped", plugin_name=name)
            except Exception:
                meta.status = PluginStatus.ERROR
                logger.error(
                    "plugin_stop_failed",
                    plugin_name=name,
                    exc_info=True,
                )

    async def health_check(self) -> dict[str, dict[str, Any]]:
        """Check health of all registered plugins.

        Returns:
            Dictionary mapping plugin names to their health status.
        """
        results: dict[str, dict[str, Any]] = {}
        for name, plugin in self._plugins.items():
            try:
                results[name] = plugin.health()
            except Exception:
                results[name] = {"status": "error", "plugin": name}
        return results

    @staticmethod
    def discover_plugins(
        group: str = "q_guardian.plugins",
    ) -> list[Plugin]:
        """Discover plugins registered via Python entry points.

        Plugins can register themselves by adding an entry point
        in their pyproject.toml:

            [project.entry-points."q_guardian.plugins"]
            my_plugin = "my_package:MyPlugin"

        Args:
            group: The entry point group name.

        Returns:
            List of discovered plugin instances.
        """
        discovered: list[Plugin] = []
        try:
            eps = importlib.metadata.entry_points()
            plugin_eps = eps.select(group=group) if hasattr(eps, "select") else []

            for ep in plugin_eps:
                try:
                    plugin_class = ep.load()
                    if isinstance(plugin_class, type) and issubclass(plugin_class, Plugin):
                        discovered.append(plugin_class())
                        logger.info(
                            "plugin_discovered",
                            name=ep.name,
                            entry_point=str(ep),
                        )
                except Exception:
                    logger.error(
                        "plugin_discovery_failed",
                        name=ep.name,
                        exc_info=True,
                    )
        except Exception:
            logger.warning("plugin_discovery_unavailable", exc_info=True)

        return discovered
