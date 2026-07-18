"""Security events for Q-Guardian.

Defines events published during the prompt security analysis pipeline.
These events are consumed by monitoring, logging, and dashboard plugins.
"""

from __future__ import annotations

from pydantic import Field

from q_guardian.events.base import Event


class PromptNormalized(Event):
    """Published after prompt normalization completes."""

    event_type: str = Field(default="security.prompt.normalized", init=False)


class PromptValidated(Event):
    """Published after prompt validation completes."""

    event_type: str = Field(default="security.prompt.validated", init=False)


class PromptFeaturesExtracted(Event):
    """Published after feature extraction completes."""

    event_type: str = Field(default="security.prompt.features", init=False)


class PromptRuleMatched(Event):
    """Published when a security rule matches."""

    event_type: str = Field(default="security.prompt.rule_matched", init=False)


class PromptAnalysisCompleted(Event):
    """Published when full prompt analysis is complete."""

    event_type: str = Field(default="security.prompt.analysis_completed", init=False)


class PromptBlocked(Event):
    """Published when a prompt is blocked."""

    event_type: str = Field(default="security.prompt.blocked", init=False)


class PromptAllowed(Event):
    """Published when a prompt is allowed."""

    event_type: str = Field(default="security.prompt.allowed", init=False)
