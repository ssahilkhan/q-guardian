from __future__ import annotations

import math
from datetime import UTC, datetime

import structlog

from q_guardian.observability.data import TimeWindow, TrendData
from q_guardian.observability.enums import TrendDirection
from q_guardian.observability.analytics.statistics import StatisticsEngine

logger = structlog.get_logger("observability.analytics.trend")


class TrendAnalyzer:
    """Trend detection and classification engine."""

    def __init__(self) -> None:
        self._stats = StatisticsEngine()
        logger.debug("trend_analyzer_created")

    def analyze(
        self,
        name: str,
        values: list[float],
        timestamps: list[datetime] | None = None,
    ) -> TrendData:
        if not values:
            return TrendData(
                metric_name=name,
                direction=TrendDirection.STABLE,
                slope=0.0,
                r_squared=0.0,
                mean=0.0,
                std_dev=0.0,
                min_value=0.0,
                max_value=0.0,
                sample_count=0,
            )
        mean_val = self._stats.mean(values)
        std_val = self._stats.std_dev(values)
        min_val = self._stats.min_val(values) or 0.0
        max_val = self._stats.max_val(values) or 0.0
        x_values = list(range(len(values)))
        slope, _, r_squared = self._stats.linear_regression(x_values, values)
        direction = self.classify_direction(slope, std_val)
        period = None
        if timestamps and len(timestamps) >= 2:
            period = TimeWindow(start=timestamps[0], end=timestamps[-1])
        trend = TrendData(
            metric_name=name,
            direction=direction,
            slope=slope,
            r_squared=r_squared,
            mean=mean_val,
            std_dev=std_val,
            min_value=min_val,
            max_value=max_val,
            sample_count=len(values),
            period=period,
        )
        logger.debug(
            "trend_analyzed",
            metric_name=name,
            direction=direction.value,
            slope=slope,
            r_squared=r_squared,
            sample_count=len(values),
        )
        return trend

    def classify_direction(self, slope: float, std_dev: float) -> TrendDirection:
        if std_dev == 0 and slope == 0:
            return TrendDirection.STABLE
        normalized_slope = abs(slope) / std_dev if std_dev > 0 else abs(slope)
        if normalized_slope < 0.05:
            if std_dev > 0 and (self._stats.mean([abs(slope), std_dev]) > 0):
                coefficient_of_variation = std_dev / self._stats.mean([abs(slope), std_dev]) if self._stats.mean([abs(slope), std_dev]) > 0 else 0
                if coefficient_of_variation > 1.0:
                    return TrendDirection.VOLATILE
            return TrendDirection.STABLE
        if normalized_slope > 0.5:
            return TrendDirection.VOLATILE
        if slope > 0:
            return TrendDirection.INCREASING
        return TrendDirection.DECREASING

    def detect_anomalies(
        self, values: list[float], threshold: float = 2.0
    ) -> list[int]:
        if len(values) < 3:
            return []
        mean_val = self._stats.mean(values)
        std_val = self._stats.std_dev(values)
        if std_val == 0:
            return []
        anomaly_indices: list[int] = []
        for i, v in enumerate(values):
            z_score = abs(v - mean_val) / std_val
            if z_score > threshold:
                anomaly_indices.append(i)
        return anomaly_indices

    def compute_moving_trend(
        self, values: list[float], window: int = 10
    ) -> list[TrendDirection]:
        if not values or window <= 0:
            return []
        directions: list[TrendDirection] = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            subset = values[start : i + 1]
            if len(subset) < 2:
                directions.append(TrendDirection.STABLE)
                continue
            x_vals = list(range(len(subset)))
            slope, _, r_squared = self._stats.linear_regression(x_vals, subset)
            std_val = self._stats.std_dev(subset)
            directions.append(self.classify_direction(slope, std_val))
        return directions
