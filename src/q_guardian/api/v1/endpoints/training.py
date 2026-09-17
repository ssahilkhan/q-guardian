"""Training endpoints for the product workflow.

List prior runs, start a prepare+train job for the hybrid detector, and start
an evaluation job over a trained checkpoint. Both jobs stream progress through
the job runner and persist results under ``artifacts/training``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, HTTPException, Request

from q_guardian.api.services import training_service
from q_guardian.schemas.base import ResponseSchema
from q_guardian.schemas.product import StartTrainingRequest

if TYPE_CHECKING:
    from q_guardian.schemas.product import StartTrainingRequest

logger = structlog.get_logger("api.training")

router = APIRouter()


@router.get("", response_model=ResponseSchema[list[dict[str, Any]]])
async def list_runs(request: Request) -> ResponseSchema[list[dict[str, Any]]]:
    """List persisted training runs (newest first)."""
    runs = training_service.runs()
    return ResponseSchema(
        success=True,
        message=f"{len(runs)} training run(s) found",
        data=runs,
    )


@router.get("/{name}", response_model=ResponseSchema[dict[str, Any]])
async def get_run(request: Request, name: str) -> ResponseSchema[dict[str, Any]]:
    """Return one training run."""
    run = training_service.run(name)
    if run is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    return ResponseSchema(
        success=True,
        message="Training run retrieved successfully",
        data=run,
    )


@router.post("", response_model=ResponseSchema[dict[str, Any]])
async def start_training(
    request: Request, payload: StartTrainingRequest
) -> ResponseSchema[dict[str, Any]]:
    """Start a prepare+train job for the hybrid detector."""
    try:
        job = training_service.submit_run(
            dataset_ids=payload.dataset_ids,
            name=payload.name,
            validation_ratio=payload.validation_ratio,
            seed=payload.seed,
            max_samples_per_class=payload.max_samples_per_class,
            quantum=payload.quantum,
            quantum_shots=payload.quantum_shots,
            quantum_feature_count=payload.quantum_feature_count,
            quantum_cap=payload.quantum_cap,
            n_estimators=payload.n_estimators,
            contamination=payload.contamination,
            threshold=payload.threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseSchema(
        success=True,
        message=f"Training job queued as {job.id}",
        data=job.as_dict(),
    )


@router.post("/{name}/evaluate", response_model=ResponseSchema[dict[str, Any]])
async def start_evaluation(
    request: Request, name: str
) -> ResponseSchema[dict[str, Any]]:
    """Schedule evaluation of a trained checkpoint."""
    run = training_service.run(name)
    if run is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    if not run.get("model", {}).get("exists"):
        raise HTTPException(status_code=400, detail="Training run has no saved model")
    try:
        job = training_service.submit_evaluate(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseSchema(
        success=True,
        message=f"Evaluation job queued as {job.id}",
        data=job.as_dict(),
    )
