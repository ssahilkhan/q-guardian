from datetime import UTC, datetime, timedelta

import pytest

from q_guardian.observability.data import (
    AggregatedMetric,
    Alert,
    AlertEvent,
    AlertRule,
    AnalyticsReport,
    DashboardSnapshot,
    ForecastResult,
    HealthReport,
    HealthStatusModel,
    Metric,
    MetricPoint,
    MetricSeries,
    PerformanceMetrics,
    ResourceMetrics,
    RuntimeStatistics,
    Span,
    SpanStatus,
    TimeWindow,
    Trace,
    TrendData,
)
from q_guardian.observability.enums import (
    AlertSeverity,
    AlertState,
    AlertType,
    HealthLevel,
    HealthStatus,
    MetricType,
    MetricUnit,
    SpanKind,
    TraceStatus,
    TrendDirection,
)


class TestTimeWindow:
    def test_creation(self) -> None:
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 2, tzinfo=UTC)
        tw = TimeWindow(start=start, end=end)
        assert tw.start == start
        assert tw.end == end

    def test_duration_seconds(self) -> None:
        start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = start + timedelta(seconds=60)
        tw = TimeWindow(start=start, end=end)
        assert tw.duration_seconds == 60.0

    def test_contains_inside(self) -> None:
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 2, tzinfo=UTC)
        tw = TimeWindow(start=start, end=end)
        inside = datetime(2025, 1, 1, 12, tzinfo=UTC)
        assert tw.contains(inside) is True

    def test_contains_outside(self) -> None:
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 2, tzinfo=UTC)
        tw = TimeWindow(start=start, end=end)
        outside = datetime(2025, 1, 3, tzinfo=UTC)
        assert tw.contains(outside) is False

    def test_contains_boundary(self) -> None:
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 2, tzinfo=UTC)
        tw = TimeWindow(start=start, end=end)
        assert tw.contains(start) is True
        assert tw.contains(end) is True


class TestMetricPoint:
    def test_creation(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        mp = MetricPoint(timestamp=ts, value=42.0, labels={"env": "prod"})
        assert mp.value == 42.0
        assert mp.labels == {"env": "prod"}
        assert mp.timestamp == ts

    def test_defaults(self) -> None:
        mp = MetricPoint(value=1.0)
        assert mp.labels == {}
        assert mp.timestamp is not None


class TestMetric:
    def test_creation(self) -> None:
        m = Metric(name="requests", metric_type=MetricType.COUNTER)
        assert m.name == "requests"
        assert m.metric_type == MetricType.COUNTER
        assert m.unit == MetricUnit.NONE
        assert m.points == []
        assert m.metric_id is not None

    def test_add_point(self) -> None:
        m = Metric(name="cpu", metric_type=MetricType.GAUGE)
        point = m.add_point(0.75, labels={"host": "a"})
        assert point.value == 0.75
        assert point.labels == {"host": "a"}
        assert len(m.points) == 1

    def test_add_point_merges_labels(self) -> None:
        m = Metric(name="cpu", metric_type=MetricType.GAUGE, labels={"env": "prod"})
        point = m.add_point(0.5, labels={"host": "a"})
        assert point.labels == {"env": "prod", "host": "a"}

    def test_latest_value(self) -> None:
        m = Metric(name="req", metric_type=MetricType.COUNTER)
        assert m.latest_value() is None
        m.add_point(10.0)
        m.add_point(20.0)
        assert m.latest_value() == 20.0

    def test_values_in_window(self) -> None:
        m = Metric(name="req", metric_type=MetricType.COUNTER)
        m.add_point(1.0)
        m.add_point(2.0)
        m.add_point(3.0)
        start = datetime.now(UTC) - timedelta(seconds=5)
        end = datetime.now(UTC) + timedelta(seconds=5)
        tw = TimeWindow(start=start, end=end)
        vals = m.values_in_window(tw)
        assert len(vals) == 3


class TestMetricSeries:
    def test_creation(self) -> None:
        ms = MetricSeries(metric_name="latency", aggregation="average")
        assert ms.metric_name == "latency"
        assert ms.aggregation == "average"
        assert ms.interval_seconds == 60
        assert ms.points == []


class TestAggregatedMetric:
    def test_creation(self) -> None:
        am = AggregatedMetric(name="cpu", aggregation="max", value=95.0)
        assert am.name == "cpu"
        assert am.value == 95.0
        assert am.min_value is None
        assert am.max_value is None

    def test_with_window(self) -> None:
        tw = TimeWindow(
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 2, tzinfo=UTC),
        )
        am = AggregatedMetric(name="x", aggregation="sum", value=100, window=tw)
        assert am.window is not None
        assert am.window.duration_seconds == 86400.0


class TestHealthStatusModel:
    def test_creation(self) -> None:
        hsm = HealthStatusModel(component="api")
        assert hsm.component == "api"
        assert hsm.status == HealthStatus.UNKNOWN
        assert hsm.health_score == 1.0

    def test_update_level_excellent(self) -> None:
        hsm = HealthStatusModel(component="x", health_score=0.95)
        hsm.update_level()
        assert hsm.level == HealthLevel.EXCELLENT

    def test_update_level_good(self) -> None:
        hsm = HealthStatusModel(component="x", health_score=0.8)
        hsm.update_level()
        assert hsm.level == HealthLevel.GOOD

    def test_update_level_fair(self) -> None:
        hsm = HealthStatusModel(component="x", health_score=0.6)
        hsm.update_level()
        assert hsm.level == HealthLevel.FAIR

    def test_update_level_poor(self) -> None:
        hsm = HealthStatusModel(component="x", health_score=0.35)
        hsm.update_level()
        assert hsm.level == HealthLevel.POOR

    def test_update_level_critical(self) -> None:
        hsm = HealthStatusModel(component="x", health_score=0.1)
        hsm.update_level()
        assert hsm.level == HealthLevel.CRITICAL


class TestHealthReport:
    def test_calculate_overall_no_components(self) -> None:
        hr = HealthReport()
        hr.calculate_overall()
        assert hr.overall_status == HealthStatus.UNKNOWN
        assert hr.overall_score == 0.0

    def test_calculate_overall_all_healthy(self) -> None:
        hr = HealthReport(
            components=[
                HealthStatusModel(component="a", health_score=1.0, status=HealthStatus.HEALTHY),
                HealthStatusModel(component="b", health_score=0.9, status=HealthStatus.HEALTHY),
            ]
        )
        hr.calculate_overall()
        assert hr.overall_status == HealthStatus.HEALTHY
        assert hr.overall_score == pytest.approx(0.95)

    def test_calculate_overall_with_unhealthy(self) -> None:
        hr = HealthReport(
            components=[
                HealthStatusModel(component="a", health_score=0.5, status=HealthStatus.HEALTHY),
                HealthStatusModel(component="b", health_score=0.1, status=HealthStatus.UNHEALTHY),
            ]
        )
        hr.calculate_overall()
        assert hr.overall_status == HealthStatus.UNHEALTHY

    def test_calculate_overall_with_degraded(self) -> None:
        hr = HealthReport(
            components=[
                HealthStatusModel(component="a", health_score=0.8, status=HealthStatus.HEALTHY),
                HealthStatusModel(component="b", health_score=0.6, status=HealthStatus.DEGRADED),
            ]
        )
        hr.calculate_overall()
        assert hr.overall_status == HealthStatus.DEGRADED

    def test_calculate_overall_counts_warnings_and_failures(self) -> None:
        hr = HealthReport(
            components=[
                HealthStatusModel(
                    component="a",
                    health_score=1.0,
                    status=HealthStatus.HEALTHY,
                    warnings=["warn1"],
                    failures=["fail1", "fail2"],
                ),
            ]
        )
        hr.calculate_overall()
        assert hr.active_warnings == 1
        assert hr.active_failures == 2


class TestSpanStatus:
    def test_ok(self) -> None:
        s = SpanStatus.ok()
        assert s.code == 0
        assert s.message == "OK"

    def test_error(self) -> None:
        s = SpanStatus.error("something broke")
        assert s.code == 1
        assert s.message == "something broke"

    def test_error_default_message(self) -> None:
        s = SpanStatus.error()
        assert s.code == 1
        assert s.message == "error"

    def test_timeout(self) -> None:
        s = SpanStatus.timeout()
        assert s.code == 2
        assert s.message == "timeout"


class TestSpan:
    def test_creation(self) -> None:
        sp = Span(trace_id="t1", name="op1")
        assert sp.trace_id == "t1"
        assert sp.name == "op1"
        assert sp.kind == SpanKind.INTERNAL
        assert sp.end_time is None

    def test_duration_ms_none_when_not_finished(self) -> None:
        sp = Span(trace_id="t1", name="op1")
        assert sp.duration_ms is None

    def test_duration_ms_after_finish(self) -> None:
        sp = Span(trace_id="t1", name="op1")
        sp.finish()
        assert sp.duration_ms is not None
        assert sp.duration_ms >= 0

    def test_finish_with_status(self) -> None:
        sp = Span(trace_id="t1", name="op1")
        sp.finish(SpanStatus.error("oops"))
        assert sp.status.code == 1

    def test_add_event(self) -> None:
        sp = Span(trace_id="t1", name="op1")
        sp.add_event("event1", {"key": "val"})
        assert len(sp.events) == 1
        assert sp.events[0]["name"] == "event1"
        assert sp.events[0]["attributes"] == {"key": "val"}

    def test_set_attribute(self) -> None:
        sp = Span(trace_id="t1", name="op1")
        sp.set_attribute("http.method", "GET")
        assert sp.attributes["http.method"] == "GET"

    def test_is_complete(self) -> None:
        sp = Span(trace_id="t1", name="op1")
        assert sp.is_complete is False
        sp.finish()
        assert sp.is_complete is True


class TestTrace:
    def test_creation(self) -> None:
        t = Trace()
        assert t.status == TraceStatus.ACTIVE
        assert t.spans == []
        assert t.trace_id is not None

    def test_add_span(self) -> None:
        t = Trace()
        sp = Span(trace_id="wrong", name="op1")
        t.add_span(sp)
        assert sp.trace_id == t.trace_id
        assert len(t.spans) == 1

    def test_get_span(self) -> None:
        t = Trace()
        sp = Span(trace_id="", name="op1")
        t.add_span(sp)
        found = t.get_span(sp.span_id)
        assert found is not None
        assert found.name == "op1"

    def test_get_span_not_found(self) -> None:
        t = Trace()
        assert t.get_span("nonexistent") is None

    def test_get_root_spans(self) -> None:
        t = Trace()
        root = Span(trace_id="", name="root")
        child = Span(trace_id="", name="child", parent_span_id="x")
        t.add_span(root)
        t.add_span(child)
        roots = t.get_root_spans()
        assert len(roots) == 1
        assert roots[0].name == "root"

    def test_get_child_spans(self) -> None:
        t = Trace()
        parent = Span(trace_id="", name="parent")
        t.add_span(parent)
        child = Span(trace_id="", name="child", parent_span_id=parent.span_id)
        t.add_span(child)
        children = t.get_child_spans(parent.span_id)
        assert len(children) == 1

    def test_finish(self) -> None:
        t = Trace()
        t.finish()
        assert t.end_time is not None
        assert t.status == TraceStatus.COMPLETED

    def test_finish_with_status(self) -> None:
        t = Trace()
        t.finish(TraceStatus.ERROR)
        assert t.status == TraceStatus.ERROR

    def test_span_count(self) -> None:
        t = Trace()
        assert t.span_count == 0
        t.add_span(Span(trace_id="", name="s1"))
        assert t.span_count == 1

    def test_duration_ms_none(self) -> None:
        t = Trace()
        assert t.duration_ms is None


class TestAlert:
    def test_creation(self) -> None:
        a = Alert(rule_id="r1")
        assert a.rule_id == "r1"
        assert a.state == AlertState.PENDING
        assert a.severity == AlertSeverity.MEDIUM

    def test_acknowledge(self) -> None:
        a = Alert(rule_id="r1")
        a.acknowledge("admin")
        assert a.state == AlertState.ACKNOWLEDGED
        assert a.acknowledged_by == "admin"
        assert a.acknowledged_at is not None

    def test_resolve(self) -> None:
        a = Alert(rule_id="r1")
        a.resolve()
        assert a.state == AlertState.RESOLVED
        assert a.resolved_at is not None

    def test_escalate(self) -> None:
        a = Alert(rule_id="r1")
        a.escalate()
        assert a.state == AlertState.ESCALATED
        assert a.escalation_level == 1
        a.escalate()
        assert a.escalation_level == 2

    def test_suppress(self) -> None:
        a = Alert(rule_id="r1")
        a.suppress()
        assert a.state == AlertState.SUPPRESSED

    def test_duration_seconds(self) -> None:
        a = Alert(rule_id="r1")
        dur = a.duration_seconds
        assert dur >= 0


class TestAlertRule:
    def test_creation(self) -> None:
        r = AlertRule(name="r1", metric_name="cpu", condition="gt", threshold=90)
        assert r.name == "r1"
        assert r.enabled is True
        assert r.cooldown_seconds == 300

    def test_evaluate_gt(self) -> None:
        r = AlertRule(name="r", metric_name="m", condition="gt", threshold=10)
        assert r.evaluate(11) is True
        assert r.evaluate(10) is False
        assert r.evaluate(9) is False

    def test_evaluate_lt(self) -> None:
        r = AlertRule(name="r", metric_name="m", condition="lt", threshold=10)
        assert r.evaluate(9) is True
        assert r.evaluate(10) is False

    def test_evaluate_eq(self) -> None:
        r = AlertRule(name="r", metric_name="m", condition="eq", threshold=10)
        assert r.evaluate(10) is True
        assert r.evaluate(11) is False

    def test_evaluate_gte(self) -> None:
        r = AlertRule(name="r", metric_name="m", condition="gte", threshold=10)
        assert r.evaluate(10) is True
        assert r.evaluate(9) is False

    def test_evaluate_lte(self) -> None:
        r = AlertRule(name="r", metric_name="m", condition="lte", threshold=10)
        assert r.evaluate(10) is True
        assert r.evaluate(11) is False

    def test_evaluate_unknown_condition(self) -> None:
        r = AlertRule(name="r", metric_name="m", condition="unknown", threshold=10)
        assert r.evaluate(10) is False


class TestAlertEvent:
    def test_creation(self) -> None:
        ae = AlertEvent(alert_id="a1", new_state=AlertState.FIRING)
        assert ae.alert_id == "a1"
        assert ae.new_state == AlertState.FIRING
        assert ae.old_state is None
        assert ae.event_id is not None


class TestAnalyticsReport:
    def test_creation(self) -> None:
        ar = AnalyticsReport(title="Test Report")
        assert ar.title == "Test Report"
        assert ar.threat_trends == []
        assert ar.forecasts == []


class TestTrendData:
    def test_creation(self) -> None:
        td = TrendData(metric_name="cpu", direction=TrendDirection.INCREASING, slope=0.5)
        assert td.metric_name == "cpu"
        assert td.direction == TrendDirection.INCREASING
        assert td.slope == 0.5


class TestForecastResult:
    def test_creation(self) -> None:
        fr = ForecastResult(metric_name="latency", method="linear")
        assert fr.metric_name == "latency"
        assert fr.method == "linear"
        assert fr.confidence_level == 0.95
        assert fr.forecast_values == []


class TestRuntimeStatistics:
    def test_creation(self) -> None:
        rs = RuntimeStatistics()
        assert rs.total_requests == 0
        assert rs.success_rate == 0.0


class TestPerformanceMetrics:
    def test_creation(self) -> None:
        pm = PerformanceMetrics()
        assert pm.prompt_latency_ms == 0.0
        assert pm.p99_latency_ms == 0.0


class TestResourceMetrics:
    def test_creation(self) -> None:
        rm = ResourceMetrics()
        assert rm.queue_size == 0
        assert rm.cpu_usage_percent == 0.0


class TestDashboardSnapshot:
    def test_creation(self) -> None:
        ds = DashboardSnapshot()
        assert ds.snapshot_id is not None
        assert isinstance(ds.runtime_stats, RuntimeStatistics)
        assert isinstance(ds.performance, PerformanceMetrics)
        assert isinstance(ds.resources, ResourceMetrics)
        assert isinstance(ds.health, HealthReport)
        assert ds.recent_alerts == []
        assert ds.top_metrics == []
