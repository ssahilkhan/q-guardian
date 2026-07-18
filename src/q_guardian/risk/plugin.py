"""RiskAnalysisPlugin — framework plugin for the Risk & Decision Intelligence Engine."""

from __future__ import annotations

import time
from typing import Any

import structlog

from q_guardian.framework.context import FrameworkContext
from q_guardian.plugins.base import Plugin
from q_guardian.risk.actions.action_engine import ActionEngine
from q_guardian.risk.assessment.risk_engine import RiskAssessmentEngine
from q_guardian.risk.config import RiskConfig
from q_guardian.risk.data import NormalizedPrediction, RiskAssessment
from q_guardian.risk.enums import DecisionOutcome
from q_guardian.risk.explainability.explanation_engine import ExplanationEngine
from q_guardian.risk.policy.policy_engine import PolicyEngine
from q_guardian.risk.storage import RiskStorage

logger = structlog.get_logger("risk.plugin")


class RiskAnalysisPlugin(Plugin):
    """Risk & Decision Intelligence Engine plugin.

    Integrates the full risk pipeline into the Q-Guardian framework:
      1. RiskAssessmentEngine — scoring, trust, confidence, severity
      2. PolicyEngine — policy evaluation
      3. ActionEngine — action execution
      4. ExplanationEngine — explainability

    Consumes NormalizedPrediction inputs. Source-agnostic — does not
    know whether inputs came from rules, classical ML, or quantum.
    """

    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()
        self._risk_engine = RiskAssessmentEngine(self._config)
        self._policy_engine = PolicyEngine()
        self._action_engine = ActionEngine()
        self._explanation_engine = ExplanationEngine()
        self._storage: RiskStorage | None = None
        self._context: FrameworkContext | None = None
        self._assessment_count = 0
        self._block_count = 0

    @property
    def name(self) -> str:
        return "risk-analysis"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def author(self) -> str:
        return "Q-Guardian"

    @property
    def description(self) -> str:
        return "Risk & Decision Intelligence Engine for threat assessment and policy enforcement"

    @property
    def interfaces(self) -> list[str]:
        return ["risk_analyzer"]

    @property
    def config(self) -> RiskConfig:
        return self._config

    @property
    def risk_engine(self) -> RiskAssessmentEngine:
        return self._risk_engine

    @property
    def policy_engine(self) -> PolicyEngine:
        return self._policy_engine

    @property
    def action_engine(self) -> ActionEngine:
        return self._action_engine

    @property
    def explanation_engine(self) -> ExplanationEngine:
        return self._explanation_engine

    async def initialize(self, context: FrameworkContext) -> None:
        """Initialize the plugin with framework context."""
        self._context = context
        self._policy_engine.load_defaults()
        self._storage = RiskStorage()

        logger.info(
            "risk_plugin_initialized",
            policies=self._policy_engine.registry.count,
        )

    async def start(self) -> None:
        """Start the plugin."""
        logger.info(
            "risk_plugin_started",
            config=self._config.model_dump(),
        )

    async def stop(self) -> None:
        """Stop the plugin."""
        logger.info(
            "risk_plugin_stopped",
            assessments=self._assessment_count,
            blocks=self._block_count,
        )

    async def assess(self, prediction: NormalizedPrediction) -> dict[str, Any]:
        """Run the full risk assessment pipeline.

        Args:
            prediction: Normalized prediction input.

        Returns:
            Dict with assessment, decision, and explanation.
        """
        start = time.monotonic()
        self._assessment_count += 1

        assessment = self._risk_engine.assess(prediction)

        decision = self._policy_engine.evaluate(assessment)

        action_result = self._action_engine.execute(decision, assessment)

        explanation = self._explanation_engine.explain(assessment, decision, action_result)

        if decision.outcome == DecisionOutcome.BLOCKED:
            self._block_count += 1

        elapsed_ms = (time.monotonic() - start) * 1000

        result = {
            "assessment": assessment.model_dump(),
            "decision": decision.model_dump(),
            "action": action_result.model_dump(),
            "explanation": explanation.model_dump(),
            "processing_time_ms": round(elapsed_ms, 2),
        }

        await self._publish_events(assessment, decision)

        return result

    async def assess_batch(self, predictions: list[NormalizedPrediction]) -> list[dict[str, Any]]:
        """Assess a batch of predictions."""
        return [await self.assess(p) for p in predictions]

    async def _publish_events(self, assessment: RiskAssessment, decision: Any) -> None:
        """Publish risk assessment events."""
        if self._context is None or not hasattr(self._context, "event_bus"):
            return

        bus = self._context.event_bus
        source = f"plugin:{self.name}"

        from q_guardian.risk.events import RiskAssessmentCompleted, RiskCalculated

        await bus.publish(RiskCalculated(
            source=source,
            data={"assessment_id": assessment.assessment_id, "risk_score": assessment.risk_score},
        ))

        await bus.publish(RiskAssessmentCompleted(
            source=source,
            data={"assessment_id": assessment.assessment_id, "outcome": decision.outcome.value},
        ))

    def health(self) -> dict[str, Any]:
        """Return plugin health status."""
        return {
            "status": "healthy",
            "plugin": self.name,
            "assessment_count": self._assessment_count,
            "block_count": self._block_count,
            "policies": self._policy_engine.registry.count,
            "evaluations": self._policy_engine.evaluation_count,
            "actions": self._action_engine.execution_count,
            "explanations": self._explanation_engine.explanation_count,
        }

    def configuration(self) -> dict[str, Any]:
        """Return plugin configuration."""
        return self._config.model_dump()
