"""HybridFusionEngine — the main orchestrator of the Hybrid Intelligence Layer.

Consumes only PredictionProvider outputs (ThreatPrediction objects).
Never knows which algorithms produced them.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from q_guardian.quantum.fusion.calibrator import ConfidenceCalibrator
from q_guardian.quantum.fusion.prediction import ThreatPrediction
from q_guardian.quantum.fusion.providers import PredictionProvider
from q_guardian.quantum.fusion.strategies.base import FusionStrategy, FusedPrediction
from q_guardian.quantum.fusion.strategies.stacking import StackingFusionStrategy
from q_guardian.quantum.exceptions import ConfigurationError, FusionError

logger = structlog.get_logger("quantum.fusion.engine")


class HybridFusionEngine:
    """Orchestrates hybrid fusion across heterogeneous prediction sources.

    Architecture:
      1. Register PredictionProviders (rule, classical, quantum, external)
      2. Register FusionStrategies (swap at runtime)
      3. fuse() collects predictions from all providers, calibrates,
         and delegates to the active strategy.
      4. Produces a FusedPrediction with explainability metadata.

    The engine never imports or references specific algorithms. It
    depends only on PredictionProvider, ThreatPrediction, and
    FusionStrategy.
    """

    def __init__(
        self,
        strategy: FusionStrategy | None = None,
        calibrator: ConfidenceCalibrator | None = None,
        provider_weights: dict[str, float] | None = None,
    ) -> None:
        self._providers: dict[str, PredictionProvider] = {}
        self._strategies: dict[str, FusionStrategy] = {}
        self._active_strategy: FusionStrategy = strategy or StackingFusionStrategy()
        self._calibrator = calibrator or ConfidenceCalibrator(method="none")
        self._provider_weights = provider_weights or {}
        self._fusion_history: list[dict[str, Any]] = []
        self._total_fusions = 0
        self._total_provider_failures = 0

        self._strategies[self._active_strategy.name] = self._active_strategy

    @property
    def active_strategy_name(self) -> str:
        return self._active_strategy.name

    @property
    def active_strategy(self) -> FusionStrategy:
        return self._active_strategy

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    @property
    def strategy_count(self) -> int:
        return len(self._strategies)

    @property
    def total_fusions(self) -> int:
        return self._total_fusions

    @property
    def total_provider_failures(self) -> int:
        return self._total_provider_failures

    @property
    def calibrator(self) -> ConfidenceCalibrator:
        return self._calibrator

    # ── Provider management ─────────────────────────────────────────────

    def register_provider(
        self,
        provider: PredictionProvider,
        weight: float | None = None,
    ) -> None:
        """Register a prediction provider."""
        self._providers[provider.provider_id] = provider
        if weight is not None:
            self._provider_weights[provider.provider_id] = weight

        logger.info(
            "provider_registered",
            provider_id=provider.provider_id,
            provider_type=provider.provider_type,
            weight=weight,
        )

    def unregister_provider(self, provider_id: str) -> bool:
        """Remove a prediction provider."""
        if provider_id not in self._providers:
            return False
        del self._providers[provider_id]
        self._provider_weights.pop(provider_id, None)
        logger.info("provider_unregistered", provider_id=provider_id)
        return True

    def get_provider(self, provider_id: str) -> PredictionProvider | None:
        return self._providers.get(provider_id)

    @property
    def provider_ids(self) -> list[str]:
        return list(self._providers.keys())

    # ── Strategy management ─────────────────────────────────────────────

    def register_strategy(self, strategy: FusionStrategy) -> None:
        """Register a fusion strategy for dynamic switching."""
        self._strategies[strategy.name] = strategy
        logger.info("strategy_registered", strategy_name=strategy.name)

    def unregister_strategy(self, strategy_name: str) -> bool:
        if strategy_name not in self._strategies:
            return False
        if strategy_name == self._active_strategy.name:
            raise FusionError(f"Cannot unregister the active strategy '{strategy_name}'")
        del self._strategies[strategy_name]
        return True

    def set_strategy(self, strategy_name: str) -> None:
        """Switch the active fusion strategy at runtime."""
        if strategy_name not in self._strategies:
            raise ConfigurationError(
                f"Strategy '{strategy_name}' not registered. "
                f"Available: {list(self._strategies.keys())}"
            )
        old = self._active_strategy.name
        self._active_strategy = self._strategies[strategy_name]
        logger.info("strategy_switched", old=old, new=strategy_name)

    @property
    def available_strategies(self) -> list[str]:
        return list(self._strategies.keys())

    # ── Core fusion ─────────────────────────────────────────────────────

    async def fuse(
        self,
        prompt: str,
        features: dict[str, Any] | None = None,
        strategy_name: str | None = None,
        weights: dict[str, float] | None = None,
        calibrate: bool = True,
        **kwargs: Any,
    ) -> FusedPrediction:
        """Collect predictions from all providers and fuse them.

        Args:
            prompt: The raw prompt text.
            features: Optional pre-extracted features.
            strategy_name: Override the active strategy for this call.
            weights: Override provider weights for this call.
            calibrate: Whether to apply confidence calibration.
            **kwargs: Extra arguments passed to the strategy.

        Returns:
            FusedPrediction combining all provider outputs.
        """
        start = time.monotonic()

        predictions = await self._collect_predictions(prompt, features)

        if calibrate:
            predictions = self._calibrator.calibrate(predictions)

        strategy = self._get_strategy(strategy_name)
        effective_weights = {**self._provider_weights, **(weights or {})}

        try:
            fused = strategy.fuse(predictions, effective_weights, **kwargs)
        except Exception as exc:
            logger.error(
                "fusion_failed",
                strategy=strategy.name,
                error=str(exc),
            )
            fused = FusedPrediction(
                predicted_label="unknown",
                confidence=0.0,
                strategy_name=strategy.name,
                source_predictions=predictions,
                num_providers=len(predictions),
                num_failed=len(predictions),
                reasoning_summary=f"Fusion failed: {exc}",
                metadata={"error": str(exc)},
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        fused.metadata["fusion_latency_ms"] = round(elapsed_ms, 3)

        self._total_fusions += 1
        self._record_fusion(fused, elapsed_ms)

        logger.info(
            "fusion_completed",
            strategy=strategy.name,
            predicted_label=fused.predicted_label,
            confidence=fused.confidence,
            num_providers=fused.num_providers,
            latency_ms=round(elapsed_ms, 3),
        )

        return fused

    async def _collect_predictions(
        self,
        prompt: str,
        features: dict[str, Any] | None,
    ) -> list[ThreatPrediction]:
        """Collect predictions from all registered providers."""
        predictions: list[ThreatPrediction] = []

        for provider_id, provider in self._providers.items():
            try:
                pred = await provider.predict(prompt, features)
                predictions.append(pred)
            except Exception as exc:
                self._total_provider_failures += 1
                logger.warning(
                    "provider_failed",
                    provider_id=provider_id,
                    error=str(exc),
                )
                predictions.append(ThreatPrediction(
                    provider_id=provider_id,
                    predicted_label="unknown",
                    confidence=0.0,
                    is_valid=False,
                    error_message=str(exc),
                ))

        return predictions

    def _get_strategy(self, strategy_name: str | None) -> FusionStrategy:
        if strategy_name is None:
            return self._active_strategy
        if strategy_name not in self._strategies:
            raise ConfigurationError(
                f"Strategy '{strategy_name}' not registered. "
                f"Available: {list(self._strategies.keys())}"
            )
        return self._strategies[strategy_name]

    def _record_fusion(self, fused: FusedPrediction, elapsed_ms: float) -> None:
        record = {
            "fused_id": fused.fused_id,
            "strategy": fused.strategy_name,
            "predicted_label": fused.predicted_label,
            "confidence": fused.confidence,
            "num_providers": fused.num_providers,
            "num_failed": fused.num_failed,
            "latency_ms": round(elapsed_ms, 3),
        }
        self._fusion_history.append(record)
        if len(self._fusion_history) > 500:
            self._fusion_history = self._fusion_history[-500:]

    # ── Performance / health ────────────────────────────────────────────

    def get_performance_stats(self) -> dict[str, Any]:
        if not self._fusion_history:
            return {
                "total_fusions": self._total_fusions,
                "total_provider_failures": self._total_provider_failures,
                "history_size": 0,
            }

        latencies = [r["latency_ms"] for r in self._fusion_history]
        return {
            "total_fusions": self._total_fusions,
            "total_provider_failures": self._total_provider_failures,
            "history_size": len(self._fusion_history),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 3),
            "min_latency_ms": round(min(latencies), 3),
            "max_latency_ms": round(max(latencies), 3),
            "strategy_usage": self._get_strategy_usage(),
        }

    def _get_strategy_usage(self) -> dict[str, int]:
        usage: dict[str, int] = {}
        for record in self._fusion_history:
            s = record.get("strategy", "unknown")
            usage[s] = usage.get(s, 0) + 1
        return usage

    def health(self) -> dict[str, Any]:
        providers_health = {}
        for pid, provider in self._providers.items():
            try:
                providers_health[pid] = provider.health()
            except Exception as exc:
                providers_health[pid] = {"status": "error", "error": str(exc)}

        return {
            "provider_count": self.provider_count,
            "strategy_count": self.strategy_count,
            "active_strategy": self.active_strategy_name,
            "performance": self.get_performance_stats(),
            "calibration": self._calibrator.get_stats(),
            "providers": providers_health,
            "strategies": {
                name: s.health() for name, s in self._strategies.items()
            },
        }

    def clear_history(self) -> int:
        count = len(self._fusion_history)
        self._fusion_history.clear()
        return count
