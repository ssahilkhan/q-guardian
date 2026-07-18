"""Provider adapters — bridge existing Q-Guardian components to PredictionProvider.

These adapters wrap existing rule engine, classical ML models, and quantum
models behind the PredictionProvider ABC so they can participate in
hybrid fusion without modifying their source code.
"""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.quantum.fusion.prediction import ReasoningTrace, ThreatPrediction
from q_guardian.quantum.fusion.providers import PredictionProvider

logger = structlog.get_logger("quantum.fusion.adapters")


class RuleEngineProvider(PredictionProvider):
    """Adapts the existing RuleEngine to the PredictionProvider interface.

    Wraps a SecurityDecisionEngine or a simple callable rule function.
    """

    def __init__(
        self,
        provider_id: str = "rule-engine",
        rule_engine: Any = None,
    ) -> None:
        self._provider_id = provider_id
        self._rule_engine = rule_engine

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_type(self) -> str:
        return "rule"

    @property
    def display_name(self) -> str:
        return "Rule Engine"

    async def predict(
        self,
        prompt: str,
        features: dict[str, Any] | None = None,
    ) -> ThreatPrediction:
        findings: list[dict[str, Any]] = []
        risk_score = 0.0
        confidence = 0.5
        label = "benign"
        rules_triggered: list[str] = []

        if self._rule_engine is not None:
            try:
                if hasattr(self._rule_engine, "analyze"):
                    result = self._rule_engine.analyze(prompt)
                    if hasattr(result, "findings"):
                        findings = [
                            {"rule_id": f.rule_id, "severity": f.severity.value}
                            for f in result.findings
                        ]
                        rules_triggered = [f.rule_id for f in result.findings]
                    if hasattr(result, "risk_score"):
                        risk_score = result.risk_score
                elif callable(self._rule_engine):
                    result = self._rule_engine(prompt)
                    if isinstance(result, dict):
                        risk_score = result.get("risk_score", 0.0)
                        findings = result.get("findings", [])
            except Exception as exc:
                logger.warning("rule_engine_adapter_error", error=str(exc))

        high_count = sum(
            1 for f in findings
            if f.get("severity") in ("high", "critical")
        )
        if high_count >= 2:
            label = "threat"
            confidence = min(0.5 + high_count * 0.15, 0.95)
        elif high_count == 1:
            label = "suspicious"
            confidence = 0.6
        else:
            label = "benign"
            confidence = max(0.5, 1.0 - risk_score)

        probabilities = {
            "benign": round(1.0 - confidence, 6) if label != "benign" else round(confidence, 6),
            "threat": round(confidence, 6) if label == "threat" else round(confidence * 0.3, 6),
        }

        return ThreatPrediction(
            provider_id=self._provider_id,
            predicted_label=label,
            confidence=round(confidence, 6),
            probabilities=probabilities,
            risk_score=round(risk_score, 6),
            model_name="rule-engine",
            reasoning=ReasoningTrace(
                rules_triggered=rules_triggered,
                evidence=[f.get("rule_id", "") for f in findings],
            ),
            metadata={"findings_count": len(findings)},
        )


class ClassicalModelProvider(PredictionProvider):
    """Adapts any BaseThreatModel (IsolationForest, RandomForest, XGBoost)
    to the PredictionProvider interface.
    """

    def __init__(
        self,
        model: Any,
        provider_id: str | None = None,
    ) -> None:
        self._model = model
        self._provider_id = provider_id or getattr(model, "name", "classical-model")

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_type(self) -> str:
        return "classical"

    @property
    def display_name(self) -> str:
        return f"Classical: {self._provider_id}"

    async def predict(
        self,
        prompt: str,
        features: dict[str, Any] | None = None,
    ) -> ThreatPrediction:
        raw_result: dict[str, Any] = {}
        try:
            if hasattr(self._model, "predict") and callable(self._model.predict):
                import asyncio
                raw_result = await self._model.predict(
                    features.get("feature_vector", []) if features else []
                )
        except Exception as exc:
            logger.warning("classical_model_adapter_error", provider=self._provider_id, error=str(exc))
            return ThreatPrediction(
                provider_id=self._provider_id,
                predicted_label="unknown",
                confidence=0.0,
                is_valid=False,
                error_message=str(exc),
            )

        predicted_class = raw_result.get("predicted_class", raw_result.get("predicted_label", "unknown"))
        confidence = float(raw_result.get("confidence", 0.0))
        probabilities = raw_result.get("probabilities", {})
        risk_score = float(raw_result.get("risk_score", 1.0 - confidence if predicted_class != "benign" else 0.0))

        return ThreatPrediction(
            provider_id=self._provider_id,
            predicted_label=str(predicted_class),
            confidence=confidence,
            probabilities=probabilities,
            risk_score=risk_score,
            model_name=self._provider_id,
            metadata={"raw_result": raw_result},
        )


class QuantumModelProvider(PredictionProvider):
    """Adapts any BaseQuantumModel to the PredictionProvider interface."""

    def __init__(
        self,
        model: Any,
        provider_id: str | None = None,
    ) -> None:
        self._model = model
        self._provider_id = provider_id or getattr(model, "name", "quantum-model")

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_type(self) -> str:
        return "quantum"

    @property
    def display_name(self) -> str:
        return f"Quantum: {self._provider_id}"

    async def predict(
        self,
        prompt: str,
        features: dict[str, Any] | None = None,
    ) -> ThreatPrediction:
        try:
            feature_vector = features.get("feature_vector", []) if features else []

            if hasattr(self._model, "predict_quantum") and callable(self._model.predict_quantum):
                result = await self._model.predict_quantum(feature_vector)
            elif hasattr(self._model, "predict") and callable(self._model.predict):
                import asyncio
                result = await self._model.predict(feature_vector)
            else:
                return ThreatPrediction(
                    provider_id=self._provider_id,
                    predicted_label="unknown",
                    confidence=0.0,
                    is_valid=False,
                    error_message="Model has no predict method",
                )

            if hasattr(result, "model_dump"):
                raw = result.model_dump()
            elif isinstance(result, dict):
                raw = result
            else:
                raw = {"predicted_class": str(result)}

        except Exception as exc:
            logger.warning("quantum_model_adapter_error", provider=self._provider_id, error=str(exc))
            return ThreatPrediction(
                provider_id=self._provider_id,
                predicted_label="unknown",
                confidence=0.0,
                is_valid=False,
                error_message=str(exc),
            )

        predicted_class = raw.get("predicted_class", raw.get("predicted_label", "unknown"))
        confidence = float(raw.get("confidence", 0.0))
        probabilities = raw.get("probabilities", {})
        risk_score = float(raw.get("risk_score", 0.0))

        backend = ""
        if hasattr(self._model, "quantum_metadata"):
            qm = self._model.quantum_metadata
            if hasattr(qm, "backend_type"):
                backend = str(qm.backend_type.value) if hasattr(qm.backend_type, "value") else str(qm.backend_type)

        return ThreatPrediction(
            provider_id=self._provider_id,
            predicted_label=str(predicted_class),
            confidence=confidence,
            probabilities=probabilities,
            risk_score=risk_score,
            model_name=self._provider_id,
            backend=backend,
            metadata={"raw_result": raw},
        )


class GenericProvider(PredictionProvider):
    """Generic adapter for any callable that returns a dict."""

    def __init__(
        self,
        provider_id: str,
        callable_fn: Any,
        provider_type: str = "external",
    ) -> None:
        self._provider_id = provider_id
        self._callable_fn = callable_fn
        self._type = provider_type

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_type(self) -> str:
        return self._type

    async def predict(
        self,
        prompt: str,
        features: dict[str, Any] | None = None,
    ) -> ThreatPrediction:
        try:
            if callable(self._callable_fn):
                import asyncio
                if asyncio.iscoroutinefunction(self._callable_fn):
                    result = await self._callable_fn(prompt, features)
                else:
                    result = self._callable_fn(prompt, features)
            else:
                return ThreatPrediction(
                    provider_id=self._provider_id,
                    predicted_label="unknown",
                    confidence=0.0,
                    is_valid=False,
                    error_message="Not callable",
                )

            if isinstance(result, dict):
                return ThreatPrediction(
                    provider_id=self._provider_id,
                    predicted_label=result.get("predicted_label", result.get("label", "unknown")),
                    confidence=float(result.get("confidence", 0.0)),
                    probabilities=result.get("probabilities", {}),
                    risk_score=float(result.get("risk_score", 0.0)),
                    metadata=result.get("metadata", {}),
                )

            return ThreatPrediction(
                provider_id=self._provider_id,
                predicted_label=str(result),
                confidence=0.5,
            )
        except Exception as exc:
            return ThreatPrediction(
                provider_id=self._provider_id,
                predicted_label="unknown",
                confidence=0.0,
                is_valid=False,
                error_message=str(exc),
            )
