from q_guardian.exceptions.base import ApplicationError
from q_guardian.observability.exceptions import (
    AlertError,
    AnalyticsError,
    ConfigurationError,
    DashboardError,
    ExporterError,
    HealthError,
    MetricError,
    ObservabilityError,
    StorageError,
    TraceError,
)


class TestObservabilityError:
    def test_default_message(self) -> None:
        e = ObservabilityError()
        assert e.message == "Observability error"
        assert e.code == "OBSERVABILITY_ERROR"
        assert e.status_code == 500

    def test_custom_message(self) -> None:
        e = ObservabilityError(message="custom msg", details={"key": "val"})
        assert e.message == "custom msg"
        assert e.details == {"key": "val"}

    def test_to_dict(self) -> None:
        e = ObservabilityError(message="err", details={"x": 1})
        d = e.to_dict()
        assert d["error"]["code"] == "OBSERVABILITY_ERROR"
        assert d["error"]["message"] == "err"
        assert d["error"]["details"] == {"x": 1}

    def test_is_application_exception(self) -> None:
        assert isinstance(ObservabilityError(), ApplicationError)

    def test_is_exception(self) -> None:
        assert isinstance(ObservabilityError(), Exception)


class TestMetricError:
    def test_default_message(self) -> None:
        e = MetricError()
        assert e.message == "Metric operation failed"
        assert e.code == "METRIC_ERROR"

    def test_is_observability_error(self) -> None:
        assert isinstance(MetricError(), ObservabilityError)

    def test_custom_message(self) -> None:
        e = MetricError(message="bad metric")
        assert e.message == "bad metric"


class TestTraceError:
    def test_default_message(self) -> None:
        e = TraceError()
        assert e.message == "Trace operation failed"
        assert e.code == "TRACE_ERROR"

    def test_is_observability_error(self) -> None:
        assert isinstance(TraceError(), ObservabilityError)


class TestHealthError:
    def test_default_message(self) -> None:
        e = HealthError()
        assert e.message == "Health check failed"
        assert e.code == "HEALTH_ERROR"

    def test_is_observability_error(self) -> None:
        assert isinstance(HealthError(), ObservabilityError)


class TestAnalyticsError:
    def test_default_message(self) -> None:
        e = AnalyticsError()
        assert e.message == "Analytics operation failed"
        assert e.code == "ANALYTICS_ERROR"

    def test_is_observability_error(self) -> None:
        assert isinstance(AnalyticsError(), ObservabilityError)


class TestAlertError:
    def test_default_message(self) -> None:
        e = AlertError()
        assert e.message == "Alert operation failed"
        assert e.code == "ALERT_ERROR"

    def test_is_observability_error(self) -> None:
        assert isinstance(AlertError(), ObservabilityError)


class TestExporterError:
    def test_default_message(self) -> None:
        e = ExporterError()
        assert e.message == "Exporter operation failed"
        assert e.code == "EXPORTER_ERROR"

    def test_is_observability_error(self) -> None:
        assert isinstance(ExporterError(), ObservabilityError)


class TestDashboardError:
    def test_default_message(self) -> None:
        e = DashboardError()
        assert e.message == "Dashboard operation failed"
        assert e.code == "DASHBOARD_ERROR"

    def test_is_observability_error(self) -> None:
        assert isinstance(DashboardError(), ObservabilityError)


class TestStorageError:
    def test_default_message(self) -> None:
        e = StorageError()
        assert e.message == "Storage operation failed"
        assert e.code == "OBSERVABILITY_STORAGE_ERROR"

    def test_is_observability_error(self) -> None:
        assert isinstance(StorageError(), ObservabilityError)

    def test_custom_details(self) -> None:
        e = StorageError(details={"path": "/tmp"})
        assert e.details == {"path": "/tmp"}


class TestConfigurationError:
    def test_default_message(self) -> None:
        e = ConfigurationError()
        assert e.message == "Configuration error"
        assert e.code == "CONFIGURATION_ERROR"

    def test_is_observability_error(self) -> None:
        assert isinstance(ConfigurationError(), ObservabilityError)
