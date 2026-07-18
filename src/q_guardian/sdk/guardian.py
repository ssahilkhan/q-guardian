"""Guardian SDK entry point for Q-Guardian.

Provides the main Guardian class that serves as the facade
for the entire framework. Users interact with this class
to manage plugins, events, hooks, and adapters.
"""

from __future__ import annotations

import structlog
from typing import Any, Callable

from q_guardian.adapters.base import Adapter
from q_guardian.core.framework_state import FrameworkState, FrameworkStateMachine
from q_guardian.events.base import Event, EventHandler
from q_guardian.events.bus import EventBus
from q_guardian.framework.config import FrameworkConfig
from q_guardian.framework.context import FrameworkContext
from q_guardian.hooks.manager import HookManager
from q_guardian.plugins.base import Plugin, PluginMetadata
from q_guardian.plugins.registry import PluginRegistry
from q_guardian.runtime.context import RuntimeContext
from q_guardian.runtime.managers import (
    MemoryTracker,
    RequestManager,
    SessionManager,
    ToolExecutionTracker,
)
from q_guardian.runtime.models import Agent, AgentSession
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("sdk.guardian")


class Guardian:
    """Main entry point for the Q-Guardian security framework.

    The Guardian class is a Facade that provides a clean public API
    for managing the framework lifecycle, plugins, events, hooks,
    and adapters.

    Example::

        from q_guardian import Guardian

        guardian = Guardian()
        await guardian.start()
        # ... framework is running ...
        await guardian.shutdown()

    Example with plugins::

        guardian = Guardian()
        await guardian.start()
        guardian.register_plugin(MySecurityPlugin())
        await guardian.shutdown()
    """

    def __init__(self, config: FrameworkConfig | None = None) -> None:
        """Initialize the Guardian framework.

        Args:
            config: Optional framework configuration. If None,
                    default configuration is used.
        """
        self._config = config or FrameworkConfig()
        self._state_machine = FrameworkStateMachine()
        self._event_bus = EventBus()
        self._plugin_registry = PluginRegistry()
        self._hook_manager = HookManager()
        self._adapters: dict[str, Adapter] = {}
        self._context: FrameworkContext | None = None

        # Runtime managers
        self._session_manager = SessionManager()
        self._request_manager = RequestManager()
        self._tool_tracker = ToolExecutionTracker()
        self._memory_tracker = MemoryTracker()

        # Current runtime state
        self._current_agent: Agent | None = None
        self._current_session: AgentSession | None = None
        self._runtime_context: RuntimeContext | None = None

    @property
    def state(self) -> FrameworkState:
        """Return the current framework state."""
        return self._state_machine.state

    @property
    def events(self) -> EventBus:
        """Access the event bus directly."""
        return self._event_bus

    @property
    def plugins(self) -> PluginRegistry:
        """Access the plugin registry directly."""
        return self._plugin_registry

    @property
    def config(self) -> FrameworkConfig:
        """Access the framework configuration."""
        return self._config

    @property
    def runtime(self) -> RuntimeContext | None:
        """Access the current runtime context.

        Returns:
            The RuntimeContext if the framework is running, None otherwise.
        """
        return self._runtime_context

    @property
    def current_agent(self) -> Agent | None:
        """Return the currently active agent."""
        return self._current_agent

    @property
    def current_session(self) -> AgentSession | None:
        """Return the currently active session."""
        return self._current_session

    @property
    def session_manager(self) -> SessionManager:
        """Access the session manager directly."""
        return self._session_manager

    @property
    def request_manager(self) -> RequestManager:
        """Access the request manager directly."""
        return self._request_manager

    @property
    def tool_tracker(self) -> ToolExecutionTracker:
        """Access the tool execution tracker directly."""
        return self._tool_tracker

    @property
    def memory_tracker(self) -> MemoryTracker:
        """Access the memory tracker directly."""
        return self._memory_tracker

    def get_context(self) -> FrameworkContext | None:
        """Get the current framework context.

        Returns:
            The FrameworkContext, or None if the framework hasn't started.
        """
        return self._context

    async def start(self) -> None:
        """Start the Q-Guardian framework.

        Performs the full startup sequence:
        1. Transitions to INITIALIZING
        2. Creates the FrameworkContext
        3. Discovers plugins (if auto_discover is enabled)
        4. Initializes all plugins
        5. Starts all plugins
        6. Transitions to RUNNING
        7. Publishes FrameworkStarted event

        Raises:
            StateTransitionError: If the framework is not in a valid
                state for starting.
        """
        self._state_machine.transition_to(FrameworkState.INITIALIZING)

        self._context = FrameworkContext(
            logger=logger,
            config=self._config,
            event_bus=self._event_bus,
            plugin_registry=self._plugin_registry,
            hook_manager=self._hook_manager,
            session_id=generate_uuid(),
        )

        self._state_machine.transition_to(FrameworkState.STARTING)

        if self._config.plugins.enabled:
            self._discover_and_register_plugins()

        await self._plugin_registry.initialize_all(self._context)
        await self._plugin_registry.start_all()

        self._state_machine.transition_to(FrameworkState.RUNNING)

        self._update_runtime_context()

        from q_guardian.events.standard import FrameworkStarted

        await self._event_bus.publish(
            FrameworkStarted(
                source="guardian",
                data={"session_id": self._context.session_id},
            )
        )

        logger.info(
            "guardian_started",
            session_id=self._context.session_id,
            plugins=len(self._plugin_registry.list_plugins()),
        )

    async def shutdown(self) -> None:
        """Shut down the Q-Guardian framework.

        Performs the shutdown sequence:
        1. Transitions to STOPPING
        2. Publishes FrameworkStopped event
        3. Stops all plugins in reverse order
        4. Clears event bus
        5. Transitions to STOPPED

        If the framework is not running, this is a no-op.
        """
        if self._state_machine.state not in (
            FrameworkState.RUNNING,
            FrameworkState.ERROR,
        ):
            return

        self._state_machine.transition_to(FrameworkState.STOPPING)

        from q_guardian.events.standard import FrameworkStopped

        await self._event_bus.publish(
            FrameworkStopped(source="guardian", data={})
        )

        await self._plugin_registry.stop_all()
        await self._event_bus.clear()
        await self._hook_manager.clear()

        self._state_machine.transition_to(FrameworkState.STOPPED)
        logger.info("guardian_shutdown")

    # ------------------------------------------------------------------
    # Plugin Management
    # ------------------------------------------------------------------

    def register_plugin(self, plugin: Plugin) -> None:
        """Register a plugin with the framework.

        Args:
            plugin: The plugin instance to register.
        """
        self._plugin_registry.register_plugin(plugin)

    def unregister_plugin(self, name: str) -> None:
        """Unregister a plugin by name.

        Args:
            name: The plugin name to remove.
        """
        self._plugin_registry.unregister_plugin(name)

    def enable_plugin(self, name: str) -> None:
        """Enable a registered plugin.

        Args:
            name: The plugin name.
        """
        self._plugin_registry.enable_plugin(name)

    def disable_plugin(self, name: str) -> None:
        """Disable a registered plugin.

        Args:
            name: The plugin name.
        """
        self._plugin_registry.disable_plugin(name)

    def list_plugins(self) -> list[PluginMetadata]:
        """List all registered plugins.

        Returns:
            List of plugin metadata objects.
        """
        return self._plugin_registry.list_plugins()

    def get_plugin(self, name: str) -> Plugin:
        """Get a plugin by name.

        Args:
            name: The plugin name.

        Returns:
            The plugin instance.

        Raises:
            KeyError: If the plugin is not registered.
        """
        return self._plugin_registry.get_plugin(name)

    # ------------------------------------------------------------------
    # Event System
    # ------------------------------------------------------------------

    async def publish(self, event: Event) -> Event:
        """Publish an event to the event bus.

        Args:
            event: The event to publish.

        Returns:
            The published event after handler processing.
        """
        return await self._event_bus.publish(event)

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        priority: int = 0,
    ) -> int:
        """Subscribe a handler to an event type.

        Args:
            event_type: The event type to subscribe to.
            handler: The async handler callable.
            priority: Handler execution priority.

        Returns:
            Subscription ID for later unsubscribe.
        """
        return await self._event_bus.subscribe(event_type, handler, priority)

    async def unsubscribe(self, subscription_id: int) -> bool:
        """Unsubscribe a handler.

        Args:
            subscription_id: The subscription ID from subscribe().

        Returns:
            True if the subscription was removed.
        """
        return await self._event_bus.unsubscribe(subscription_id)

    # ------------------------------------------------------------------
    # Hook System
    # ------------------------------------------------------------------

    async def register_hook(
        self,
        hook_name: str,
        handler: Callable[..., Any],
    ) -> None:
        """Register a lifecycle hook handler.

        Args:
            hook_name: The hook point name.
            handler: The callable to execute at this hook point.
        """
        await self._hook_manager.register_hook(hook_name, handler)

    async def execute_hook(self, hook_name: str, **kwargs: Any) -> dict[str, Any]:
        """Execute all handlers for a named hook.

        Args:
            hook_name: The hook point name.
            **kwargs: Arguments passed to handlers.

        Returns:
            The merged context dictionary.
        """
        return await self._hook_manager.execute_hook(hook_name, **kwargs)

    # ------------------------------------------------------------------
    # Adapter Management
    # ------------------------------------------------------------------

    def register_adapter(self, adapter: Adapter) -> None:
        """Register an AI framework adapter.

        Args:
            adapter: The adapter instance.
        """
        self._adapters[adapter.name] = adapter
        logger.info("adapter_registered", adapter_name=adapter.name)

    def get_adapter(self, name: str) -> Adapter:
        """Get an adapter by name.

        Args:
            name: The adapter name.

        Returns:
            The adapter instance.

        Raises:
            KeyError: If the adapter is not registered.
        """
        if name not in self._adapters:
            msg = f"Adapter '{name}' is not registered"
            raise KeyError(msg)
        return self._adapters[name]

    # ------------------------------------------------------------------
    # Convenience Methods (Plugin Dispatch)
    # ------------------------------------------------------------------

    async def scan_prompt(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Scan a prompt through registered prompt scanners.

        Executes the 'before_prompt' hook, dispatches to plugins
        implementing 'prompt_scanner', executes 'after_prompt' hook,
        and publishes events.

        Args:
            prompt: The prompt text to scan.
            **kwargs: Additional context for scanning.

        Returns:
            Aggregated scan results from all scanners.
        """
        from q_guardian.events.standard import AfterPrompt, BeforePrompt

        await self._hook_manager.execute_hook("before_prompt", prompt=prompt, **kwargs)

        await self._event_bus.publish(
            BeforePrompt(
                source="guardian",
                data={"prompt": prompt, **kwargs},
            )
        )

        scanners = self._plugin_registry.get_plugins_by_interface("prompt_scanner")
        results: dict[str, Any] = {}
        for scanner in scanners:
            if hasattr(scanner, "scan_prompt"):
                try:
                    result = await scanner.scan_prompt(prompt, **kwargs)
                    results[scanner.name] = result
                except Exception:
                    logger.error(
                        "scanner_error",
                        plugin=scanner.name,
                        exc_info=True,
                    )

        context = await self._hook_manager.execute_hook(
            "after_prompt", prompt=prompt, results=results, **kwargs
        )

        await self._event_bus.publish(
            AfterPrompt(
                source="guardian",
                data={"prompt": prompt, "results": results},
            )
        )

        return context.get("results", results)

    async def monitor(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Monitor runtime activity through registered monitors.

        Args:
            event_data: Runtime event data to monitor.

        Returns:
            Aggregated monitoring results.
        """
        monitors = self._plugin_registry.get_plugins_by_interface("runtime_monitor")
        results: dict[str, Any] = {}
        for monitor in monitors:
            if hasattr(monitor, "monitor"):
                try:
                    result = await monitor.monitor(event_data)
                    results[monitor.name] = result
                except Exception:
                    logger.error(
                        "monitor_error",
                        plugin=monitor.name,
                        exc_info=True,
                    )
        return results

    async def calculate_risk(self, data: dict[str, Any]) -> dict[str, Any]:
        """Calculate risk through registered risk engines.

        Args:
            data: Data to assess for risk.

        Returns:
            Aggregated risk assessment results.
        """
        engines = self._plugin_registry.get_plugins_by_interface("risk_engine")
        results: dict[str, Any] = {}
        for engine in engines:
            if hasattr(engine, "calculate_risk"):
                try:
                    result = await engine.calculate_risk(data)
                    results[engine.name] = result
                except Exception:
                    logger.error(
                        "risk_calculation_error",
                        plugin=engine.name,
                        exc_info=True,
                    )
        return results

    async def enforce_policy(self, data: dict[str, Any]) -> dict[str, Any]:
        """Enforce policies through registered policy engines.

        Args:
            data: Data to check against policies.

        Returns:
            Aggregated policy enforcement results.
        """
        engines = self._plugin_registry.get_plugins_by_interface("policy_engine")
        results: dict[str, Any] = {}
        for engine in engines:
            if hasattr(engine, "enforce_policy"):
                try:
                    result = await engine.enforce_policy(data)
                    results[engine.name] = result
                except Exception:
                    logger.error(
                        "policy_enforcement_error",
                        plugin=engine.name,
                        exc_info=True,
                    )
        return results

    # ------------------------------------------------------------------
    # Runtime Management
    # ------------------------------------------------------------------

    async def create_session(
        self,
        agent_id: str = "",
        conversation_id: str = "",
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AgentSession:
        """Create a new runtime session.

        Creates a session, links it to the current agent if set,
        and updates the runtime context.

        Args:
            agent_id: Agent that owns this session. If empty,
                      uses the current agent's ID.
            conversation_id: Optional conversation identifier.
            user_id: Optional end-user identifier.
            metadata: Optional session metadata.

        Returns:
            The newly created session.
        """
        if not agent_id and self._current_agent:
            agent_id = self._current_agent.id

        session = await self._session_manager.create_session(
            agent_id=agent_id,
            conversation_id=conversation_id,
            user_id=user_id,
            metadata=metadata,
        )
        self._current_session = session
        self._update_runtime_context()

        from q_guardian.runtime.events import SessionStarted

        await self._event_bus.publish(
            SessionStarted(
                source="guardian",
                data={"session_id": session.session_id, "agent_id": agent_id},
            )
        )
        return session

    async def close_session(self) -> bool:
        """Close the current runtime session.

        Returns:
            True if a session was closed, False if no session was active.
        """
        if self._current_session is None:
            return False

        session_id = self._current_session.session_id
        closed = await self._session_manager.close_session(session_id)

        if closed:
            from q_guardian.runtime.events import SessionEnded

            await self._event_bus.publish(
                SessionEnded(
                    source="guardian",
                    data={"session_id": session_id},
                )
            )

        self._current_session = None
        self._update_runtime_context()
        return closed

    def set_agent(self, agent: Agent) -> None:
        """Set the current active agent.

        Activates the agent and updates the runtime context.

        Args:
            agent: The agent to set as current.
        """
        if self._current_agent and self._current_agent.id != agent.id:
            self._current_agent.deactivate()

        agent.activate()
        self._current_agent = agent
        self._update_runtime_context()

    def get_runtime_context(self) -> RuntimeContext | None:
        """Get the current runtime context.

        Returns:
            The RuntimeContext, or None if not initialized.
        """
        return self._runtime_context

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_runtime_context(self) -> None:
        """Update the runtime context with current state."""
        self._runtime_context = RuntimeContext(
            current_agent=self._current_agent,
            current_session=self._current_session,
            framework_context=self._context,
        )

    def _discover_and_register_plugins(self) -> None:
        """Discover and register plugins from entry points."""
        discovered = PluginRegistry.discover_plugins()
        for plugin in discovered:
            try:
                if not self._plugin_registry.has_plugin(plugin.name):
                    self._plugin_registry.register_plugin(plugin)
            except Exception:
                logger.warning(
                    "plugin_auto_registration_failed",
                    plugin_name=plugin.name,
                    exc_info=True,
                )
