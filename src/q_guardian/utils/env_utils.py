"""Environment detection utilities for Q-Guardian."""

from __future__ import annotations

import os


def get_environment() -> str:
    """Get the current environment name.

    Returns:
        The ENVIRONMENT variable value, defaults to 'development'.
    """
    return os.getenv("ENVIRONMENT", "development").lower()


def is_development() -> bool:
    """Check if running in development environment.

    Returns:
        True if ENVIRONMENT is 'development'.
    """
    return get_environment() == "development"


def is_testing() -> bool:
    """Check if running in testing environment.

    Returns:
        True if ENVIRONMENT is 'testing'.
    """
    return get_environment() == "testing"


def is_production() -> bool:
    """Check if running in production environment.

    Returns:
        True if ENVIRONMENT is 'production'.
    """
    return get_environment() == "production"


def get_env_variable(key: str, default: str = "") -> str:
    """Safely retrieve an environment variable.

    Args:
        key: The environment variable name.
        default: Fallback value if the variable is not set.

    Returns:
        The environment variable value or the default.
    """
    return os.getenv(key, default)
