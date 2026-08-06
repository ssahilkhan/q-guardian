"""PromptScannerPlugin — Q-Guardian's first functional security plugin.

Integrates the full prompt security pipeline into the framework.
Receives RuntimeContext, publishes events, updates SecurityContext.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.plugins.base import Plugin
from q_guardian.security.config import PromptSecurityConfig
from q_guardian.security.decision import SecurityDecisionEngine
from q_guardian.security.enums import PromptDecision
from q_guardian.security.models import PromptAnalysis
from q_guardian.security.pipeline import (
    PromptFeatureExtractor,
    PromptNormalizer,
    PromptValidator,
    RuleEngine,
)

if TYPE_CHECKING:
    from q_guardian.framework.context import FrameworkContext

logger = structlog.get_logger("security.prompt_scanner")


class PromptScannerPlugin(Plugin):
    """Prompt Security Scanner plugin for Q-Guardian.

    Implements the full prompt security pipeline:
      Normalize → Validate → Extract Features → Rule Analysis → Decision

    This plugin:
    - Inherits from Plugin interface
    - Registers with Guardian as a prompt_scanner
    - Receives RuntimeContext
    - Publishes framework events
    - Updates SecurityContext

    Future ML/Quantum modules will extend this pipeline by
    implementing PromptDetector and ThreatClassifier interfaces.
    """

    def __init__(
        self,
        config: PromptSecurityConfig | None = None,
    ) -> None:
        """Initialize the plugin.

        Args:
            config: Optional configuration. Uses defaults if None.
        """
        self._config = config or PromptSecurityConfig()
        self._normalizer = PromptNormalizer()
        self._validator = PromptValidator(
            max_length=self._config.max_prompt_length,
            min_length=self._config.min_prompt_length,
            max_lines=self._config.max_lines,
        )
        self._feature_extractor = PromptFeatureExtractor(
            suspicious_keywords=self._config.suspicious_keywords,
        )
        self._rule_engine = RuleEngine()
        self._decision_engine = SecurityDecisionEngine(
            block_on_critical=self._config.block_on_critical,
            block_on_high_count=self._config.block_on_high_count,
            review_on_high_count=self._config.review_on_high_count,
            warn_on_medium_count=self._config.warn_on_medium_count,
        )
        self._context: FrameworkContext | None = None
        self._scan_count: int = 0
        self._block_count: int = 0

    @property
    def name(self) -> str:
        return "prompt-scanner"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def author(self) -> str:
        return "Q-Guardian"

    @property
    def description(self) -> str:
        return "Rule-based prompt security scanner with ML/Quantum extensibility"

    @property
    def interfaces(self) -> list[str]:
        return ["prompt_scanner"]

    @property
    def rule_engine(self) -> RuleEngine:
        """Access the rule engine for configuration."""
        return self._rule_engine

    @property
    def decision_engine(self) -> SecurityDecisionEngine:
        """Access the decision engine for configuration."""
        return self._decision_engine

    async def initialize(self, context: FrameworkContext) -> None:
        """Initialize the plugin with framework context.

        Args:
            context: The shared framework context.
        """
        self._context = context
        logger.info("prompt_scanner_initialized")

    async def start(self) -> None:
        """Start the plugin."""
        logger.info(
            "prompt_scanner_started",
            rules=len(self._rule_engine.list_rules()),
        )

    async def stop(self) -> None:
        """Stop the plugin."""
        logger.info(
            "prompt_scanner_stopped",
            scans=self._scan_count,
            blocked=self._block_count,
        )

    async def scan_prompt(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Scan a prompt through the full security pipeline.

        This is the main entry point called by Guardian.scan_prompt().

        Args:
            prompt: The raw prompt text to scan.
            **kwargs: Additional context.

        Returns:
            Dictionary with analysis results.
        """
        import time

        start_time = time.monotonic()
        self._scan_count += 1

        # Step 1: Normalize
        normalized = self._normalizer.normalize(prompt)

        # Step 2: Validate
        validation_status, validation_errors = self._validator.validate(normalized)

        # Step 3: Extract features
        features = self._feature_extractor.extract(normalized)

        # Step 4: Rule analysis
        findings = self._rule_engine.analyze(normalized, features)

        # Build analysis
        analysis = PromptAnalysis(
            original_prompt=prompt,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=findings,
        )

        # Step 5: Decision
        self._decision_engine.decide(analysis)

        # Record timing
        elapsed_ms = (time.monotonic() - start_time) * 1000
        analysis.processing_time_ms = round(elapsed_ms, 2)

        # Track blocks
        if analysis.decision == PromptDecision.BLOCK:
            self._block_count += 1

        # Publish events
        await self._publish_events(analysis)

        # Log findings
        if self._config.log_findings and findings:
            logger.info(
                "prompt_findings",
                finding_count=len(findings),
                decision=analysis.decision.value,
                risk_score=analysis.risk_score,
            )

        return analysis.model_dump()

    async def _publish_events(self, analysis: PromptAnalysis) -> None:
        """Publish analysis events to the event bus.

        Args:
            analysis: The completed analysis.
        """
        if self._context is None or not hasattr(self._context, "event_bus"):
            return

        bus = self._context.event_bus
        source = f"plugin:{self.name}"

        from q_guardian.security.events import (
            PromptAllowed,
            PromptAnalysisCompleted,
            PromptBlocked,
            PromptFeaturesExtracted,
            PromptNormalized,
            PromptRuleMatched,
            PromptValidated,
        )

        await bus.publish(
            PromptNormalized(
                source=source,
                data={"analysis_id": analysis.analysis_id},
            )
        )

        await bus.publish(
            PromptValidated(
                source=source,
                data={
                    "analysis_id": analysis.analysis_id,
                    "status": analysis.validation_status.value,
                },
            )
        )

        await bus.publish(
            PromptFeaturesExtracted(
                source=source,
                data={
                    "analysis_id": analysis.analysis_id,
                    "features": analysis.features.model_dump(),
                },
            )
        )

        for finding in analysis.findings:
            await bus.publish(
                PromptRuleMatched(
                    source=source,
                    data={
                        "analysis_id": analysis.analysis_id,
                        "finding_id": finding.finding_id,
                        "rule_id": finding.rule_id,
                        "category": finding.category.value,
                        "severity": finding.severity.value,
                    },
                )
            )

        await bus.publish(
            PromptAnalysisCompleted(
                source=source,
                data=analysis.to_security_dict(),
            )
        )

        if analysis.decision == PromptDecision.BLOCK:
            await bus.publish(
                PromptBlocked(
                    source=source,
                    data=analysis.to_security_dict(),
                )
            )
        else:
            await bus.publish(
                PromptAllowed(
                    source=source,
                    data=analysis.to_security_dict(),
                )
            )

    def health(self) -> dict[str, Any]:
        """Return plugin health status.

        Returns:
            Dictionary with health information.
        """
        return {
            "status": "healthy",
            "plugin": self.name,
            "scan_count": self._scan_count,
            "block_count": self._block_count,
            "rule_count": len(self._rule_engine.list_rules()),
        }

    def configuration(self) -> dict[str, Any]:
        """Return plugin configuration schema.

        Returns:
            Dictionary describing configuration options.
        """
        return self._config.model_dump()
