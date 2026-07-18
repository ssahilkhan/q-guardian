"""UUID generation utilities for Q-Guardian."""

from __future__ import annotations

import uuid


def generate_uuid() -> str:
    """Generate a new UUID v4 string.

    Returns:
        A lowercase UUID v4 string.
    """
    return str(uuid.uuid4())


def generate_correlation_id() -> str:
    """Generate a short correlation ID for request tracing.

    Uses UUID v4 but truncates to 12 characters for readability
    in logs and headers while maintaining sufficient uniqueness.

    Returns:
        A 12-character truncated UUID string.
    """
    return uuid.uuid4().hex[:12]
