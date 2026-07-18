"""Response Plugin — pluggable response handlers for the Response Engine."""

from __future__ import annotations

from typing import Any, Callable

import structlog

from q_guardian.response.enums import ResponseAction

logger = structlog.get_logger(__name__)


class ResponsePlugin:
    """Base class for response plugins."""

    name: str = "base"
    version: str = "1.0.0"

    def __init__(self) -> None:
        self._initialized = False

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    def can_handle(self, action: ResponseAction) -> bool:
        return False

    def execute(self, action: ResponseAction, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @property
    def is_initialized(self) -> bool:
        return self._initialized


class PluginRegistry:
    """Registry for response plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, ResponsePlugin] = {}
        self._action_handlers: dict[ResponseAction, ResponsePlugin] = {}

    def register(self, plugin: ResponsePlugin, config: dict[str, Any] | None = None) -> None:
        plugin.initialize(config)
        self._plugins[plugin.name] = plugin
        logger.info("plugin_registered", name=plugin.name, version=plugin.version)

    def unregister(self, name: str) -> bool:
        plugin = self._plugins.pop(name, None)
        if plugin:
            plugin.shutdown()
            return True
        return False

    def get(self, name: str) -> ResponsePlugin | None:
        return self._plugins.get(name)

    def bind_action(self, action: ResponseAction, plugin_name: str) -> None:
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            raise ValueError(f"Plugin not found: {plugin_name}")
        self._action_handlers[action] = plugin

    def get_handler(self, action: ResponseAction) -> ResponsePlugin | None:
        return self._action_handlers.get(action)

    def list_plugins(self) -> list[ResponsePlugin]:
        return list(self._plugins.values())

    def count(self) -> int:
        return len(self._plugins)

    def shutdown_all(self) -> None:
        for plugin in self._plugins.values():
            plugin.shutdown()
        self._plugins.clear()
        self._action_handlers.clear()
