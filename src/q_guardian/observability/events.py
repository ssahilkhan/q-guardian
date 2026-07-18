"""Events for the Observability & Operations Platform."""

from __future__ import annotations

from pydantic import Field

from q_guardian.events.base import Event


class MetricRecorded(Event):
    """Published when a metric value is recorded."""

    event_type: str = Field(default="observability.metric.recorded", init=False)


class HealthChanged(Event):
    """Published when a component health status changes."""

    event_type: str = Field(default="observability.health.changed", init=False)


class TraceStarted(Event):
    """Published when a new distributed trace begins."""

    event_type: str = Field(default="observability.trace.started", init=False)


class TraceCompleted(Event):
    """Published when a distributed trace completes."""

    event_type: str = Field(default="observability.trace.completed", init=False)


class AlertRaised(Event):
    """Published when an alert is raised."""

    event_type: str = Field(default="observability.alert.raised", init=False)


class AlertResolved(Event):
    """Published when an alert is resolved."""

    event_type: str = Field(default="observability.alert.resolved", init=False)


class DashboardUpdated(Event):
    """Published when dashboard data is refreshed."""

    event_type: str = Field(default="observability.dashboard.updated", init=False)


class AnalyticsGenerated(Event):
    """Published when an analytics report is generated."""

    event_type: str = Field(default="observability.analytics.generated", init=False)
