"""Analytics endpoints for the product workflow.

Aggregate numbers over persisted artifacts (dashboard summary) and cross-dataset
analytics over saved report JSON files, both computed from real metrics only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, HTTPException, Request

from q_guardian.api.services import analytics_service
from q_guardian.schemas.base import ResponseSchema
from q_guardian.schemas.product import CrossAnalyticsRequest

if TYPE_CHECKING:
    from q_guardian.schemas.product import CrossAnalyticsRequest

logger = structlog.get_logger("api.analytics")

router = APIRouter()


@router.get("/summary", response_model=ResponseSchema[dict[str, Any]])
async def analytics_summary(request: Request) -> ResponseSchema[dict[str, Any]]:
    """Return the aggregated dashboard summary over persisted artifacts."""
    summary = analytics_service.summary()
    return ResponseSchema(
        success=True,
        message="Analytics summary computed",
        data=summary,
    )


@router.post("/cross", response_model=ResponseSchema[dict[str, Any]])
async def cross_analytics(
    request: Request, payload: CrossAnalyticsRequest
) -> ResponseSchema[dict[str, Any]]:
    """Run cross-dataset analytics over previously saved report JSON files."""
    try:
        report = analytics_service.cross(payload.files, mode=payload.mode, strict=payload.strict)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseSchema(
        success=True,
        message="Cross-dataset analysis completed",
        data=report,
    )
