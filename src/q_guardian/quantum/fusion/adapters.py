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
from q_guardian.security.pipeline import PromptNormalizer

logger = structlog.get_logger("quantum.fusion.adapters")

# Severity -> threat-probability contribution used to convert rule findings
# into a continuous threat score for fusion voting. Mirrors the canonical
# weights in q_guardian.security.decision.DecisionEngine.
_RULE_SEVERITY_WEIGHTS: dict[str, float] = {
    "info": 0.1,
    "low": 0.2,
    "medium": 0.5,
    "high": 0.8,
    "critical": 1.0,
}


def _normalize_rule_findings(
    result: Any,
) -> tuple[list[dict[str, Any]], float]:
    """Extract (findings, risk_score) from any rule-engine return shape.

    Supports:
      - q_guardian.security.pipeline.RuleEngine.analyze() which returns a
        ``list[PromptFinding]`` (each finding has ``rule_id`` and
        ``severity`` enum with a ``.value``).
      - Objects exposing ``.findings`` and/or ``.risk_score``.
      - Plain dicts.
    """
    findings: list[dict[str, Any]] = []
    risk_score = 0.0

    if isinstance(result, (list, tuple)):
        for item in result:
            rule_id = getattr(item, "rule_id", None)
            severity = getattr(getattr(item, "severity", None), "value", None)
            if rule_id is None and isinstance(item, dict):
                rule_id = item.get("rule_id")
                severity = item.get("severity")
            findings.append({"rule_id": rule_id, "severity": severity})
        return findings, risk_score

    if hasattr(result, "findings"):
        findings = [{"rule_id": f.rule_id, "severity": f.severity.value} for f in result.findings]
    if hasattr(result, "risk_score"):
        risk_score = float(result.risk_score)
    return findings, risk_score


def _threat_probability_from_findings(
    findings: list[dict[str, Any]],
) -> float:
    """Convert rule findings into a continuous threat probability."""
    threat_prob = 0.0
    for f in findings:
        threat_prob += _RULE_SEVERITY_WEIGHTS.get(str(f.get("severity")), 0.0)
    return min(1.0, threat_prob)


class RuleEngineProvider(PredictionProvider):
    """Adapts the existing RuleEngine to the PredictionProvider interface.

    Wraps a ``q_guardian.security.pipeline.RuleEngine`` (or any object with
    an ``analyze()`` method returning a list of findings, an object exposing
    ``.findings`` / ``.risk_score``, or a plain dict).
    """

    def __init__(
        self,
        provider_id: str = "rule-engine",
        rule_engine: Any = None,
        normalizer: Any | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._rule_engine = rule_engine
        self._normalizer = normalizer or PromptNormalizer()

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

        if self._rule_engine is not None:
            try:
                normalized = self._normalizer.normalize(prompt)
                if hasattr(self._rule_engine, "analyze"):
                    result = self._rule_engine.analyze(normalized)
                    findings, risk_score = _normalize_rule_findings(result)
                elif callable(self._rule_engine):
                    result = self._rule_engine(normalized)
                    if isinstance(result, dict):
                        risk_score = result.get("risk_score", 0.0)
                        findings = result.get("findings", [])
                    else:
                        findings, risk_score = _normalize_rule_findings(result)
            except Exception as exc:
                logger.warning("rule_engine_adapter_error", error=str(exc))

        rules_triggered = [f.get("rule_id") for f in findings if f.get("rule_id")]
        threat_prob = _threat_probability_from_findings(findings)
        risk_score = max(risk_score, threat_prob)

        label = "threat" if threat_prob >= 0.5 else "benign"
        confidence = threat_prob if label == "threat" else 1.0 - threat_prob

        probabilities = {
            "benign": round(1.0 - threat_prob, 6),
            "threat": round(threat_prob, 6),
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
        self._provider_id = provider_id or str(getattr(model, "name", "classical-model"))

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
                raw_result = await self._model.predict(
                    features.get("feature_vector", []) if features else []
                )
        except Exception as exc:
            logger.warning(
                "classical_model_adapter_error", provider=self._provider_id, error=str(exc)
            )
            return ThreatPrediction(
                provider_id=self._provider_id,
                predicted_label="unknown",
                confidence=0.0,
                is_valid=False,
                error_message=str(exc),
            )

        # IsolationForest-style output: {is_anomaly, anomaly_score}.
        # anomaly_score is the model's continuous 0-1 anomaly likelihood and
        # is used directly as the threat probability so the anomaly path
        # participates in fusion voting instead of always contributing 0.
        if "is_anomaly" in raw_result or "anomaly_score" in raw_result:
            is_anomaly = bool(raw_result.get("is_anomaly", False))
            anomaly_score = max(
                0.0,
                min(1.0, float(raw_result.get("anomaly_score", 0.0))),
            )
            label = "threat" if is_anomaly else "benign"
            threat_prob = anomaly_score
            benign_prob = 1.0 - threat_prob
            return ThreatPrediction(
                provider_id=self._provider_id,
                predicted_label=label,
                confidence=round(threat_prob if label == "threat" else benign_prob, 6),
                probabilities={
                    "benign": round(benign_prob, 6),
                    "threat": round(threat_prob, 6),
                },
                risk_score=round(threat_prob, 6),
                model_name=self._provider_id,
                metadata={"raw_result": raw_result, "predicted_category": "anomaly"},
            )

        predicted_class = raw_result.get(
            "predicted_class", raw_result.get("predicted_label", "unknown")
        )
        confidence = float(raw_result.get("confidence", 0.0))
        probabilities = raw_result.get("probabilities", {})
        category = str(predicted_class)

        raw_risk = raw_result.get("risk_score")
        if raw_risk is not None:
            risk_score = float(raw_risk)
        else:
            benign_p: float | None = None
            if isinstance(probabilities, dict) and "benign" in probabilities:
                try:
                    benign_p = float(probabilities["benign"])
                except (TypeError, ValueError):
                    benign_p = None
            if benign_p is not None:
                risk_score = max(0.0, min(1.0, 1.0 - benign_p))
            elif category == "benign":
                risk_score = max(0.0, 1.0 - confidence)
            else:
                risk_score = min(1.0, confidence)

        # Normalize into the shared {benign, threat} label space used by the
        # fusion strategies. Models speak fine-grained categories; fusion
        # votes aggregate threat probability, so a category other than
        # "benign" maps to "threat" (the original category is preserved in
        # metadata for explainability).
        label = "benign" if category == "benign" else "threat"
        threat_prob = max(0.0, min(1.0, risk_score))
        benign_prob = 1.0 - threat_prob
        return ThreatPrediction(
            provider_id=self._provider_id,
            predicted_label=label,
            confidence=round(threat_prob if label == "threat" else benign_prob, 6),
            probabilities={
                "benign": round(benign_prob, 6),
                "threat": round(threat_prob, 6),
            },
            risk_score=round(threat_prob, 6),
            model_name=self._provider_id,
            metadata={"raw_result": raw_result, "predicted_category": category},
        )


class QuantumModelProvider(PredictionProvider):
    """Adapts any BaseQuantumModel to the PredictionProvider interface."""

    def __init__(
        self,
        model: Any,
        provider_id: str | None = None,
    ) -> None:
        self._model = model
        self._provider_id = provider_id or str(getattr(model, "name", "quantum-model"))

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
            logger.warning(
                "quantum_model_adapter_error", provider=self._provider_id, error=str(exc)
            )
            return ThreatPrediction(
                provider_id=self._provider_id,
                predicted_label="unknown",
                confidence=0.0,
                is_valid=False,
                error_message=str(exc),
            )

        predicted_class = raw.get("predicted_class", raw.get("predicted_label", "unknown"))
        confidence = float(raw.get("confidence", 0.0))
        probs = raw.get("probabilities", raw.get("predictions", {}))
        category = str(predicted_class)

        raw_risk = raw.get("risk_score")
        benign_prob = None
        if isinstance(probs, dict) and ("0" in probs or "benign" in probs):
            benign_key = "benign" if "benign" in probs else "0"
            try:
                benign_prob = float(probs[benign_key])
            except (TypeError, ValueError):
                benign_prob = None
        if benign_prob is not None:
            risk_score = max(0.0, min(1.0, 1.0 - benign_prob))
        elif raw_risk is not None:
            risk_score = float(raw_risk)
        elif category in ("0", "benign", "unknown"):
            risk_score = max(0.0, 1.0 - confidence)
        else:
            risk_score = min(1.0, confidence)

        backend = ""
        if hasattr(self._model, "quantum_metadata"):
            qm = self._model.quantum_metadata
            if hasattr(qm, "backend_type"):
                backend = (
                    str(qm.backend_type.value)
                    if hasattr(qm.backend_type, "value")
                    else str(qm.backend_type)
                )

        # Normalize into the shared {benign, threat} label space (see
        # ClassicalModelProvider). "0"/"benign" -> benign, anything else
        # (threat class index or category name) -> threat.
        label = "benign" if category in ("0", "benign") else "threat"
        threat_prob = max(0.0, min(1.0, risk_score))
        benign_prob = 1.0 - threat_prob
        return ThreatPrediction(
            provider_id=self._provider_id,
            predicted_label=label,
            confidence=round(threat_prob if label == "threat" else benign_prob, 6),
            probabilities={
                "benign": round(benign_prob, 6),
                "threat": round(threat_prob, 6),
            },
            risk_score=round(threat_prob, 6),
            model_name=self._provider_id,
            backend=backend,
            metadata={"raw_result": raw, "predicted_category": category},
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
