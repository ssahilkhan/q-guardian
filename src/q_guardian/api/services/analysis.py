"""AnalysisService — thin API facade over the existing detection pipeline.

Reuses :class:`ThreatAnalysisPlugin` (normalize -> validate -> features ->
rules -> optional ML/quantum -> decision) without duplicating any detection
logic, and keeps a bounded in-memory scan history for the console UI.

The service is deliberately read-mostly: the only mutation it exposes is
submitting a prompt through the existing scan pipeline.
"""

from __future__ import annotations

import asyncio
import importlib.util
from collections import deque
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from q_guardian.config.settings import SecuritySettings, get_settings
from q_guardian.ml.config import MLConfig
from q_guardian.ml.plugin import ThreatAnalysisPlugin
from q_guardian.security.config import PromptSecurityConfig

if TYPE_CHECKING:
    from q_guardian.security.pipeline import RuleEngine

MAX_HISTORY = 200

# Quantum backends shipped with the framework. Names match the `name`
# properties in q_guardian.quantum.backends. `requires` is the optional
# SDK whose presence determines runtime availability.
_QUANTUM_BACKENDS: tuple[dict[str, str], ...] = (
    {
        "name": "local-simulator",
        "requires": "",
        "description": "Pure-Python statevector simulator (no external SDK)",
    },
    {
        "name": "qiskit-aer",
        "requires": "qiskit_aer",
        "description": "Qiskit Aer statevector and qasm simulators",
    },
    {
        "name": "qiskit-runtime",
        "requires": "qiskit_ibm_runtime",
        "description": "Qiskit IBM Runtime remote backend",
    },
)

# Pipeline stage inventory for the console components view.
_COMPONENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "normalize",
        "name": "Normalization",
        "status": "active",
        "detail": "Unicode NFKC, hidden-character stripping, whitespace collapsing",
    },
    {
        "id": "validate",
        "name": "Validation",
        "status": "active",
        "detail": "Length, line, encoding and structural input limits",
    },
    {
        "id": "features",
        "name": "Feature Extraction",
        "status": "active",
        "detail": "Statistical, keyword and structural prompt features",
    },
    {
        "id": "rules",
        "name": "Rule Engine",
        "status": "active",
        "detail": "Built-in and custom detection rules",
    },
    {
        "id": "ml",
        "name": "Classical ML",
        "status": "available",
        "detail": "Isolation Forest, Random Forest and XGBoost detectors",
    },
    {
        "id": "quantum",
        "name": "Quantum",
        "status": "available",
        "detail": "Local simulator plus optional Qiskit backends",
    },
    {
        "id": "decision",
        "name": "Decision Engine",
        "status": "active",
        "detail": "ALLOW / WARN / REVIEW / BLOCK cascade",
    },
    {
        "id": "response",
        "name": "Response Orchestration",
        "status": "available",
        "detail": "Playbooks, quarantine and recovery actions",
    },
)

# Keys never exposed by the configuration endpoint, regardless of source.
_REDACTED_KEYS = frozenset(
    {"secret_key", "api_key", "password", "token", "client_secret", "private_key"}
)


def _redact_url(url: str) -> str:
    """Return a URL with any embedded credentials redacted."""
    if not url:
        return ""
    if "://" not in url:
        return "<redacted>"
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        _, host = rest.rsplit("@", 1)
        return f"{scheme}://***@{host}"
    return f"{scheme}://{rest}"


class AnalysisService:
    """Facade exposing the existing pipeline to the API layer."""

    def __init__(self, history_limit: int = MAX_HISTORY) -> None:
        self._plugin = ThreatAnalysisPlugin()
        self._history: deque[dict[str, Any]] = deque(maxlen=history_limit)
        self._lock = asyncio.Lock()

    @property
    def plugin(self) -> ThreatAnalysisPlugin:
        """Return the underlying threat analysis plugin."""
        return self._plugin

    @property
    def rule_engine(self) -> RuleEngine:
        """Return the rule engine used by the pipeline."""
        return self._plugin.rule_engine

    async def scan(self, prompt: str) -> dict[str, Any]:
        """Run the existing scan pipeline on a prompt and record the result."""
        result = await self._plugin.scan_prompt(prompt)
        async with self._lock:
            self._history.appendleft(result)
        return result

    def history(self) -> list[dict[str, Any]]:
        """Return the bounded scan history (most recent first)."""
        return list(self._history)

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        """Return a single analysis result by ID, or None."""
        for result in self._history:
            if result.get("analysis_id") == analysis_id:
                return result
        return None

    def rules(self) -> list[dict[str, Any]]:
        """Return the enabled detection rules as JSON-safe dicts."""
        return [rule.model_dump() for rule in self.rule_engine.list_rules()]

    def components(self) -> list[dict[str, Any]]:
        """Return the pipeline stage inventory with live status."""
        rule_count = len(self.rule_engine.list_rules())
        ml_active = self._ml_active
        return [
            {**component, "detail": self._component_detail(component, rule_count, ml_active)}
            for component in _COMPONENTS
        ]

    def models_status(self) -> dict[str, Any]:
        """Return ML model and quantum backend status."""
        manager = self._plugin.model_manager
        models = [
            {
                "name": meta.name,
                "model_type": meta.model_type.value,
                "backend": meta.backend.value,
                "version": meta.version,
                "status": meta.status.value,
                "description": meta.description,
            }
            for meta in manager.list_models()
        ]
        quantum = [
            {
                "name": backend["name"],
                "requires": backend["requires"],
                "description": backend["description"],
                "installed": self._sdk_installed(backend["requires"]),
            }
            for backend in _QUANTUM_BACKENDS
        ]
        return {
            "ml": {
                "active": self._ml_active,
                "detector_count": self._plugin.inference_engine.detector_count,
                "classifier_count": self._plugin.inference_engine.classifier_count,
                "total_models": manager.health()["total_models"],
                "loaded_models": manager.health()["loaded_models"],
                "models": models,
            },
            "quantum": {
                "active": False,
                "fusion_strategies": [
                    "weighted_voting",
                    "confidence_based",
                    "stacking",
                    "adaptive",
                    "bayesian",
                    "max_confidence",
                ],
                "backends": quantum,
            },
        }

    def configuration(self) -> dict[str, Any]:
        """Return a sanitized view of application configuration.

        Never includes secrets (secret keys, tokens, passwords, raw URLs
        with credentials) or internal filesystem paths.
        """
        settings = get_settings()
        prompt_config = PromptSecurityConfig()
        ml_config = MLConfig()
        return {
            "application": {
                "name": settings.app.name,
                "version": settings.app.version,
                "environment": settings.app.environment.value,
                "debug": settings.app.debug,
                "host": settings.app.host,
                "port": settings.app.port,
            },
            "database": {
                "configured": bool(settings.database.url),
                "database": settings.database.database,
                "url_redacted": _redact_url(settings.database.url),
            },
            "security": {
                "jwt_algorithm": settings.security.jwt_algorithm,
                "jwt_expiration_minutes": settings.security.jwt_expiration_minutes,
                "secret_key_configured": _is_secret_key_configured(settings.security),
            },
            "prompt_security": _safe_dict(prompt_config.model_dump()),
            "ml": {
                "enabled": ml_config.enabled,
                "auto_save": ml_config.auto_save,
                "anomaly_threshold": ml_config.anomaly_threshold,
                "classification_threshold": ml_config.classification_threshold,
                "max_features": ml_config.max_features,
                "xgboost_available": ml_config.xgboost_available,
                "models_directory_configured": bool(str(ml_config.model_storage_path)),
            },
        }

    def summary(self) -> dict[str, Any]:
        """Return overview aggregates for the landing page."""
        rules = self.rule_engine.list_rules()
        ml = self.models_status()["ml"]
        history = self.history()
        decisions = [result.get("decision", "") for result in history]
        return {
            "components": self.components(),
            "rules": {
                "total": len(rules),
                "enabled": sum(1 for rule in rules if rule.enabled),
            },
            "ml": ml,
            "quantum": self.models_status()["quantum"],
            "history": {
                "total": len(history),
                "blocked": decisions.count("BLOCK"),
                "review": decisions.count("REVIEW"),
                "warn": decisions.count("WARN"),
                "allowed": decisions.count("ALLOW"),
            },
        }

    @property
    def _ml_active(self) -> bool:
        return (
            self._plugin.inference_engine.detector_count
            + self._plugin.inference_engine.classifier_count
        ) > 0

    @staticmethod
    def _component_detail(component: dict[str, Any], rule_count: int, ml_active: bool) -> str:
        if component["id"] == "rules":
            return f"Built-in and custom detection rules ({rule_count} registered)"
        if component["id"] == "ml":
            return (
                "Isolation Forest, Random Forest and XGBoost detectors (active)"
                if ml_active
                else "Isolation Forest, Random Forest and XGBoost detectors (no models loaded)"
            )
        return str(component["detail"])

    @staticmethod
    def _sdk_installed(module: str) -> bool:
        return not module or importlib.util.find_spec(module) is not None


@lru_cache(maxsize=1)
def get_analysis_service() -> AnalysisService:
    """Return the shared AnalysisService singleton.

    Cached so every API endpoint and the console UI observe the same
    pipeline instance and the same bounded scan history.
    """
    return AnalysisService()


def _is_secret_key_configured(settings: SecuritySettings) -> bool:
    """Return True when a non-default secret key is configured."""
    value = settings.secret_key
    return bool(value) and value != "change-me-to-a-random-secret-key"


def _safe_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively drop any key that must never be exposed."""
    return {key: _safe_value(value) for key, value in payload.items() if _is_safe_key(key)}


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _safe_dict(value)
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return value


def _is_safe_key(key: str) -> bool:
    lowered = key.lower()
    return not any(redacted in lowered for redacted in _REDACTED_KEYS)
