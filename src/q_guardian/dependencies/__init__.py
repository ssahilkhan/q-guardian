"""Dependency injection module for Q-Guardian.

Provides centralized dependency management for FastAPI's
dependency injection system.
"""

from q_guardian.dependencies.container import get_container

__all__ = ["get_container"]
