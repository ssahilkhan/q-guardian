"""Dataset endpoints for the product workflow.

Read-only catalog / access views over the shipped dataset registry plus the
ability to schedule preparation (download -> normalize -> split -> manifest)
through the job runner.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request

from q_guardian.api.services import dataset_service
from q_guardian.schemas.base import ResponseSchema

logger = structlog.get_logger("api.datasets")

router = APIRouter()


@router.get("", response_model=ResponseSchema[list[dict[str, Any]]])
async def list_datasets(request: Request) -> ResponseSchema[list[dict[str, Any]]]:
    """List the full dataset catalog with access status."""
    catalog = dataset_service.catalog()
    return ResponseSchema(
        success=True,
        message=f"{len(catalog)} dataset(s) in catalog",
        data=catalog,
    )


@router.get("/auth-status", response_model=ResponseSchema[dict[str, Any]])
async def dataset_auth_status(request: Request) -> ResponseSchema[dict[str, Any]]:
    """Return dataset-authentication configuration (never the token itself)."""
    status = dataset_service.auth_status()
    return ResponseSchema(
        success=True,
        message="Dataset authentication status retrieved",
        data=status,
    )


@router.get("/prepared", response_model=ResponseSchema[list[dict[str, Any]]])
async def list_prepared(request: Request) -> ResponseSchema[list[dict[str, Any]]]:
    """Inventory datasets already prepared on disk."""
    prepared = dataset_service.prepared()
    return ResponseSchema(
        success=True,
        message=f"{len(prepared)} prepared dataset(s) found",
        data=prepared,
    )


@router.get("/{dataset_id}", response_model=ResponseSchema[dict[str, Any]])
async def get_dataset(
    request: Request, dataset_id: str
) -> ResponseSchema[dict[str, Any]]:
    """Return one catalog entry."""
    entry = dataset_service.get_dataset(dataset_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ResponseSchema(
        success=True,
        message="Dataset retrieved successfully",
        data=entry,
    )


@router.get("/{dataset_id}/access", response_model=ResponseSchema[dict[str, Any]])
async def get_dataset_access(
    request: Request, dataset_id: str
) -> ResponseSchema[dict[str, Any]]:
    """Return the access classification for one dataset."""
    info = dataset_service.access(dataset_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ResponseSchema(
        success=True,
        message="Dataset access retrieved successfully",
        data=info,
    )


@router.post("/{dataset_id}/prepare", response_model=ResponseSchema[dict[str, Any]])
async def prepare_dataset(
    request: Request, dataset_id: str
) -> ResponseSchema[dict[str, Any]]:
    """Schedule dataset preparation (downloads via the server-side HF token)."""
    if dataset_service.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        job = dataset_service.submit_prepare(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseSchema(
        success=True,
        message=f"Dataset preparation queued as job {job.id}",
        data=job.as_dict(),
    )
