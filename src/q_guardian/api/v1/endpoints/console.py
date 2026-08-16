"""Console endpoints for the Q-Guardian web console.

Read-only inventory and configuration views (rules, models, components,
sanitized configuration, and overview summary) consumed by the console UI.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request

from q_guardian.api.services.analysis import get_analysis_service
from q_guardian.schemas.base import ResponseSchema

logger = structlog.get_logger("api.console")

router = APIRouter()

service = get_analysis_service()


@router.get("/rules", response_model=ResponseSchema[list[dict[str, Any]]])
async def list_rules(request: Request) -> ResponseSchema[list[dict[str, Any]]]:
    """List the active detection rules.

    Args:
        request: Incoming request.

    Returns:
        The rule catalog from the pipeline's rule engine.
    """
    rules = service.rules()
    return ResponseSchema(
        success=True,
        message=f"{len(rules)} rule(s) retrieved",
        data=rules,
    )


@router.get("/models", response_model=ResponseSchema[dict[str, Any]])
async def models_status(request: Request) -> ResponseSchema[dict[str, Any]]:
    """Return ML model and quantum backend status.

    Args:
        request: Incoming request.

    Returns:
        Model registry status and quantum backend availability.
    """
    status = service.models_status()
    return ResponseSchema(
        success=True,
        message="Model and backend status retrieved successfully",
        data=status,
    )


@router.get("/components", response_model=ResponseSchema[list[dict[str, Any]]])
async def components(request: Request) -> ResponseSchema[list[dict[str, Any]]]:
    """Return the pipeline stage inventory.

    Args:
        request: Incoming request.

    Returns:
        Pipeline stages with live availability status.
    """
    stages = service.components()
    return ResponseSchema(
        success=True,
        message=f"{len(stages)} component(s) retrieved",
        data=stages,
    )


@router.get("/configuration", response_model=ResponseSchema[dict[str, Any]])
async def configuration(request: Request) -> ResponseSchema[dict[str, Any]]:
    """Return a sanitized view of the application configuration.

    Secrets (secret keys, tokens, passwords, raw credentialed URLs) and
    internal filesystem paths are never exposed.

    Args:
        request: Incoming request.

    Returns:
        Redacted configuration grouped by category.
    """
    config = service.configuration()
    return ResponseSchema(
        success=True,
        message="Configuration retrieved successfully",
        data=config,
    )


@router.get("/summary", response_model=ResponseSchema[dict[str, Any]])
async def summary(request: Request) -> ResponseSchema[dict[str, Any]]:
    """Return overview aggregates for the console landing page.

    Args:
        request: Incoming request.

    Returns:
        Component, rule, model and history aggregates.
    """
    data = service.summary()
    return ResponseSchema(
        success=True,
        message="Summary retrieved successfully",
        data=data,
    )


@router.get("/research", response_model=ResponseSchema[dict[str, Any]])
async def research(request: Request) -> ResponseSchema[dict[str, Any]]:
    """Return a read-only snapshot of research artifacts on disk.

    Reads existing datasets, trained model storage, evaluation reports,
    benchmark suites and load-test results. Nothing is re-run and no
    binary model contents are deserialized.

    Args:
        request: Incoming request.

    Returns:
        Bounded, structured research artifact inventory.
    """
    data = service.research()
    return ResponseSchema(
        success=True,
        message="Research artifacts retrieved successfully",
        data=data,
    )
