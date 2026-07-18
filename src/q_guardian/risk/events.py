"""Events for the Risk & Decision Intelligence Engine."""

from __future__ import annotations

from pydantic import Field

from q_guardian.events.base import Event


class RiskCalculated(Event):
    """Published when a risk score is calculated."""

    event_type: str = Field(default="risk.score.calculated", init=False)


class ThreatScored(Event):
    """Published when a threat score is computed."""

    event_type: str = Field(default="risk.threat.scored", init=False)


class TrustUpdated(Event):
    """Published when a provider's trust score is updated."""

    event_type: str = Field(default="risk.trust.updated", init=False)


class PolicyMatched(Event):
    """Published when a policy rule matches an assessment."""

    event_type: str = Field(default="risk.policy.matched", init=False)


class PolicyExecuted(Event):
    """Published when a policy decision is executed."""

    event_type: str = Field(default="risk.policy.executed", init=False)


class ActionExecuted(Event):
    """Published when an action is executed."""

    event_type: str = Field(default="risk.action.executed", init=False)


class ExplanationGenerated(Event):
    """Published when an explanation is generated."""

    event_type: str = Field(default="risk.explanation.generated", init=False)


class RiskAssessmentCompleted(Event):
    """Published when a full risk assessment cycle completes."""

    event_type: str = Field(default="risk.assessment.completed", init=False)
