from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import structlog

from q_guardian.observability.analytics.statistics import StatisticsEngine
from q_guardian.observability.data import ForecastResult, MetricPoint

logger = structlog.get_logger("observability.analytics.forecasting")


class ForecastEngine:
    """Statistical forecasting engine for metric predictions."""

    def __init__(self) -> None:
        self._stats = StatisticsEngine()
        logger.debug("forecast_engine_created")

    def linear_forecast(
        self,
        values: list[float],
        horizon: int,
        timestamps: list[datetime] | None = None,
    ) -> ForecastResult:
        if not values or horizon <= 0:
            return ForecastResult(
                metric_name="",
                method="linear",
                forecast_values=[],
                confidence_interval_lower=[],
                confidence_interval_upper=[],
            )
        x_values = [float(i) for i in range(len(values))]
        slope, intercept, r_squared = self._stats.linear_regression(x_values, values)
        std_val = self._stats.std_dev(values) if len(values) > 1 else 0.0
        base_timestamp = self._resolve_base_timestamp(timestamps, values)
        forecast_points: list[MetricPoint] = []
        lower_points: list[MetricPoint] = []
        upper_points: list[MetricPoint] = []
        n = len(values)
        margin_of_error = 1.96 * std_val * math.sqrt(1 + 1.0 / n) if n > 1 else 0.0
        for i in range(1, horizon + 1):
            predicted = slope * (n + i - 1) + intercept
            ts = base_timestamp + timedelta(hours=i)
            forecast_points.append(MetricPoint(timestamp=ts, value=predicted))
            lower_points.append(MetricPoint(timestamp=ts, value=predicted - margin_of_error))
            upper_points.append(MetricPoint(timestamp=ts, value=predicted + margin_of_error))
        result = ForecastResult(
            metric_name="",
            method="linear",
            forecast_values=forecast_points,
            confidence_interval_lower=lower_points,
            confidence_interval_upper=upper_points,
            confidence_level=0.95,
        )
        logger.debug(
            "linear_forecast_generated",
            horizon=horizon,
            slope=slope,
            r_squared=r_squared,
        )
        return result

    def moving_average_forecast(
        self,
        values: list[float],
        horizon: int,
        window: int = 5,
    ) -> ForecastResult:
        if not values or horizon <= 0:
            return ForecastResult(
                metric_name="",
                method="moving_average",
                forecast_values=[],
                confidence_interval_lower=[],
                confidence_interval_upper=[],
            )
        effective_window = min(window, len(values))
        recent = values[-effective_window:]
        avg = self._stats.mean(recent)
        std_val = self._stats.std_dev(recent) if len(recent) > 1 else 0.0
        base_timestamp = datetime.now(UTC)
        forecast_points: list[MetricPoint] = []
        lower_points: list[MetricPoint] = []
        upper_points: list[MetricPoint] = []
        for i in range(1, horizon + 1):
            ts = base_timestamp + timedelta(hours=i)
            forecast_points.append(MetricPoint(timestamp=ts, value=avg))
            ci_width = 1.96 * std_val * math.sqrt(i / effective_window)
            lower_points.append(MetricPoint(timestamp=ts, value=avg - ci_width))
            upper_points.append(MetricPoint(timestamp=ts, value=avg + ci_width))
        result = ForecastResult(
            metric_name="",
            method="moving_average",
            forecast_values=forecast_points,
            confidence_interval_lower=lower_points,
            confidence_interval_upper=upper_points,
            confidence_level=0.95,
        )
        logger.debug(
            "moving_average_forecast_generated",
            horizon=horizon,
            window=effective_window,
            average=avg,
        )
        return result

    def exponential_smoothing_forecast(
        self,
        values: list[float],
        horizon: int,
        alpha: float = 0.3,
    ) -> ForecastResult:
        if not values or horizon <= 0:
            return ForecastResult(
                metric_name="",
                method="exponential_smoothing",
                forecast_values=[],
                confidence_interval_lower=[],
                confidence_interval_upper=[],
            )
        ema_series = self._stats.exponential_moving_average(values, alpha)
        level = ema_series[-1]
        trend = ema_series[-1] - ema_series[-2] if len(ema_series) >= 2 else 0.0
        residuals = [values[i] - ema_series[i] for i in range(len(values))]
        residual_std = self._stats.std_dev(residuals) if len(residuals) > 1 else 0.0
        base_timestamp = datetime.now(UTC)
        forecast_points: list[MetricPoint] = []
        lower_points: list[MetricPoint] = []
        upper_points: list[MetricPoint] = []
        for i in range(1, horizon + 1):
            predicted = level + trend * i
            ts = base_timestamp + timedelta(hours=i)
            ci_width = 1.96 * residual_std * math.sqrt(i)
            forecast_points.append(MetricPoint(timestamp=ts, value=predicted))
            lower_points.append(MetricPoint(timestamp=ts, value=predicted - ci_width))
            upper_points.append(MetricPoint(timestamp=ts, value=predicted + ci_width))
        result = ForecastResult(
            metric_name="",
            method="exponential_smoothing",
            forecast_values=forecast_points,
            confidence_interval_lower=lower_points,
            confidence_interval_upper=upper_points,
            confidence_level=0.95,
        )
        logger.debug(
            "exponential_smoothing_forecast_generated",
            horizon=horizon,
            level=level,
            trend=trend,
        )
        return result

    def forecast(
        self,
        metric_name: str,
        values: list[float],
        horizon: int,
        method: str = "linear",
    ) -> ForecastResult:
        if method == "moving_average":
            result = self.moving_average_forecast(values, horizon)
        elif method == "exponential_smoothing":
            result = self.exponential_smoothing_forecast(values, horizon)
        else:
            result = self.linear_forecast(values, horizon)
        result.metric_name = metric_name
        return result

    @staticmethod
    def _resolve_base_timestamp(timestamps: list[datetime] | None, values: list[float]) -> datetime:
        if timestamps and len(timestamps) > 0:
            return timestamps[-1]
        return datetime.now(UTC)
