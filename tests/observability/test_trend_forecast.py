import pytest
from datetime import UTC, datetime

from q_guardian.observability.analytics.trend_analysis import TrendAnalyzer
from q_guardian.observability.analytics.forecasting import ForecastEngine
from q_guardian.observability.enums import TrendDirection


class TestTrendAnalyzerAnalyze:
    def test_analyze_increasing_values(self) -> None:
        analyzer = TrendAnalyzer()
        trend = analyzer.analyze("test", [10.0, 1.0, 11.0, 2.0, 12.0])
        assert trend.direction == TrendDirection.INCREASING
        assert trend.slope > 0

    def test_analyze_decreasing_values(self) -> None:
        analyzer = TrendAnalyzer()
        trend = analyzer.analyze("test", [12.0, 2.0, 11.0, 1.0, 10.0])
        assert trend.direction == TrendDirection.DECREASING
        assert trend.slope < 0

    def test_analyze_stable_values(self) -> None:
        analyzer = TrendAnalyzer()
        trend = analyzer.analyze("test", [5.0, 5.0, 5.0, 5.0, 5.0])
        assert trend.direction == TrendDirection.STABLE
        assert trend.slope == pytest.approx(0.0)

    def test_analyze_with_timestamps(self) -> None:
        analyzer = TrendAnalyzer()
        ts1 = datetime(2025, 1, 1, tzinfo=UTC)
        ts2 = datetime(2025, 1, 2, tzinfo=UTC)
        trend = analyzer.analyze("test", [1.0, 2.0], [ts1, ts2])
        assert trend.period is not None
        assert trend.sample_count == 2

    def test_analyze_empty(self) -> None:
        analyzer = TrendAnalyzer()
        trend = analyzer.analyze("test", [])
        assert trend.direction == TrendDirection.STABLE
        assert trend.sample_count == 0


class TestTrendAnalyzerClassifyDirection:
    def test_classify_direction_increasing(self) -> None:
        analyzer = TrendAnalyzer()
        result = analyzer.classify_direction(1.0, 2.0)
        assert result == TrendDirection.INCREASING

    def test_classify_direction_decreasing(self) -> None:
        analyzer = TrendAnalyzer()
        result = analyzer.classify_direction(-1.0, 2.0)
        assert result == TrendDirection.DECREASING

    def test_classify_direction_stable(self) -> None:
        analyzer = TrendAnalyzer()
        result = analyzer.classify_direction(0.0, 0.0)
        assert result == TrendDirection.STABLE


class TestTrendAnalyzerDetectAnomalies:
    def test_detect_anomalies_with_outlier(self) -> None:
        analyzer = TrendAnalyzer()
        values = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 100.0]
        anomalies = analyzer.detect_anomalies(values, threshold=2.0)
        assert len(anomalies) == 1
        assert anomalies[0] == 9

    def test_detect_anomalies_no_outliers(self) -> None:
        analyzer = TrendAnalyzer()
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        anomalies = analyzer.detect_anomalies(values, threshold=3.0)
        assert anomalies == []

    def test_detect_anomalies_insufficient_data(self) -> None:
        analyzer = TrendAnalyzer()
        assert analyzer.detect_anomalies([1.0, 2.0]) == []


class TestForecastEngine:
    def setup_method(self) -> None:
        self.engine = ForecastEngine()

    def test_linear_forecast(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = self.engine.linear_forecast(values, horizon=3)
        assert result.method == "linear"
        assert len(result.forecast_values) == 3
        assert len(result.confidence_interval_lower) == 3
        assert len(result.confidence_interval_upper) == 3

    def test_linear_forecast_empty(self) -> None:
        result = self.engine.linear_forecast([], horizon=3)
        assert result.method == "linear"
        assert len(result.forecast_values) == 0

    def test_moving_average_forecast(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = self.engine.moving_average_forecast(values, horizon=3)
        assert result.method == "moving_average"
        assert len(result.forecast_values) == 3

    def test_moving_average_forecast_empty(self) -> None:
        result = self.engine.moving_average_forecast([], horizon=3)
        assert len(result.forecast_values) == 0

    def test_exponential_smoothing_forecast(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = self.engine.exponential_smoothing_forecast(values, horizon=3)
        assert result.method == "exponential_smoothing"
        assert len(result.forecast_values) == 3

    def test_exponential_smoothing_forecast_empty(self) -> None:
        result = self.engine.exponential_smoothing_forecast([], horizon=3)
        assert len(result.forecast_values) == 0

    def test_forecast_dispatcher_linear(self) -> None:
        result = self.engine.forecast("cpu", [1.0, 2.0, 3.0], horizon=2, method="linear")
        assert result.metric_name == "cpu"
        assert result.method == "linear"

    def test_forecast_dispatcher_moving_average(self) -> None:
        result = self.engine.forecast("cpu", [1.0, 2.0, 3.0], horizon=2, method="moving_average")
        assert result.method == "moving_average"

    def test_forecast_dispatcher_exponential_smoothing(self) -> None:
        result = self.engine.forecast("cpu", [1.0, 2.0, 3.0], horizon=2, method="exponential_smoothing")
        assert result.method == "exponential_smoothing"
