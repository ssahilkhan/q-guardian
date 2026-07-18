"""Common helper utilities for Q-Guardian."""

from __future__ import annotations

from typing import Any


def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """Mask a sensitive string, showing only the last few characters.

    Args:
        value: The sensitive string to mask.
        visible_chars: Number of characters to leave visible at the end.

    Returns:
        Masked string with asterisks replacing sensitive characters.
    """
    if len(value) <= visible_chars:
        return "*" * len(value)
    masked_length = len(value) - visible_chars
    return "*" * masked_length + value[-visible_chars:]


def chunk_list(items: list[Any], chunk_size: int) -> list[list[Any]]:
    """Split a list into chunks of specified size.

    Args:
        items: The list to split.
        chunk_size: Maximum size of each chunk.

    Returns:
        List of smaller lists.

    Raises:
        ValueError: If chunk_size is less than 1.
    """
    if chunk_size < 1:
        msg = "chunk_size must be at least 1"
        raise ValueError(msg)
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def flatten_list(nested: list[list[Any]]) -> list[Any]:
    """Flatten a nested list into a single list.

    Args:
        nested: The nested list to flatten.

    Returns:
        A single-level list.
    """
    return [item for sublist in nested for item in sublist]


def none_if_empty(value: str | None) -> str | None:
    """Return None if the string is empty or whitespace-only.

    Args:
        value: The string to check.

    Returns:
        The original string or None if empty/whitespace.
    """
    if value is not None and value.strip():
        return value
    return None
