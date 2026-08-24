"""Database health check utilities for Q-Guardian."""

from __future__ import annotations

import time
from typing import Any

import structlog

from q_guardian.database.client import get_db_client

logger = structlog.get_logger("database.health")

# Cache window for health probe results. Load balancers and container
# healthchecks poll this endpoint frequently; when MongoDB is unreachable a
# live ping can stall for serverSelectionTimeoutMS (~20s), so repeated probes
# within this window reuse the last verified result instead.
_CACHE_TTL_SECONDS = 5.0

_health_cache: dict[str, Any] | None = None


def reset_database_health_cache() -> None:
    """Clear the cached health result. Intended for tests."""
    global _health_cache
    _health_cache = None


async def check_database_health(*, force: bool = False) -> dict[str, Any]:
    """Check MongoDB connectivity and return health status.

    Results are cached for ``_CACHE_TTL_SECONDS`` to keep probes fast and to
    avoid hammering an unreachable database. Pass ``force=True`` to bypass
    the cache.

    Returns:
        Dictionary with database health information.
    """
    global _health_cache
    now = time.monotonic()
    if (
        not force
        and _health_cache is not None
        and (now - _health_cache["checked_at"]) < _CACHE_TTL_SECONDS
    ):
        logger.debug("database_health_cache_hit")
        cached: dict[str, Any] = _health_cache["result"]
        return cached
    try:
        client = get_db_client()
        is_connected = await client.ping()
        if is_connected:
            result: dict[str, Any] = {
                "status": "healthy",
                "database": "mongodb",
                "message": "Connection successful",
            }
        else:
            result = {
                "status": "unhealthy",
                "database": "mongodb",
                "message": "Ping failed",
            }
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        result = {
            "status": "unhealthy",
            "database": "mongodb",
            "message": str(e),
        }
    _health_cache = {"checked_at": now, "result": result}
    return result
