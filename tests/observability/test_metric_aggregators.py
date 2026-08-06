import pytest

from q_guardian.observability.data import AggregatedMetric
from q_guardian.observability.enums import AggregationType
from q_guardian.observability.metrics.aggregators import MetricAggregator


class TestAggregateSum:
    def test_aggregate_sum_normal(self):
        result = MetricAggregator.aggregate_sum([1.0, 2.0, 3.0])
        assert result == 6.0

    def test_aggregate_sum_empty(self):
        result = MetricAggregator.aggregate_sum([])
        assert result == 0.0


class TestAggregateAverage:
    def test_aggregate_average_normal(self):
        result = MetricAggregator.aggregate_average([1.0, 2.0, 3.0])
        assert result == 2.0

    def test_aggregate_average_empty_list(self):
        result = MetricAggregator.aggregate_average([])
        assert result == 0.0


class TestAggregateMin:
    def test_aggregate_min_normal(self):
        result = MetricAggregator.aggregate_min([3.0, 1.0, 4.0, 1.0, 5.0])
        assert result == 1.0

    def test_aggregate_min_empty_list(self):
        result = MetricAggregator.aggregate_min([])
        assert result == 0.0


class TestAggregateMax:
    def test_aggregate_max_normal(self):
        result = MetricAggregator.aggregate_max([3.0, 1.0, 4.0, 1.0, 5.0])
        assert result == 5.0

    def test_aggregate_max_empty_list(self):
        result = MetricAggregator.aggregate_max([])
        assert result == 0.0


class TestAggregateCount:
    def test_aggregate_count_normal(self):
        result = MetricAggregator.aggregate_count([1.0, 2.0, 3.0])
        assert result == 3

    def test_aggregate_count_empty(self):
        result = MetricAggregator.aggregate_count([])
        assert result == 0


class TestAggregateRate:
    def test_aggregate_rate_normal(self):
        result = MetricAggregator.aggregate_rate([60.0, 60.0], 60)
        assert result == 2.0

    def test_aggregate_rate_empty_list(self):
        result = MetricAggregator.aggregate_rate([], 60)
        assert result == 0.0

    def test_aggregate_rate_zero_window(self):
        result = MetricAggregator.aggregate_rate([10.0, 20.0], 0)
        assert result == 0.0


class TestAggregatePercentile:
    def test_aggregate_percentile_p50(self):
        result = MetricAggregator.aggregate_percentile([1, 2, 3, 4, 5], 50.0)
        assert result == 3.0

    def test_aggregate_percentile_p95(self):
        values = list(range(1, 101))
        result = MetricAggregator.aggregate_percentile(values, 95.0)
        assert result == pytest.approx(95.0, abs=0.1)

    def test_aggregate_percentile_p99(self):
        values = list(range(1, 101))
        result = MetricAggregator.aggregate_percentile(values, 99.0)
        assert result == pytest.approx(99.0, abs=0.1)

    def test_aggregate_percentile_empty_list(self):
        result = MetricAggregator.aggregate_percentile([], 95.0)
        assert result == 0.0

    def test_aggregate_percentile_single_value(self):
        result = MetricAggregator.aggregate_percentile([42.0], 95.0)
        assert result == 42.0


class TestAggregateLast:
    def test_aggregate_last_normal(self):
        result = MetricAggregator.aggregate_last([1.0, 2.0, 3.0])
        assert result == 3.0

    def test_aggregate_last_empty_list(self):
        result = MetricAggregator.aggregate_last([])
        assert result == 0.0


class TestCompute:
    def test_compute_sum(self):
        result = MetricAggregator.compute([1.0, 2.0, 3.0], AggregationType.SUM)
        assert result.aggregation == "sum"
        assert result.value == 6.0

    def test_compute_average(self):
        result = MetricAggregator.compute([1.0, 2.0, 3.0], AggregationType.AVERAGE)
        assert result.value == 2.0

    def test_compute_min(self):
        result = MetricAggregator.compute([3.0, 1.0, 2.0], AggregationType.MIN)
        assert result.value == 1.0

    def test_compute_max(self):
        result = MetricAggregator.compute([3.0, 1.0, 2.0], AggregationType.MAX)
        assert result.value == 3.0

    def test_compute_count(self):
        result = MetricAggregator.compute([1.0, 2.0, 3.0], AggregationType.COUNT)
        assert result.count == 3

    def test_compute_rate(self):
        result = MetricAggregator.compute([60.0, 60.0], AggregationType.RATE)
        assert result.value == 2.0

    def test_compute_last(self):
        result = MetricAggregator.compute([1.0, 2.0, 3.0], AggregationType.LAST)
        assert result.value == 3.0

    def test_compute_percentile(self):
        result = MetricAggregator.compute(
            list(range(1, 101)), AggregationType.PERCENTILE, percentile=95.0
        )
        assert result.value == pytest.approx(95.0, abs=0.1)

    def test_compute_empty_data(self):
        result = MetricAggregator.compute([], AggregationType.SUM)
        assert result.value == 0.0
        assert result.count == 0

    def test_compute_returns_aggregated_metric_with_correct_fields(self):
        result = MetricAggregator.compute([1.0, 2.0, 3.0, 4.0, 5.0], AggregationType.AVERAGE)
        assert isinstance(result, AggregatedMetric)
        assert result.name == ""
        assert result.aggregation == "average"
        assert result.value == 3.0
        assert result.count == 5
        assert result.min_value == 1.0
        assert result.max_value == 5.0
