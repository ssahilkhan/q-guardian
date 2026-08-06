import pytest

from q_guardian.observability.analytics.statistics import StatisticsEngine


class TestMean:
    def test_mean_normal(self) -> None:
        assert StatisticsEngine.mean([1.0, 2.0, 3.0]) == pytest.approx(2.0)

    def test_mean_empty(self) -> None:
        assert StatisticsEngine.mean([]) == 0.0


class TestMedian:
    def test_median_odd_count(self) -> None:
        assert StatisticsEngine.median([1.0, 3.0, 5.0]) == pytest.approx(3.0)

    def test_median_even_count(self) -> None:
        assert StatisticsEngine.median([1.0, 2.0, 3.0, 4.0]) == pytest.approx(2.5)

    def test_median_empty(self) -> None:
        assert StatisticsEngine.median([]) == 0.0


class TestMode:
    def test_mode_normal(self) -> None:
        assert StatisticsEngine.mode([1.0, 2.0, 2.0, 3.0]) == pytest.approx(2.0)

    def test_mode_no_mode(self) -> None:
        assert StatisticsEngine.mode([1.0, 2.0, 3.0]) is None

    def test_mode_empty(self) -> None:
        assert StatisticsEngine.mode([]) is None


class TestStdDev:
    def test_std_dev_normal(self) -> None:
        sd = StatisticsEngine.std_dev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert sd == pytest.approx(2.138, abs=0.01)

    def test_std_dev_single_value(self) -> None:
        assert StatisticsEngine.std_dev([5.0]) == 0.0

    def test_std_dev_empty(self) -> None:
        assert StatisticsEngine.std_dev([]) == 0.0


class TestVariance:
    def test_variance_normal(self) -> None:
        var = StatisticsEngine.variance([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert var == pytest.approx(4.571, abs=0.01)

    def test_variance_single_value(self) -> None:
        assert StatisticsEngine.variance([5.0]) == 0.0

    def test_variance_empty(self) -> None:
        assert StatisticsEngine.variance([]) == 0.0


class TestPercentile:
    def test_percentile_p50(self) -> None:
        vals = list(range(1, 101))
        p50 = StatisticsEngine.percentile(vals, 50)
        assert p50 == pytest.approx(50.5, abs=1.0)

    def test_percentile_p95(self) -> None:
        vals = list(range(1, 101))
        p95 = StatisticsEngine.percentile(vals, 95)
        assert p95 >= 94.0

    def test_percentile_p99(self) -> None:
        vals = list(range(1, 101))
        p99 = StatisticsEngine.percentile(vals, 99)
        assert p99 >= 98.0

    def test_percentile_empty(self) -> None:
        assert StatisticsEngine.percentile([], 50) == 0.0

    def test_percentile_single_value(self) -> None:
        assert StatisticsEngine.percentile([42.0], 50) == pytest.approx(42.0)


class TestMinMax:
    def test_min_val_normal(self) -> None:
        assert StatisticsEngine.min_val([3.0, 1.0, 2.0]) == pytest.approx(1.0)

    def test_min_val_empty(self) -> None:
        assert StatisticsEngine.min_val([]) is None

    def test_max_val_normal(self) -> None:
        assert StatisticsEngine.max_val([3.0, 1.0, 2.0]) == pytest.approx(3.0)

    def test_max_val_empty(self) -> None:
        assert StatisticsEngine.max_val([]) is None


class TestCountAndSum:
    def test_count(self) -> None:
        assert StatisticsEngine.count([1.0, 2.0, 3.0]) == 3

    def test_sum_val(self) -> None:
        assert StatisticsEngine.sum_val([1.0, 2.0, 3.0]) == pytest.approx(6.0)


class TestLinearRegression:
    def test_perfect_fit(self) -> None:
        x = [0.0, 1.0, 2.0, 3.0, 4.0]
        y = [0.0, 2.0, 4.0, 6.0, 8.0]
        slope, intercept, r_squared = StatisticsEngine.linear_regression(x, y)
        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(0.0)
        assert r_squared == pytest.approx(1.0)

    def test_no_correlation(self) -> None:
        x = [1.0, 1.0, 1.0]
        y = [1.0, 2.0, 3.0]
        slope, _intercept, r_squared = StatisticsEngine.linear_regression(x, y)
        assert slope == pytest.approx(0.0)
        assert r_squared == pytest.approx(0.0)

    def test_single_point(self) -> None:
        slope, intercept, r_squared = StatisticsEngine.linear_regression([1.0], [2.0])
        assert slope == 0.0
        assert intercept == 0.0
        assert r_squared == 0.0

    def test_mismatched_lengths(self) -> None:
        slope, intercept, r_squared = StatisticsEngine.linear_regression([1.0, 2.0], [1.0])
        assert slope == 0.0
        assert intercept == 0.0
        assert r_squared == 0.0


class TestMovingAverage:
    def test_moving_average_normal(self) -> None:
        result = StatisticsEngine.moving_average([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert len(result) == 5
        assert result[0] == pytest.approx(1.0)
        assert result[2] == pytest.approx(2.0)

    def test_moving_average_window_larger_than_data(self) -> None:
        result = StatisticsEngine.moving_average([1.0, 2.0], 10)
        assert len(result) == 2
        assert result[0] == pytest.approx(1.0)
        assert result[1] == pytest.approx(1.5)

    def test_moving_average_empty(self) -> None:
        assert StatisticsEngine.moving_average([], 3) == []


class TestExponentialMovingAverage:
    def test_exponential_moving_average_normal(self) -> None:
        result = StatisticsEngine.exponential_moving_average([1.0, 2.0, 3.0], 0.5)
        assert len(result) == 3
        assert result[0] == pytest.approx(1.0)
        assert result[1] == pytest.approx(1.5)

    def test_exponential_moving_average_empty(self) -> None:
        assert StatisticsEngine.exponential_moving_average([]) == []
