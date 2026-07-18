"""Standard framework events for Q-Guardian.

Defines the predefined event types that the framework and plugins
use to communicate. Each event class carries typed data relevant
to its occurrence.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from q_guardian.events.base import Event


class FrameworkStarted(Event):
    """Published when the framework has fully started."""

    event_type: str = Field(default="framework.started", init=False)


class FrameworkStopped(Event):
    """Published when the framework has shut down."""

    event_type: str = Field(default="framework.stopped", init=False)


class PluginLoaded(Event):
    """Published when a plugin is successfully loaded."""

    event_type: str = Field(default="plugin.loaded", init=False)


class PluginUnloaded(Event):
    """Published when a plugin is unloaded."""

    event_type: str = Field(default="plugin.unloaded", init=False)


class PromptReceived(Event):
    """Published when a prompt is received for analysis."""

    event_type: str = Field(default="prompt.received", init=False)


class ThreatDetected(Event):
    """Published when a security threat is detected."""

    event_type: str = Field(default="threat.detected", init=False)


class RiskCalculated(Event):
    """Published when a risk assessment is completed."""

    event_type: str = Field(default="risk.calculated", init=False)


class PolicyViolation(Event):
    """Published when a policy violation occurs."""

    event_type: str = Field(default="policy.violation", init=False)


class RuntimeEvent(Event):
    """Published for general runtime monitoring events."""

    event_type: str = Field(default="runtime.event", init=False)


class IncidentCreated(Event):
    """Published when a security incident is created."""

    event_type: str = Field(default="incident.created", init=False)


class DashboardUpdated(Event):
    """Published when dashboard data is updated."""

    event_type: str = Field(default="dashboard.updated", init=False)


class BeforePrompt(Event):
    """Published before prompt processing begins."""

    event_type: str = Field(default="prompt.before", init=False)


class AfterPrompt(Event):
    """Published after prompt processing completes."""

    event_type: str = Field(default="prompt.after", init=False)


class BeforeToolExecution(Event):
    """Published before a tool execution begins."""

    event_type: str = Field(default="tool.before", init=False)


class AfterToolExecution(Event):
    """Published after a tool execution completes."""

    event_type: str = Field(default="tool.after", init=False)
