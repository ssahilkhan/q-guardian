import json
import tempfile
from pathlib import Path

import pytest

from q_guardian.observability.data import (
    Alert,
    AlertEvent,
    AlertSeverity,
    AlertState,
    AlertType,
    HealthReport,
    Metric,
    MetricType,
    Trace,
)
from q_guardian.observability.exceptions import StorageError
from q_guardian.observability.storage import ObservabilityStorage


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    return tmp_path / "obs_storage"


@pytest.fixture
def storage(storage_root: Path) -> ObservabilityStorage:
    return ObservabilityStorage(storage_root=storage_root)


@pytest.fixture
def sample_metric() -> Metric:
    return Metric(name="test_metric", metric_type=MetricType.COUNTER)


@pytest.fixture
def sample_trace() -> Trace:
    return Trace(correlation_id="corr-1")


@pytest.fixture
def sample_alert() -> Alert:
    return Alert(rule_id="rule-1", message="test alert")


@pytest.fixture
def sample_alert_event() -> AlertEvent:
    return AlertEvent(alert_id="alert-1", new_state=AlertState.FIRING)


class TestStorageDirectoryCreation:
    def test_creates_root_directory(self, storage_root: Path) -> None:
        ObservabilityStorage(storage_root=storage_root)
        assert storage_root.exists()

    def test_creates_subdirectories(self, storage_root: Path) -> None:
        ObservabilityStorage(storage_root=storage_root)
        for subdir in ("metrics", "traces", "alerts", "alert_events", "health", "analytics"):
            assert (storage_root / subdir).exists()

    def test_root_property(self, storage: ObservabilityStorage, storage_root: Path) -> None:
        assert storage.root == storage_root


class TestMetricStorage:
    def test_save_and_load_metric(
        self, storage: ObservabilityStorage, sample_metric: Metric
    ) -> None:
        path = storage.save_metric(sample_metric)
        assert path.exists()
        data = storage.load_metric(sample_metric.metric_id)
        assert data["name"] == "test_metric"
        assert data["metric_type"] == "counter"

    def test_load_missing_metric_raises(self, storage: ObservabilityStorage) -> None:
        with pytest.raises(StorageError):
            storage.load_metric("nonexistent")

    def test_list_metrics(self, storage: ObservabilityStorage, sample_metric: Metric) -> None:
        storage.save_metric(sample_metric)
        ids = storage.list_metrics()
        assert sample_metric.metric_id in ids

    def test_delete_metric(self, storage: ObservabilityStorage, sample_metric: Metric) -> None:
        storage.save_metric(sample_metric)
        result = storage.delete_metric(sample_metric.metric_id)
        assert result is True
        assert sample_metric.metric_id not in storage.list_metrics()

    def test_delete_nonexistent_metric(self, storage: ObservabilityStorage) -> None:
        result = storage.delete_metric("nonexistent")
        assert result is False


class TestTraceStorage:
    def test_save_and_load_trace(
        self, storage: ObservabilityStorage, sample_trace: Trace
    ) -> None:
        path = storage.save_trace(sample_trace)
        assert path.exists()
        data = storage.load_trace(sample_trace.trace_id)
        assert data["correlation_id"] == "corr-1"

    def test_load_missing_trace_raises(self, storage: ObservabilityStorage) -> None:
        with pytest.raises(StorageError):
            storage.load_trace("nonexistent")

    def test_list_traces(self, storage: ObservabilityStorage, sample_trace: Trace) -> None:
        storage.save_trace(sample_trace)
        ids = storage.list_traces()
        assert sample_trace.trace_id in ids

    def test_delete_trace(self, storage: ObservabilityStorage, sample_trace: Trace) -> None:
        storage.save_trace(sample_trace)
        result = storage.delete_trace(sample_trace.trace_id)
        assert result is True
        assert sample_trace.trace_id not in storage.list_traces()

    def test_delete_nonexistent_trace(self, storage: ObservabilityStorage) -> None:
        result = storage.delete_trace("nonexistent")
        assert result is False


class TestAlertStorage:
    def test_save_and_load_alert(
        self, storage: ObservabilityStorage, sample_alert: Alert
    ) -> None:
        path = storage.save_alert(sample_alert)
        assert path.exists()
        data = storage.load_alert(sample_alert.alert_id)
        assert data["rule_id"] == "rule-1"
        assert data["message"] == "test alert"

    def test_load_missing_alert_raises(self, storage: ObservabilityStorage) -> None:
        with pytest.raises(StorageError):
            storage.load_alert("nonexistent")

    def test_list_alerts(self, storage: ObservabilityStorage, sample_alert: Alert) -> None:
        storage.save_alert(sample_alert)
        ids = storage.list_alerts()
        assert sample_alert.alert_id in ids

    def test_delete_alert(self, storage: ObservabilityStorage, sample_alert: Alert) -> None:
        storage.save_alert(sample_alert)
        result = storage.delete_alert(sample_alert.alert_id)
        assert result is True
        assert sample_alert.alert_id not in storage.list_alerts()

    def test_delete_nonexistent_alert(self, storage: ObservabilityStorage) -> None:
        result = storage.delete_alert("nonexistent")
        assert result is False


class TestAlertEventStorage:
    def test_save_alert_event(
        self, storage: ObservabilityStorage, sample_alert_event: AlertEvent
    ) -> None:
        path = storage.save_alert_event(sample_alert_event)
        assert path.exists()

    def test_list_alert_events(
        self, storage: ObservabilityStorage, sample_alert_event: AlertEvent
    ) -> None:
        storage.save_alert_event(sample_alert_event)
        ids = storage.list_alert_events()
        assert sample_alert_event.event_id in ids


class TestHealthReportStorage:
    def test_save_health_report(self, storage: ObservabilityStorage) -> None:
        report = {"report_id": "hr-1", "status": "healthy"}
        path = storage.save_health_report(report)
        assert path.exists()
        assert path.name == "hr-1.json"

    def test_save_health_report_default_id(self, storage: ObservabilityStorage) -> None:
        report = {"status": "healthy"}
        path = storage.save_health_report(report)
        assert path.name == "latest.json"


class TestAnalyticsReportStorage:
    def test_save_analytics_report(self, storage: ObservabilityStorage) -> None:
        report = {"report_id": "ar-1", "title": "Test"}
        path = storage.save_analytics_report(report)
        assert path.exists()
        assert path.name == "ar-1.json"


class TestStorageStats:
    def test_get_storage_stats(
        self,
        storage: ObservabilityStorage,
        sample_metric: Metric,
        sample_trace: Trace,
        sample_alert: Alert,
    ) -> None:
        storage.save_metric(sample_metric)
        storage.save_trace(sample_trace)
        storage.save_alert(sample_alert)
        stats = storage.get_storage_stats()
        assert stats["counts"]["metrics"] == 1
        assert stats["counts"]["traces"] == 1
        assert stats["counts"]["alerts"] == 1
        assert stats["counts"]["alert_events"] == 0
        assert stats["total_size_bytes"] > 0
        assert stats["storage_root"] == str(storage.root)
