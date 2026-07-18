"""Health check endpoint for Q-Guardian.

Provides liveness and readiness probes for monitoring.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Request

from q_guardian.config.settings import get_settings
from q_guardian.database.health import check_database_health
from q_guardian.schemas.base import HealthResponseSchema

logger = structlog.get_logger("api.health")

router = APIRouter()


@router.get("", response_model=HealthResponseSchema)
@router.get("/", response_model=HealthResponseSchema)
async def health_check(request: Request) -> HealthResponseSchema:
    """Perform a health check.

    Returns application status, version, environment, and database health.
    Used as a liveness probe for container orchestrators.

    Returns:
        HealthResponseSchema with comprehensive health information.
    """
    settings = get_settings()
    db_health = await check_database_health()

    overall_status = "healthy" if db_health["status"] == "healthy" else "degraded"

    return HealthResponseSchema(
        status=overall_status,
        application=settings.app.name,
        version=settings.app.version,
        environment=settings.app.environment.value,
        timestamp=datetime.now(UTC),
        database=db_health,
    )
