"""Request/response schemas for the console UI API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from q_guardian.schemas.base import BaseSchema
from q_guardian.utils.datetime_utils import get_utc_now

MAX_PROMPT_LENGTH = 100_000


class ScanRequestSchema(BaseSchema):
    """Request body for scanning a prompt through the detection pipeline."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROMPT_LENGTH,
        description="Prompt text to analyze",
    )


class AnalysisItemSchema(BaseSchema):
    """Summary of a single analysis result."""

    analysis_id: str = Field(description="Unique analysis ID")
    decision: str = Field(description="ALLOW / WARN / REVIEW / BLOCK decision")
    risk_score: float = Field(ge=0.0, le=1.0, description="Derived risk score")
    is_valid: bool = Field(description="Whether the input passed validation")
    finding_count: int = Field(ge=0, description="Number of findings")
    high_severity_count: int = Field(ge=0, description="HIGH/CRITICAL finding count")
    processing_time_ms: float = Field(ge=0.0, description="Pipeline latency in ms")
    timestamp: datetime = Field(default_factory=get_utc_now, description="When the analysis ran")
    payload: dict[str, Any] = Field(description="Full analysis payload")
