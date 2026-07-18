"""Datetime utilities for Q-Guardian."""

from __future__ import annotations

from datetime import UTC, datetime


def get_utc_now() -> datetime:
    """Get the current UTC datetime with timezone info.

    Returns:
        Current UTC datetime.
    """
    return datetime.now(UTC)


def utc_timestamp() -> float:
    """Get current UTC timestamp as a Unix float.

    Returns:
        Unix timestamp float.
    """
    return get_utc_now().timestamp()


def get_current_timestamp() -> str:
    """Get current UTC time as an ISO 8601 string.

    Returns:
        ISO 8601 formatted timestamp string.
    """
    return get_utc_now().isoformat()


def to_iso_format(dt: datetime) -> str:
    """Convert a datetime object to ISO 8601 string.

    Args:
        dt: The datetime to convert.

    Returns:
        ISO 8601 formatted string.
    """
    return dt.isoformat()
