"""ConfidenceEngine — normalizes and aggregates confidence scores.

Provides calibration, confidence intervals, and aggregation across
multiple prediction sources.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from q_guardian.risk.config import ConfidenceConfig
from q_guardian.risk.data import ConfidenceScore
from q_guardian.risk.enums import ConfidenceMethod

logger = structlog.get_logger("risk.confidence_engine")


class ConfidenceEngine:
    """Normalizes, calibrates, and aggregates confidence scores.

    Supports:
      - pass-through (none)
      - temperature scaling
      - min-max normalization
      - z-score normalization
      - weighted average aggregation
      - confidence interval estimation
    """

    def __init__(self, config: ConfidenceConfig | None = None) -> None:
        self._config = config or ConfidenceConfig()
        self._running_mean: float = 0.0
        self._running_m2: float = 0.0
        self._running_count: int = 0
        self._running_min: float = float("inf")
        self._running_max: float = float("-inf")

    @property
    def config(self) -> ConfidenceConfig:
        return self._config

    def normalize(self, raw_confidence: float) -> ConfidenceScore:
        """Normalize a single confidence score using the configured method.

        Args:
            raw_confidence: Raw confidence value 0-1.

        Returns:
            ConfidenceScore with normalized value.
        """
        clamped = max(0.0, min(1.0, raw_confidence))
        self._update_running_stats(clamped)
        normalized = self._apply_method(clamped)
        interval = self._compute_interval(normalized)

        return ConfidenceScore(
            raw_confidence=clamped,
            normalized_confidence=normalized,
            method=self._config.method,
            confidence_interval=interval,
            aggregation_count=1,
        )

    def aggregate(
        self,
        confidences: list[float],
        weights: list[float] | None = None,
    ) -> ConfidenceScore:
        """Aggregate multiple confidence scores into a single value.

        Args:
            confidences: List of confidence values.
            weights: Optional weights (same length as confidences).

        Returns:
            ConfidenceScore with aggregated and normalized value.
        """
        if not confidences:
            return ConfidenceScore(
                raw_confidence=0.0,
                normalized_confidence=0.0,
                method=self._config.method,
                aggregation_count=0,
            )

        for c in confidences:
            self._update_running_stats(c)

        if weights is None:
            weights = [1.0 / len(confidences)] * len(confidences)
        else:
            total_w = sum(weights)
            if total_w > 0:
                weights = [w / total_w for w in weights]
            else:
                weights = [1.0 / len(confidences)] * len(confidences)

        if self._config.aggregation_method == "weighted_average":
            raw_agg = sum(c * w for c, w in zip(confidences, weights))
        elif self._config.aggregation_method == "geometric_mean":
            product = 1.0
            for c, w in zip(confidences, weights):
                product *= max(c, 1e-10) ** w
            raw_agg = product
        else:
            raw_agg = sum(c * w for c, w in zip(confidences, weights))

        raw_agg = max(0.0, min(1.0, raw_agg))
        normalized = self._apply_method(raw_agg)
        interval = self._compute_interval(normalized)

        return ConfidenceScore(
            raw_confidence=raw_agg,
            normalized_confidence=normalized,
            method=self._config.method,
            confidence_interval=interval,
            aggregation_count=len(confidences),
        )

    def reset(self) -> None:
        """Reset running statistics."""
        self._running_mean = 0.0
        self._running_m2 = 0.0
        self._running_count = 0
        self._running_min = float("inf")
        self._running_max = float("-inf")

    def _apply_method(self, confidence: float) -> float:
        """Apply the configured normalization method."""
        if self._config.method == ConfidenceMethod.TEMPERATURE:
            return self._temperature_scale(confidence)
        elif self._config.method == ConfidenceMethod.MIN_MAX:
            return self._min_max_normalize(confidence)
        elif self._config.method == ConfidenceMethod.Z_SCORE:
            return self._z_score_normalize(confidence)
        return max(0.0, min(1.0, confidence))

    def _temperature_scale(self, confidence: float) -> float:
        """Apply temperature scaling."""
        T = self._config.temperature
        if T <= 0:
            return confidence
        logit = math.log(max(confidence, 1e-10) / max(1 - confidence, 1e-10))
        scaled = 1.0 / (1.0 + math.exp(-logit / T))
        return max(0.0, min(1.0, scaled))

    def _min_max_normalize(self, confidence: float) -> float:
        """Min-max normalization using running stats."""
        if self._running_count < 2:
            return confidence
        range_val = self._running_max - self._running_min
        if range_val < 1e-10:
            return 0.5
        return max(0.0, min(1.0, (confidence - self._running_min) / range_val))

    def _z_score_normalize(self, confidence: float) -> float:
        """Z-score normalization then sigmoid."""
        if self._running_count < 2:
            return confidence
        variance = self._running_m2 / (self._running_count - 1) if self._running_count > 1 else 0.0
        std = math.sqrt(variance)
        if std < 1e-10:
            return confidence
        z = (confidence - self._running_mean) / std
        calibrated = 1.0 / (1.0 + math.exp(-z))
        return max(0.0, min(1.0, calibrated))

    def _compute_interval(self, confidence: float) -> tuple[float, float]:
        """Compute approximate confidence interval."""
        if self._running_count < 2:
            return (max(0.0, confidence - 0.1), min(1.0, confidence + 0.1))
        variance = self._running_m2 / (self._running_count - 1) if self._running_count > 1 else 0.0
        std = math.sqrt(variance)
        margin = 1.96 * std / math.sqrt(self._running_count)
        return (max(0.0, confidence - margin), min(1.0, confidence + margin))

    def _update_running_stats(self, value: float) -> None:
        """Update Welford's online algorithm for running mean/variance."""
        self._running_count += 1
        delta = value - self._running_mean
        self._running_mean += delta / self._running_count
        delta2 = value - self._running_mean
        self._running_m2 += delta * delta2
        self._running_min = min(self._running_min, value)
        self._running_max = max(self._running_max, value)
