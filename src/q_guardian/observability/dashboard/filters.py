from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.observability.data import TimeWindow
from q_guardian.observability.enums import (
    AlertSeverity,
    AnalyticsGranularity,
    DashboardFormat,
)


class DashboardFilter(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start_time: datetime | None = None
    end_time: datetime | None = None
    metric_name: str | None = None
    severity: AlertSeverity | None = None
    status: str | None = None
    component: str | None = None
    limit: int = 100
    offset: int = 0
    format: DashboardFormat = DashboardFormat.JSON


class TimeRangeFilter(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start: datetime | None = None
    end: datetime | None = None
    granularity: AnalyticsGranularity = AnalyticsGranularity.HOUR

    def to_time_window(self) -> TimeWindow | None:
        if self.start is None and self.end is None:
            return None
        now = datetime.now(UTC)
        return TimeWindow(
            start=self.start or now,
            end=self.end or now,
        )


class MetricFilter(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    min_value: float | None = None
    max_value: float | None = None
