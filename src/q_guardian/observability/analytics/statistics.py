from __future__ import annotations

import math
from collections import Counter

import structlog

logger = structlog.get_logger("observability.analytics.statistics")


class StatisticsEngine:
    """Pure-function statistical computation utilities."""

    def __init__(self) -> None:
        logger.debug("statistics_engine_created")

    @staticmethod
    def mean(values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def median(values: list[float]) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        mid = n // 2
        if n % 2 == 0:
            return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
        return float(sorted_vals[mid])

    @staticmethod
    def mode(values: list[float]) -> float | None:
        if not values:
            return None
        counter = Counter(values)
        max_count = max(counter.values())
        modes = [v for v, c in counter.items() if c == max_count]
        if max_count == 1:
            return None
        return modes[0]

    @staticmethod
    def std_dev(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        variance = StatisticsEngine.variance(values)
        return math.sqrt(variance)

    @staticmethod
    def variance(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        avg = sum(values) / len(values)
        return sum((v - avg) ** 2 for v in values) / (len(values) - 1)

    @staticmethod
    def percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        if n == 1:
            return sorted_vals[0]
        rank = (p / 100.0) * (n - 1)
        lower_idx = int(math.floor(rank))
        upper_idx = int(math.ceil(rank))
        if lower_idx == upper_idx:
            return float(sorted_vals[lower_idx])
        fraction = rank - lower_idx
        return sorted_vals[lower_idx] + fraction * (sorted_vals[upper_idx] - sorted_vals[lower_idx])

    @staticmethod
    def min_val(values: list[float]) -> float | None:
        if not values:
            return None
        return min(values)

    @staticmethod
    def max_val(values: list[float]) -> float | None:
        if not values:
            return None
        return max(values)

    @staticmethod
    def count(values: list[float]) -> int:
        return len(values)

    @staticmethod
    def sum_val(values: list[float]) -> float:
        return sum(values)

    @staticmethod
    def linear_regression(
        x_values: list[float], y_values: list[float]
    ) -> tuple[float, float, float]:
        if len(x_values) != len(y_values) or len(x_values) < 2:
            return 0.0, 0.0, 0.0
        n = len(x_values)
        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values))
        sum_x_sq = sum(x * x for x in x_values)
        denominator = n * sum_x_sq - sum_x * sum_x
        if denominator == 0:
            return 0.0, float(sum_y / n), 0.0
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        mean_y = sum_y / n
        ss_tot = sum((y - mean_y) ** 2 for y in y_values)
        if ss_tot == 0:
            r_squared = 0.0
        else:
            ss_res = sum(
                (y - (slope * x + intercept)) ** 2
                for x, y in zip(x_values, y_values)
            )
            r_squared = 1.0 - (ss_res / ss_tot)
        return slope, intercept, r_squared

    @staticmethod
    def moving_average(values: list[float], window: int) -> list[float]:
        if not values or window <= 0:
            return []
        result: list[float] = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            subset = values[start : i + 1]
            result.append(sum(subset) / len(subset))
        return result

    @staticmethod
    def exponential_moving_average(
        values: list[float], alpha: float = 0.3
    ) -> list[float]:
        if not values:
            return []
        result: list[float] = [values[0]]
        for i in range(1, len(values)):
            ema = alpha * values[i] + (1.0 - alpha) * result[-1]
            result.append(ema)
        return result
