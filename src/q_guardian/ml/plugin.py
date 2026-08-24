"""ThreatAnalysisPlugin — generic orchestrator for rule-based, ML, and future quantum analysis."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.ml.config import MLConfig
from q_guardian.ml.inference.engine import InferenceEngine
from q_guardian.ml.models.model_manager import ModelManager
from q_guardian.plugins.base import Plugin
from q_guardian.security.config import IndirectInjectionConfig, PromptSecurityConfig
from q_guardian.security.decision import SecurityDecisionEngine
from q_guardian.security.enums import PromptDecision
from q_guardian.security.indirect import ContentSegment, build_untrusted_context
from q_guardian.security.models import PromptAnalysis
from q_guardian.security.pipeline import (
    PromptFeatureExtractor,
    PromptNormalizer,
    PromptValidator,
    RuleEngine,
)

if TYPE_CHECKING:
    from q_guardian.framework.context import FrameworkContext
    from q_guardian.security.extensibility import PromptClassifier, PromptDetector

logger = structlog.get_logger("ml.threat_analysis")


class ThreatAnalysisPlugin(Plugin):
    """Generic threat analysis plugin that orchestrates:
    1. Rule-based analysis (PromptSecurity pipeline)
    2. Classical ML detection (via registered PromptDetector/PromptClassifier)
    3. Future quantum analysis (via Module 6 ThreatClassifier)

    This plugin replaces PromptScannerPlugin for advanced use cases,
    combining all analysis layers into a single unified pipeline.

    Backward-compatible: if no ML models are registered, behaves
    identically to the rule-based PromptScannerPlugin.
    """

    def __init__(
        self,
        config: MLConfig | None = None,
        rule_config: Any | None = None,
    ) -> None:
        self._ml_config = config or MLConfig()

        # Rule-based pipeline (reused from security module)
        self._normalizer = PromptNormalizer()
        self._validator = PromptValidator()
        self._feature_extractor = PromptFeatureExtractor()
        self._rule_engine = RuleEngine()
        self._decision_engine = SecurityDecisionEngine()

        # Indirect injection detection configuration (P3-5). When a
        # PromptSecurityConfig is supplied as rule_config, its indirect
        # settings are honored.
        if isinstance(rule_config, PromptSecurityConfig):
            self._indirect_config: IndirectInjectionConfig = rule_config.indirect
        else:
            self._indirect_config = IndirectInjectionConfig()

        # ML components
        self._model_manager = ModelManager()
        self._inference_engine = InferenceEngine(
            registry=self._model_manager.registry,
            config=self._ml_config,
        )

        self._context: FrameworkContext | None = None
        self._scan_count: int = 0
        self._block_count: int = 0
        self._ml_findings_count: int = 0

    @property
    def name(self) -> str:
        return "threat-analysis"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def author(self) -> str:
        return "Q-Guardian"

    @property
    def description(self) -> str:
        return "Unified threat analysis: rules + classical ML + quantum (future)"

    @property
    def interfaces(self) -> list[str]:
        return ["prompt_scanner"]

    @property
    def model_manager(self) -> ModelManager:
        return self._model_manager

    @property
    def inference_engine(self) -> InferenceEngine:
        return self._inference_engine

    @property
    def rule_engine(self) -> RuleEngine:
        return self._rule_engine

    def register_ml_detector(self, detector: PromptDetector) -> None:
        """Register an ML detector for enhanced analysis.

        Args:
            detector: The detector to register.
        """
        self._inference_engine.register_detector(detector)
        self._model_manager.register_model(detector)  # type: ignore[arg-type]
        logger.info("ml_detector_registered", detector=detector.name)

    def register_ml_classifier(self, classifier: PromptClassifier) -> None:
        """Register an ML classifier for enhanced analysis.

        Args:
            classifier: The classifier to register.
        """
        self._inference_engine.register_classifier(classifier)
        self._model_manager.register_model(classifier)  # type: ignore[arg-type]
        logger.info("ml_classifier_registered", classifier=classifier.name)

    async def initialize(self, context: FrameworkContext) -> None:
        """Initialize the plugin with framework context."""
        self._context = context
        logger.info("threat_analysis_initialized")

    async def start(self) -> None:
        """Start the plugin."""
        detector_count = self._inference_engine.detector_count
        classifier_count = self._inference_engine.classifier_count
        logger.info(
            "threat_analysis_started",
            rules=len(self._rule_engine.list_rules()),
            ml_detectors=detector_count,
            ml_classifiers=classifier_count,
            ml_enabled=self._ml_config.enabled,
        )

    async def stop(self) -> None:
        """Stop the plugin."""
        logger.info(
            "threat_analysis_stopped",
            scans=self._scan_count,
            blocks=self._block_count,
            ml_findings=self._ml_findings_count,
        )

    async def scan_prompt(
        self,
        prompt: str,
        context_segments: list[ContentSegment] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Scan a prompt through the full unified pipeline.

        Pipeline:
        1. Normalize → Validate → Extract features (rule-based)
        2. Attach optional untrusted context segments (indirect injection)
        3. Rule analysis
        4. ML inference (if enabled and detectors registered)
        5. Merge findings
        6. Decision

        Args:
            prompt: The prompt text to scan.
            context_segments: Optional untrusted content segments (tool
                outputs, RAG context, documents, ...) analyzed for indirect
                injection. When omitted, behavior is identical to direct
                prompt analysis.
            **kwargs: Reserved for future extensions.

        Returns:
            Serialized PromptAnalysis with decision fields.
        """
        start = time.monotonic()
        self._scan_count += 1

        # Step 1: Normalize & Validate
        normalized = self._normalizer.normalize(prompt)
        validation_status, validation_errors = self._validator.validate(normalized)

        # Step 2: Extract features (+ attach untrusted context if provided)
        features = self._feature_extractor.extract(normalized)
        indirect_summary = self._attach_untrusted_context(features, context_segments)

        # Step 3: Rule analysis
        rule_findings = self._rule_engine.analyze(normalized, features)

        # Step 4: Build initial analysis
        analysis = PromptAnalysis(
            original_prompt=prompt,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=rule_findings,
        )

        # Step 5: ML inference (if enabled)
        ml_result = None
        ml_findings_count = 0
        if (
            self._ml_config.enabled
            and self._inference_engine.detector_count + self._inference_engine.classifier_count > 0
        ):
            try:
                ml_result = await self._inference_engine.run(normalized, features)
                analysis.findings.extend(ml_result.findings)
                ml_findings_count = len(ml_result.findings)
                self._ml_findings_count += ml_findings_count

                # Merge ML risk score with rule-based risk
                analysis.metadata["ml_risk_score"] = ml_result.risk_score
                analysis.metadata["ml_predictions"] = ml_result.predictions
                analysis.metadata["ml_anomaly_score"] = ml_result.anomaly_score
            except Exception:
                logger.error("ml_inference_error", exc_info=True)

        # Step 6: Decision
        self._decision_engine.decide(analysis)

        # Record timing
        elapsed_ms = (time.monotonic() - start) * 1000
        analysis.processing_time_ms = round(elapsed_ms, 2)
        analysis.metadata["ml_findings_count"] = ml_findings_count
        analysis.metadata["rule_findings_count"] = len(rule_findings)
        if indirect_summary:
            analysis.metadata["indirect_summary"] = indirect_summary
            analysis.metadata["indirect_findings_count"] = sum(
                1 for f in rule_findings if f.rule_id.startswith("ii-")
            )

        if analysis.decision == PromptDecision.BLOCK:
            self._block_count += 1

        # Publish events
        await self._publish_events(analysis, ml_result, features, normalized)

        return analysis.model_dump()

    def _attach_untrusted_context(
        self,
        features: Any,
        context_segments: list[ContentSegment] | None,
    ) -> dict[str, Any]:
        """Attach untrusted context segments to features for ii-* rules.

        Builds the JSON-safe provenance payload consumed by the guarded
        indirect injection rules in :class:`RuleEngine`. When no segments
        are provided or detection is disabled, features remain untouched
        and the ``ii-*`` rules stay inert.

        Args:
            features: Extracted prompt features (mutated in place).
            context_segments: Optional untrusted content segments.

        Returns:
            A summary dictionary for analysis metadata.
        """
        if not context_segments or not self._indirect_config.enabled:
            return {}
        payload = build_untrusted_context(context_segments, self._indirect_config)
        if not payload.get("segments"):
            return {
                "segments_scanned": 0,
                "segments_omitted": payload.get("segments_omitted", 0),
                "trusted_count": payload.get("trusted_count", 0),
            }
        features.metadata["untrusted_context"] = payload
        return {
            "segments_scanned": len(payload["segments"]),
            "segments_omitted": payload.get("segments_omitted", 0),
            "trusted_count": payload.get("trusted_count", 0),
        }

    async def _publish_events(
        self,
        analysis: PromptAnalysis,
        ml_result: Any = None,
        features: Any = None,
        normalized: str = "",
    ) -> None:
        """Publish analysis events including ML events."""
        if self._context is None or not hasattr(self._context, "event_bus"):
            return

        bus = self._context.event_bus
        source = f"plugin:{self.name}"

        from q_guardian.ml.events import (
            AnomalyDetected,
            EnsemblePrediction,
            FeatureExtracted,
            InferenceCompleted,
            ThreatClassified,
        )
        from q_guardian.security.events import (
            PromptAllowed,
            PromptAnalysisCompleted,
            PromptBlocked,
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

        # Publish ML events if ML inference ran
        if ml_result is not None:
            await bus.publish(
                InferenceCompleted(
                    source=source,
                    data={
                        "analysis_id": analysis.analysis_id,
                        "is_anomaly": ml_result.is_anomaly,
                        "anomaly_score": ml_result.anomaly_score,
                        "risk_score": ml_result.risk_score,
                        "predicted_class": ml_result.predicted_class,
                        "confidence": ml_result.confidence,
                        "predictions": ml_result.predictions,
                        "findings_count": len(ml_result.findings),
                        "processing_time_ms": ml_result.processing_time_ms,
                    },
                )
            )

            if ml_result.is_anomaly:
                await bus.publish(
                    AnomalyDetected(
                        source=source,
                        data={
                            "analysis_id": analysis.analysis_id,
                            "anomaly_score": ml_result.anomaly_score,
                            "threshold": self._ml_config.anomaly_threshold,
                        },
                    )
                )

            if ml_result.predicted_class and ml_result.predicted_class != "benign":
                await bus.publish(
                    ThreatClassified(
                        source=source,
                        data={
                            "analysis_id": analysis.analysis_id,
                            "predicted_class": ml_result.predicted_class,
                            "confidence": ml_result.confidence,
                            "all_predictions": ml_result.predictions,
                        },
                    )
                )

            if ml_result.predictions:
                await bus.publish(
                    EnsemblePrediction(
                        source=source,
                        data={
                            "analysis_id": analysis.analysis_id,
                            "predictions": ml_result.predictions,
                            "predicted_class": ml_result.predicted_class,
                            "confidence": ml_result.confidence,
                        },
                    )
                )

        if features is not None:
            feature_count = len(features.__dict__) if hasattr(features, "__dict__") else 0
            await bus.publish(
                FeatureExtracted(
                    source=source,
                    data={
                        "analysis_id": analysis.analysis_id,
                        "prompt_length": len(normalized) if normalized else 0,
                        "feature_count": feature_count,
                    },
                )
            )

    def health(self) -> dict[str, Any]:
        """Return plugin health status."""
        return {
            "status": "healthy",
            "plugin": self.name,
            "scan_count": self._scan_count,
            "block_count": self._block_count,
            "ml_findings_count": self._ml_findings_count,
            "rule_count": len(self._rule_engine.list_rules()),
            "ml_detectors": self._inference_engine.detector_count,
            "ml_classifiers": self._inference_engine.classifier_count,
            "ml_enabled": self._ml_config.enabled,
        }

    def configuration(self) -> dict[str, Any]:
        """Return plugin configuration."""
        return self._ml_config.model_dump()
