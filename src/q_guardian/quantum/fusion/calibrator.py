"""ConfidenceCalibrator — normalizes confidence scores across heterogeneous models.

Different models produce confidence scores on different scales and with
different biases. The calibrator applies normalization so that the
Fusion Engine can compare and combine scores fairly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

if TYPE_CHECKING:
    from q_guardian.quantum.fusion.prediction import ThreatPrediction

logger = structlog.get_logger("quantum.fusion.calibrator")


class ConfidenceCalibrator:
    """Normalizes confidence scores from heterogeneous prediction sources.

    Supported methods:
      - min_max: Scale to [0, 1] based on observed min/max per provider.
      - z_score: Standardize to z-scores, then map through sigmoid.
      - temperature: Apply temperature scaling T.
      - none: Pass through unmodified.

    The calibrator maintains per-provider statistics so that it can
    normalize scores from models with very different confidence ranges.
    """

    def __init__(
        self,
        method: str = "none",
        temperature: float = 1.0,
        smoothing: float = 0.01,
    ) -> None:
        self._method = method
        self._temperature = temperature
        self._smoothing = smoothing
        self._provider_stats: dict[str, _ProviderStats] = {}
        self._global_min = float("inf")
        self._global_max = float("-inf")

    @property
    def method(self) -> str:
        return self._method

    @property
    def temperature(self) -> float:
        return self._temperature

    def calibrate(
        self,
        predictions: list[ThreatPrediction],
    ) -> list[ThreatPrediction]:
        """Calibrate confidence scores for a batch of predictions.

        Updates internal statistics and returns new predictions with
        calibrated confidence scores. Original predictions are not mutated.
        """
        if not predictions:
            return []

        for pred in predictions:
            self._update_stats(pred.provider_id, pred.confidence)

        if self._method == "none":
            return list(predictions)

        calibrated: list[ThreatPrediction] = []
        for pred in predictions:
            new_confidence = self._apply_calibration(pred.provider_id, pred.confidence)
            new_probabilities = self._calibrate_probabilities(pred.probabilities, pred.provider_id)

            calibrated_pred = pred.model_copy(
                update={
                    "confidence": round(new_confidence, 6),
                    "probabilities": new_probabilities,
                    "metadata": {**pred.metadata, "calibration_method": self._method},
                }
            )
            calibrated.append(calibrated_pred)

        logger.debug(
            "confidence_calibrated",
            method=self._method,
            count=len(predictions),
            provider_ids=[p.provider_id for p in predictions],
        )

        return calibrated

    def reset(self) -> None:
        """Reset all accumulated statistics."""
        self._provider_stats.clear()
        self._global_min = float("inf")
        self._global_max = float("-inf")

    def get_stats(self) -> dict[str, Any]:
        """Return calibration statistics per provider."""
        return {
            "method": self._method,
            "temperature": self._temperature,
            "global_min": self._global_min if self._global_min != float("inf") else None,
            "global_max": self._global_max if self._global_max != float("-inf") else None,
            "providers": {
                pid: {
                    "count": s.count,
                    "mean": round(s.mean, 4),
                    "std": round(s.std, 4),
                    "min": round(s.min, 4),
                    "max": round(s.max, 4),
                }
                for pid, s in self._provider_stats.items()
            },
        }

    def _update_stats(self, provider_id: str, confidence: float) -> None:
        """Update running statistics for a provider."""
        if provider_id not in self._provider_stats:
            self._provider_stats[provider_id] = _ProviderStats()

        stats = self._provider_stats[provider_id]
        stats.update(confidence)

        self._global_min = min(self._global_min, confidence)
        self._global_max = max(self._global_max, confidence)

    def _apply_calibration(self, provider_id: str, confidence: float) -> float:
        """Apply the selected calibration method."""
        if self._method == "temperature":
            return self._temperature_scale(confidence)
        elif self._method == "min_max":
            return self._min_max_normalize(provider_id, confidence)
        elif self._method == "z_score":
            return self._z_score_normalize(provider_id, confidence)
        else:
            return confidence

    def _temperature_scale(self, confidence: float) -> float:
        """Apply temperature scaling: sigmoid(logit(confidence) / T)."""
        if self._temperature <= 0:
            return confidence
        logit = np.clip(np.log(confidence / max(1 - confidence, 1e-10)), -10, 10)
        scaled = 1.0 / (1.0 + np.exp(-logit / self._temperature))
        return float(np.clip(scaled, 0.0, 1.0))

    def _min_max_normalize(self, provider_id: str, confidence: float) -> float:
        """Min-max normalization per provider."""
        stats = self._provider_stats.get(provider_id)
        if stats is None or stats.count < 2:
            return confidence
        range_val = stats.max - stats.min
        if range_val < 1e-10:
            return 0.5
        return float(np.clip((confidence - stats.min) / range_val, 0.0, 1.0))

    def _z_score_normalize(self, provider_id: str, confidence: float) -> float:
        """Z-score normalization then sigmoid mapping."""
        stats = self._provider_stats.get(provider_id)
        if stats is None or stats.count < 2 or stats.std < 1e-10:
            return confidence
        z = (confidence - stats.mean) / stats.std
        calibrated = 1.0 / (1.0 + np.exp(-z))
        return float(np.clip(calibrated, 0.0, 1.0))

    def _calibrate_probabilities(
        self,
        probabilities: dict[str, float],
        provider_id: str,
    ) -> dict[str, float]:
        """Calibrate probability distributions (temperature scaling)."""
        if self._method == "none" or not probabilities:
            return dict(probabilities)

        if self._method == "temperature" and self._temperature > 0:
            logits = {
                k: np.clip(np.log(max(v, 1e-10) / max(1 - v, 1e-10)), -10, 10)
                for k, v in probabilities.items()
            }
            scaled = {k: v / self._temperature for k, v in logits.items()}
            max_s = max(scaled.values())
            exp_s = {k: np.exp(v - max_s) for k, v in scaled.items()}
            total = sum(exp_s.values())
            return {k: round(float(v / total), 6) for k, v in exp_s.items()}

        return dict(probabilities)


class _ProviderStats:
    """Running statistics for a single provider."""

    __slots__ = ("count", "m2", "max", "mean", "min")

    def __init__(self) -> None:
        self.count: int = 0
        self.mean: float = 0.0
        self.m2: float = 0.0
        self.min: float = float("inf")
        self.max: float = float("-inf")

    @property
    def std(self) -> float:
        if self.count < 2:
            return 0.0
        return float((self.m2 / (self.count - 1)) ** 0.5)

    def update(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2
        self.min = min(self.min, value)
        self.max = max(self.max, value)
