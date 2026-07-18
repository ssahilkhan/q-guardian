"""Database health check utilities for Q-Guardian."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.database.client import get_db_client

logger = structlog.get_logger("database.health")


async def check_database_health() -> dict[str, Any]:
    """Check MongoDB connectivity and return health status.

    Returns:
        Dictionary with database health information.
    """
    try:
        client = get_db_client()
        is_connected = await client.ping()
        if is_connected:
            return {
                "status": "healthy",
                "database": "mongodb",
                "message": "Connection successful",
            }
        return {
            "status": "unhealthy",
            "database": "mongodb",
            "message": "Ping failed",
        }
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "database": "mongodb",
            "message": str(e),
        }
