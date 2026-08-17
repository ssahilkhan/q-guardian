"""System endpoints for Q-Guardian.

Provides version, status, and system information endpoints.
"""

from __future__ import annotations

import platform
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Request

from q_guardian.config.settings import get_settings
from q_guardian.database.health import check_database_health
from q_guardian.schemas.base import ResponseSchema, VersionResponseSchema

logger = structlog.get_logger("api.system")

router = APIRouter()


@router.get("/version", response_model=ResponseSchema[VersionResponseSchema])
async def get_version(request: Request) -> ResponseSchema[VersionResponseSchema]:
    """Get application version and system information.

    Returns:
        ResponseSchema containing version details and environment info.
    """
    settings = get_settings()
    version_data = VersionResponseSchema(
        application=settings.app.name,
        version=settings.app.version,
        environment=settings.app.environment.value,
        python_version=platform.python_version(),
        timestamp=datetime.now(UTC),
    )
    return ResponseSchema(
        success=True,
        message="Version information retrieved successfully",
        data=version_data,
    )


@router.get("/status", response_model=ResponseSchema[dict[str, Any]])
async def get_status(request: Request) -> ResponseSchema[dict[str, Any]]:
    """Get the real current application status.

    Status is derived from live dependency health (MongoDB ping). It is
    ``operational`` only when every checked dependency is healthy, and
    ``degraded`` otherwise. Dependency failures are surfaced in the
    ``database`` block — never hidden or suppressed.

    Returns:
        ResponseSchema containing the operational status and the
        underlying dependency health snapshot.
    """
    db_health = await check_database_health()
    status = "operational" if db_health["status"] == "healthy" else "degraded"
    return ResponseSchema(
        success=True,
        message=f"Application is {status}",
        data={"status": status, "database": db_health},
    )
