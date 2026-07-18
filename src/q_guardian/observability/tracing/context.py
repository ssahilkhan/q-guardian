from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TraceContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True, frozen=True)

    trace_id: str = Field(description="Current trace ID")
    correlation_id: str = Field(default="", description="Correlation ID")
    current_span_id: str | None = Field(default=None, description="Current span ID")

    def with_span(self, span_id: str) -> TraceContext:
        return TraceContext(
            trace_id=self.trace_id,
            correlation_id=self.correlation_id,
            current_span_id=span_id,
        )

    def to_dict(self) -> dict[str, str]:
        result: dict[str, str] = {"trace_id": self.trace_id}
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        if self.current_span_id:
            result["span_id"] = self.current_span_id
        return result

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> TraceContext:
        return cls(
            trace_id=data.get("trace_id", ""),
            correlation_id=data.get("correlation_id", ""),
            current_span_id=data.get("span_id"),
        )
