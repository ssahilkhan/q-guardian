"""Analysis endpoints for the Q-Guardian console.

Submit prompts through the existing detection pipeline and inspect
the bounded scan history. No detection logic is implemented here —
the pipeline lives in :class:`q_guardian.ml.plugin.ThreatAnalysisPlugin`.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request

from q_guardian.api.metrics import record_scan_decision
from q_guardian.api.services.analysis import get_analysis_service
from q_guardian.schemas.base import PaginatedResponseSchema, ResponseSchema
from q_guardian.schemas.console import AnalysisItemSchema, ScanRequestSchema

logger = structlog.get_logger("api.analysis")

router = APIRouter()

service = get_analysis_service()


def _to_item(payload: dict[str, Any]) -> AnalysisItemSchema:
    """Project a raw analysis payload into the console item schema."""
    findings = payload.get("findings") or []
    high_severity = sum(
        1
        for finding in findings
        if str(finding.get("severity", "")).lower() in {"high", "critical"}
    )
    return AnalysisItemSchema(
        analysis_id=str(payload.get("analysis_id", "")),
        decision=str(payload.get("decision", "UNKNOWN")),
        risk_score=float(payload.get("risk_score", 0.0)),
        is_valid=bool(payload.get("is_valid", False)),
        finding_count=len(findings),
        high_severity_count=high_severity,
        processing_time_ms=float(payload.get("processing_time_ms", 0.0)),
        timestamp=payload.get("timestamp"),
        payload=payload,
    )


@router.post("/scan", response_model=ResponseSchema[AnalysisItemSchema])
async def scan_prompt(
    request: Request, body: ScanRequestSchema
) -> ResponseSchema[AnalysisItemSchema]:
    """Run the detection pipeline on a prompt.

    Args:
        request: Incoming request (correlation ID hook).
        body: The prompt to analyze.

    Returns:
        The full analysis result wrapped in the standard envelope.
    """
    result = await service.scan(body.prompt)
    item = _to_item(result)
    record_scan_decision(item.decision)
    return ResponseSchema(
        success=True,
        message=f"Analysis completed with decision {item.decision}",
        data=item,
    )


@router.get("/{analysis_id}", response_model=ResponseSchema[AnalysisItemSchema])
async def get_analysis(request: Request, analysis_id: str) -> ResponseSchema[AnalysisItemSchema]:
    """Return a single analysis result by ID.

    Args:
        request: Incoming request.
        analysis_id: Analysis ID to retrieve.

    Returns:
        The stored analysis result.
    """
    result = service.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return ResponseSchema(
        success=True,
        message="Analysis retrieved successfully",
        data=_to_item(result),
    )


@router.get("", response_model=PaginatedResponseSchema[AnalysisItemSchema])
async def list_analysis(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200, description="Max items to return"),
) -> PaginatedResponseSchema[AnalysisItemSchema]:
    """List recent analyses, most recent first.

    Args:
        request: Incoming request.
        limit: Maximum number of items to return.

    Returns:
        A paginated list of analysis summaries.
    """
    items = [_to_item(payload) for payload in service.history()[:limit]]
    return PaginatedResponseSchema(
        success=True,
        message="History retrieved successfully",
        data=items,
        total=len(items),
        page=1,
        page_size=limit,
        total_pages=1,
    )
