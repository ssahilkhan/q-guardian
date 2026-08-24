"""Request/response schemas for the console UI API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from q_guardian.schemas.base import BaseSchema
from q_guardian.security.indirect import SegmentTrust, SourceType
from q_guardian.utils.datetime_utils import get_utc_now

MAX_PROMPT_LENGTH = 100_000


class ContextSegmentSchema(BaseSchema):
    """A piece of untrusted content accompanying a prompt scan.

    Provenance declaration for indirect injection detection (P3-5).
    ``source_type`` must be one of the ``SourceType`` values; when
    ``trust`` is omitted it is derived from ``source_type``.
    """

    content: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROMPT_LENGTH,
        description="Segment text content",
    )
    source_type: SourceType = Field(
        default=SourceType.RAG_CONTEXT,
        description="Provenance: tool_output, rag_context, web_result, "
        "retrieved_document, agent_message, file_content, database_record, "
        "user_prompt or system",
    )
    trust: SegmentTrust | None = Field(
        default=None,
        description="Optional trust override: trusted, untrusted or unknown",
    )
    source_id: str = Field(default="", description="Optional source identifier")
    uri: str = Field(default="", description="Optional source URI")
    position: int = Field(default=0, ge=0, description="Optional stream position")


class ScanRequestSchema(BaseSchema):
    """Request body for scanning a prompt through the detection pipeline."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROMPT_LENGTH,
        description="Prompt text to analyze",
    )
    context_segments: list[ContextSegmentSchema] | None = Field(
        default=None,
        description=(
            "Optional untrusted content segments (tool outputs, RAG context, "
            "documents) analyzed for indirect prompt injection"
        ),
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
