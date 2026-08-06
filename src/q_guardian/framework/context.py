"""Framework context for Q-Guardian.

Provides a shared context object that is passed to all plugins
and adapters, giving them access to framework services and state.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.utils.uuid_utils import generate_uuid


class FrameworkContext(BaseModel):
    """Shared context passed to all plugins and adapters.

    Provides access to framework services (event bus, plugin registry,
    hook manager), configuration, logging, and current session state.

    Every plugin receives this context during initialization and
    can use it to interact with the framework.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    logger: Any = Field(description="Structured logger instance")
    config: Any = Field(description="Framework configuration")
    event_bus: Any = Field(description="Event bus instance")
    plugin_registry: Any = Field(description="Plugin registry instance")
    hook_manager: Any = Field(description="Hook manager instance")
    database: Any = Field(default=None, description="Database connection (optional)")
    session_id: str = Field(default_factory=generate_uuid, description="Current session identifier")
    current_request: dict[str, Any] | None = Field(default=None, description="Current request data")
    current_agent: dict[str, Any] | None = Field(default=None, description="Current agent data")
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional context data")

    def create_child_context(self, **overrides: Any) -> FrameworkContext:
        """Create a child context with overridden fields.

        Creates a copy of the context with specified fields replaced.
        Useful for request-scoped or agent-scoped contexts.

        Args:
            **overrides: Fields to override in the child context.

        Returns:
            A new FrameworkContext with the overrides applied.
        """
        current_values = {
            "logger": self.logger,
            "config": self.config,
            "event_bus": self.event_bus,
            "plugin_registry": self.plugin_registry,
            "hook_manager": self.hook_manager,
            "database": self.database,
            "session_id": self.session_id,
            "current_request": self.current_request,
            "current_agent": self.current_agent,
            "extra": dict(self.extra),
        }
        current_values.update(overrides)
        return FrameworkContext(**current_values)
