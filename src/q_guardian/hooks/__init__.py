"""Hook system for Q-Guardian.

Provides lifecycle hook management for plugins to intercept
and modify framework processing at defined hook points.
"""

from q_guardian.hooks.manager import HookManager

__all__ = ["HookManager"]
