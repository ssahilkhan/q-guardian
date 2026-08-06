from q_guardian.events.base import Event
from q_guardian.observability.events import (
    AlertRaised,
    AlertResolved,
    AnalyticsGenerated,
    DashboardUpdated,
    HealthChanged,
    MetricRecorded,
    TraceCompleted,
    TraceStarted,
)


class TestEventBase:
    def test_stop_propagation(self) -> None:
        event = MetricRecorded()
        assert event.propagation_stopped is False
        event.stop_propagation()
        assert event.propagation_stopped is True

    def test_default_id(self) -> None:
        event = MetricRecorded()
        assert event.id is not None
        assert len(event.id) > 0

    def test_default_timestamp(self) -> None:
        event = MetricRecorded()
        assert event.timestamp is not None

    def test_default_source(self) -> None:
        event = MetricRecorded()
        assert event.source == "system"

    def test_inherits_from_event(self) -> None:
        assert issubclass(MetricRecorded, Event)
        assert issubclass(HealthChanged, Event)
        assert issubclass(TraceStarted, Event)
        assert issubclass(TraceCompleted, Event)
        assert issubclass(AlertRaised, Event)
        assert issubclass(AlertResolved, Event)
        assert issubclass(DashboardUpdated, Event)
        assert issubclass(AnalyticsGenerated, Event)


class TestMetricRecorded:
    def test_event_type(self) -> None:
        e = MetricRecorded()
        assert e.event_type == "observability.metric.recorded"


class TestHealthChanged:
    def test_event_type(self) -> None:
        e = HealthChanged()
        assert e.event_type == "observability.health.changed"


class TestTraceStarted:
    def test_event_type(self) -> None:
        e = TraceStarted()
        assert e.event_type == "observability.trace.started"


class TestTraceCompleted:
    def test_event_type(self) -> None:
        e = TraceCompleted()
        assert e.event_type == "observability.trace.completed"


class TestAlertRaised:
    def test_event_type(self) -> None:
        e = AlertRaised()
        assert e.event_type == "observability.alert.raised"


class TestAlertResolved:
    def test_event_type(self) -> None:
        e = AlertResolved()
        assert e.event_type == "observability.alert.resolved"


class TestDashboardUpdated:
    def test_event_type(self) -> None:
        e = DashboardUpdated()
        assert e.event_type == "observability.dashboard.updated"


class TestAnalyticsGenerated:
    def test_event_type(self) -> None:
        e = AnalyticsGenerated()
        assert e.event_type == "observability.analytics.generated"


class TestEventsWithPayload:
    def test_event_with_data(self) -> None:
        e = MetricRecorded(data={"metric_name": "cpu", "value": 75.0})
        assert e.data["metric_name"] == "cpu"
        assert e.data["value"] == 75.0

    def test_event_with_custom_source(self) -> None:
        e = HealthChanged(source="health_engine")
        assert e.source == "health_engine"
