"""Lifecycle hook manager for Q-Guardian.

Provides a system for plugins to register before/after hooks
at specific points in the framework lifecycle. Hooks execute
in registration order and can modify shared context.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import structlog

logger = structlog.get_logger("hooks.manager")

HookHandler = Callable[..., Any]


class HookManager:
    """Manages lifecycle hooks for the framework.

    Plugins register hooks at named points (e.g., 'before_prompt',
    'after_response'). When the framework reaches that point, it
    executes all registered handlers for that hook.

    Example::

        hook_mgr = HookManager()
        hook_mgr.register_hook("before_prompt", my_validator)
        context = await hook_mgr.execute_hook("before_prompt", prompt="hello")
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookHandler]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def register_hook(
        self,
        hook_name: str,
        handler: HookHandler,
    ) -> None:
        """Register a handler for a named hook.

        Args:
            hook_name: The hook point name (e.g., 'before_prompt').
            handler: The callable to execute at this hook point.
        """
        async with self._lock:
            if hook_name not in self._hooks:
                self._hooks[hook_name] = []
            self._hooks[hook_name].append(handler)
            logger.debug(
                "hook_registered",
                hook_name=hook_name,
                handler=handler.__qualname__,
            )

    async def unregister_hook(
        self,
        hook_name: str,
        handler: HookHandler,
    ) -> bool:
        """Remove a specific handler from a hook point.

        Args:
            hook_name: The hook point name.
            handler: The handler to remove.

        Returns:
            True if the handler was found and removed.
        """
        async with self._lock:
            handlers = self._hooks.get(hook_name, [])
            try:
                handlers.remove(handler)
                if not handlers:
                    del self._hooks[hook_name]
                return True
            except ValueError:
                return False

    async def execute_hook(
        self,
        hook_name: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute all handlers registered for a hook point.

        Each handler receives the current kwargs and can return
        a dict to merge into the context. Handlers execute in
        registration order.

        Args:
            hook_name: The hook point name.
            **kwargs: Arguments passed to each handler.

        Returns:
            The merged context dictionary after all handlers run.
        """
        handlers = list(self._hooks.get(hook_name, []))
        context = dict(kwargs)

        for handler in handlers:
            try:
                import inspect

                if inspect.iscoroutinefunction(handler):
                    result = await handler(**context)
                else:
                    result = handler(**context)

                if isinstance(result, dict):
                    context.update(result)
            except Exception:
                logger.error(
                    "hook_execution_error",
                    hook_name=hook_name,
                    handler=handler.__qualname__,
                    exc_info=True,
                )

        return context

    def list_hooks(self) -> dict[str, int]:
        """List all registered hooks and their handler counts.

        Returns:
            Dictionary mapping hook names to handler counts.
        """
        return {name: len(handlers) for name, handlers in self._hooks.items()}

    async def clear(self) -> None:
        """Remove all registered hooks. Used in testing and shutdown."""
        async with self._lock:
            self._hooks.clear()
