from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.utils.uuid_utils import generate_uuid


class MetricsResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    metrics: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(default=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HealthResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    overall_status: str = Field(default="unknown")
    overall_score: float = Field(default=0.0)
    components: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalyticsResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    report_id: str = Field(default_factory=generate_uuid)
    title: str = Field(default="")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: dict[str, Any] = Field(default_factory=dict)
    threat_trends: list[dict[str, Any]] = Field(default_factory=list)
    forecasts: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    statistics: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IncidentsResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    alerts: list[dict[str, Any]] = Field(default_factory=list)
    active_count: int = Field(default=0)
    resolved_count: int = Field(default=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PoliciesResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    policies: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(default=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PluginsResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    plugins: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(default=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProvidersResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    providers: list[dict[str, Any]] = Field(default_factory=list)
    accuracy: dict[str, float] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResponsesResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    responses: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(default=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AlertsResponseDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    alerts: list[dict[str, Any]] = Field(default_factory=list)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(default=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DashboardSnapshotDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    snapshot_id: str = Field(default_factory=generate_uuid)
    runtime: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)
    active_alerts_count: int = Field(default=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
