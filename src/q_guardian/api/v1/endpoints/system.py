"""System endpoints for Q-Guardian.

Provides version, status, and system information endpoints.
"""

from __future__ import annotations

import platform
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Request

from q_guardian.config.settings import get_settings
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


@router.get("/status", response_model=ResponseSchema[dict[str, str]])
async def get_status(request: Request) -> ResponseSchema[dict[str, str]]:
    """Get application status.

    Returns:
        ResponseSchema indicating the application is operational.
    """
    return ResponseSchema(
        success=True,
        message="Application is operational",
        data={"status": "operational"},
    )
