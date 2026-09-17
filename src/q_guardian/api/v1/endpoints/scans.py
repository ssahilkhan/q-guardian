"""Security scan endpoints for the product workflow.

Run hybrid-evaluator cross-validation (``cv``) or per-checkpoint model
evaluation (``model_eval``) over prepared datasets / training runs, and browse
the persisted scan history with verdicts and detection metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request

from q_guardian.api.services import scan_service
from q_guardian.schemas.base import ResponseSchema
from q_guardian.schemas.product import StartScanRequest

if TYPE_CHECKING:
    from q_guardian.schemas.product import StartScanRequest

logger = structlog.get_logger("api.scans")

router = APIRouter()


@router.get("", response_model=ResponseSchema[list[dict[str, Any]]])
async def list_scans(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> ResponseSchema[list[dict[str, Any]]]:
    """Return persisted scan history (newest first)."""
    scans = scan_service.history(limit=limit)
    return ResponseSchema(
        success=True,
        message=f"{len(scans)} scan(s) found",
        data=scans,
    )


@router.get("/{scan_id}", response_model=ResponseSchema[dict[str, Any]])
async def get_scan(request: Request, scan_id: str) -> ResponseSchema[dict[str, Any]]:
    """Return one security scan result."""
    scan = scan_service.get(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return ResponseSchema(
        success=True,
        message="Scan retrieved successfully",
        data=scan,
    )


@router.post("", response_model=ResponseSchema[dict[str, Any]])
async def start_scan(
    request: Request, scan_request: StartScanRequest
) -> ResponseSchema[dict[str, Any]]:
    """Start a security scan over a prepared dataset or training run."""
    try:
        job = scan_service.submit_scan(
            kind=scan_request.type,
            target=scan_request.target,
            k=scan_request.k,
            seed=scan_request.seed,
            threshold=scan_request.threshold,
            ablate=scan_request.ablate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseSchema(
        success=True,
        message=f"Security scan queued as {job.id}",
        data=job.as_dict(),
    )
