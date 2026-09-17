"""Report endpoints for the product workflow.

Inventory generated report artifacts, generate new ones from real persisted
sources, and download their content. All logic lives in
:mod:`q_guardian.api.services.reporting_service` — this module only maps HTTP
contracts onto it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, Response

from q_guardian.api.services import reporting_service
from q_guardian.schemas.base import ResponseSchema
from q_guardian.schemas.product import GenerateReportRequest

if TYPE_CHECKING:
    from q_guardian.schemas.product import GenerateReportRequest

logger = structlog.get_logger("api.reports")

router = APIRouter()

_MEDIA_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
}


@router.get("", response_model=ResponseSchema[list[dict[str, Any]]])
async def list_reports(request: Request) -> ResponseSchema[list[dict[str, Any]]]:
    """List available report artifacts (newest first)."""
    entries = reporting_service.list_reports()
    return ResponseSchema(
        success=True,
        message=f"{len(entries)} report(s) available",
        data=entries,
    )


@router.post("", response_model=ResponseSchema[dict[str, Any]])
async def generate_report(
    request: Request, payload: GenerateReportRequest
) -> ResponseSchema[dict[str, Any]]:
    """Generate a report artifact from an existing scan, training run or
    analytics source."""
    try:
        result = reporting_service.generate(payload.kind, payload.report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseSchema(
        success=True,
        message="Report generated successfully",
        data=result,
    )


@router.get("/{report_id}/download")
async def download_report(
    request: Request,
    report_id: str,
    fmt: str = Query(
        default="md",
        pattern="^(md|json|csv)$",
        alias="format",
        description="Report artifact format.",
    ),
) -> Response:
    """Download the raw content of a report artifact."""
    content = reporting_service.download(report_id, fmt)
    if content is None:
        raise HTTPException(status_code=404, detail="Report artifact not found")
    return Response(
        content=content,
        media_type=_MEDIA_TYPES.get(fmt, "text/plain; charset=utf-8"),
        headers={"X-Report-Format": fmt},
    )
