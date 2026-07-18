"""Plugin system for Q-Guardian.

Provides the Plugin ABC, plugin metadata, status tracking,
and the PluginRegistry for managing plugin lifecycle.
"""

from q_guardian.plugins.base import Plugin, PluginMetadata, PluginStatus
from q_guardian.plugins.registry import PluginRegistry

__all__ = [
    "Plugin",
    "PluginMetadata",
    "PluginRegistry",
    "PluginStatus",
]
