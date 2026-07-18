"""Base plugin classes for Q-Guardian.

Defines the abstract Plugin interface, PluginMetadata, PluginStatus,
and PluginConfig that all framework plugins must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from q_guardian.framework.context import FrameworkContext


class PluginStatus(str, Enum):
    """Lifecycle status of a plugin."""

    REGISTERED = "registered"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    DISABLED = "disabled"


class PluginMetadata(BaseModel):
    """Metadata describing a plugin.

    Automatically populated from Plugin properties when registered.
    Used by the PluginRegistry and exposed through the SDK.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Unique plugin name")
    version: str = Field(description="Plugin version string")
    author: str = Field(default="", description="Plugin author")
    description: str = Field(default="", description="Plugin description")
    dependencies: list[str] = Field(
        default_factory=list, description="Required plugin names"
    )
    status: PluginStatus = Field(
        default=PluginStatus.REGISTERED, description="Current plugin status"
    )
    interfaces: list[str] = Field(
        default_factory=list,
        description="Interfaces this plugin implements",
    )


class Plugin(ABC):
    """Abstract base class for all Q-Guardian plugins.

    Every plugin must inherit from this class and implement
    the required lifecycle methods. The framework manages
    the full lifecycle automatically.

    Example::

        class MyScanner(Plugin):
            @property
            def name(self) -> str:
                return "my-scanner"

            @property
            def version(self) -> str:
                return "1.0.0"

            async def initialize(self, context: FrameworkContext) -> None:
                self._context = context

            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin name identifier."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version string (semver recommended)."""

    @property
    def author(self) -> str:
        """Plugin author name."""
        return ""

    @property
    def description(self) -> str:
        """Brief description of what the plugin does."""
        return ""

    @property
    def dependencies(self) -> list[str]:
        """List of plugin names this plugin depends on."""
        return []

    @property
    def interfaces(self) -> list[str]:
        """Interfaces this plugin implements.

        Used by the Guardian SDK to route method calls.
        Examples: ["prompt_scanner", "threat_detector"]
        """
        return []

    @abstractmethod
    async def initialize(self, context: FrameworkContext) -> None:
        """Initialize the plugin with framework context.

        Called once after the plugin is registered. Use this to
        set up resources, register event subscriptions, and
        register hooks.

        Args:
            context: The shared framework context.
        """

    @abstractmethod
    async def start(self) -> None:
        """Start the plugin.

        Called after all plugins are initialized. The plugin
        should begin accepting work after this call.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop the plugin.

        Called during framework shutdown. The plugin should
        release resources and stop accepting work.
        """

    def health(self) -> dict[str, Any]:
        """Return plugin health status.

        Override to provide custom health information.

        Returns:
            Dictionary with health status information.
        """
        return {"status": "healthy", "plugin": self.name}

    def configuration(self) -> dict[str, Any]:
        """Return plugin-specific configuration schema.

        Override to advertise configuration options.

        Returns:
            Dictionary describing configuration options.
        """
        return {}

    def metadata(self) -> PluginMetadata:
        """Build metadata from plugin properties.

        Returns:
            PluginMetadata populated from the plugin's properties.
        """
        return PluginMetadata(
            name=self.name,
            version=self.version,
            author=self.author,
            description=self.description,
            dependencies=self.dependencies,
            interfaces=self.interfaces,
        )
