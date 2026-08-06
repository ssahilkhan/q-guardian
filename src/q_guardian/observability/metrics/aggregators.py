"""MetricAggregator implementations for computing metric aggregations."""

from __future__ import annotations

import structlog

from q_guardian.observability.data import AggregatedMetric
from q_guardian.observability.enums import AggregationType

logger = structlog.get_logger("observability.metrics.aggregators")


class MetricAggregator:
    """Static utility class for computing metric aggregations."""

    @staticmethod
    def aggregate_sum(values: list[float]) -> float:
        return sum(values)

    @staticmethod
    def aggregate_average(values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def aggregate_min(values: list[float]) -> float:
        if not values:
            return 0.0
        return min(values)

    @staticmethod
    def aggregate_max(values: list[float]) -> float:
        if not values:
            return 0.0
        return max(values)

    @staticmethod
    def aggregate_count(values: list[float]) -> int:
        return len(values)

    @staticmethod
    def aggregate_rate(values: list[float], window_seconds: int) -> float:
        if not values or window_seconds <= 0:
            return 0.0
        total = sum(values)
        return total / window_seconds

    @staticmethod
    def aggregate_percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        index = (percentile / 100.0) * (len(sorted_vals) - 1)
        lower = int(index)
        upper = lower + 1
        if upper >= len(sorted_vals):
            return sorted_vals[-1]
        fraction = index - lower
        return sorted_vals[lower] + fraction * (sorted_vals[upper] - sorted_vals[lower])

    @staticmethod
    def aggregate_last(values: list[float]) -> float:
        if not values:
            return 0.0
        return values[-1]

    @staticmethod
    def compute(
        data: list[float],
        aggregation: AggregationType,
        percentile: float = 95.0,
    ) -> AggregatedMetric:
        if not data:
            return AggregatedMetric(
                name="",
                aggregation=aggregation.value,
                value=0.0,
                count=0,
            )

        dispatch = {
            AggregationType.SUM: lambda: MetricAggregator.aggregate_sum(data),
            AggregationType.AVERAGE: lambda: MetricAggregator.aggregate_average(data),
            AggregationType.MIN: lambda: MetricAggregator.aggregate_min(data),
            AggregationType.MAX: lambda: MetricAggregator.aggregate_max(data),
            AggregationType.COUNT: lambda: float(MetricAggregator.aggregate_count(data)),
            AggregationType.RATE: lambda: MetricAggregator.aggregate_rate(data, 60),
            AggregationType.LAST: lambda: MetricAggregator.aggregate_last(data),
            AggregationType.PERCENTILE: lambda: MetricAggregator.aggregate_percentile(
                data, percentile
            ),
        }

        compute_fn = dispatch.get(aggregation)
        if compute_fn is None:
            raise ValueError(f"Unsupported aggregation type: {aggregation}")

        value = compute_fn()
        count = MetricAggregator.aggregate_count(data)

        logger.debug(
            "aggregation_computed",
            aggregation=aggregation.value,
            value=value,
            count=count,
        )

        return AggregatedMetric(
            name="",
            aggregation=aggregation.value,
            value=value,
            count=count,
            min_value=MetricAggregator.aggregate_min(data) if data else None,
            max_value=MetricAggregator.aggregate_max(data) if data else None,
        )
