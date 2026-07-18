import pytest
from datetime import UTC, datetime

from q_guardian.observability.integrations.grafana import GrafanaIntegration
from q_guardian.observability.integrations.datadog import DatadogIntegration
from q_guardian.observability.integrations.azure_monitor import AzureMonitorIntegration
from q_guardian.observability.integrations.cloudwatch import CloudWatchIntegration
from q_guardian.observability.integrations.prometheus import PrometheusIntegration
from q_guardian.observability.data import Alert, HealthReport, HealthStatusModel, Metric, MetricPoint
from q_guardian.observability.enums import (
    AlertSeverity,
    AlertState,
    AlertType,
    HealthStatus,
    MetricType,
    MetricUnit,
)
from q_guardian.observability.exceptions import ExporterError


def _make_metric(
    name: str = "cpu_usage",
    metric_type: MetricType = MetricType.GAUGE,
    values: list[float] | None = None,
    labels: dict[str, str] | None = None,
) -> Metric:
    m = Metric(
        name=name,
        metric_type=metric_type,
        unit=MetricUnit.PERCENTAGE,
        description=f"Test metric {name}",
        labels=labels or {},
    )
    for v in (values or [75.0]):
        m.add_point(v)
    return m


def _make_alert(
    rule_name: str = "high_cpu",
    severity: AlertSeverity = AlertSeverity.HIGH,
    state: AlertState = AlertState.FIRING,
) -> Alert:
    return Alert(
        alert_id="alert-test-001",
        rule_id="rule-001",
        rule_name=rule_name,
        state=state,
        severity=severity,
        alert_type=AlertType.THRESHOLD,
        message=f"Alert {rule_name} triggered",
        labels={"host": "web1"},
        annotations={"summary": "High CPU"},
        evaluation_value=95.0,
        escalation_level=0,
    )


def _make_health_report() -> HealthReport:
    components = [
        HealthStatusModel(
            component="metrics_engine",
            status=HealthStatus.HEALTHY,
            health_score=1.0,
            warnings=[],
            failures=[],
        ),
        HealthStatusModel(
            component="trace_engine",
            status=HealthStatus.DEGRADED,
            health_score=0.5,
            warnings=["slow traces"],
            failures=[],
        ),
    ]
    report = HealthReport(
        overall_status=HealthStatus.DEGRADED,
        overall_score=0.75,
        components=components,
        framework_uptime_seconds=3600.0,
        active_warnings=1,
        active_failures=0,
    )
    return report


class TestGrafanaIntegration:
    def test_format_metrics_for_dashboard(self):
        g = GrafanaIntegration(api_url="http://localhost:3000")
        metrics = [_make_metric("cpu"), _make_metric("mem")]
        result = g.format_metrics_for_dashboard(metrics)
        assert isinstance(result, dict)
        assert "targets" in result
        assert result["metric_count"] == 2
        assert len(result["metric_names"]) == 2

    def test_format_metrics_empty_raises(self):
        g = GrafanaIntegration()
        with pytest.raises(ExporterError):
            g.format_metrics_for_dashboard([])

    def test_format_alert_for_grafana(self):
        g = GrafanaIntegration(api_url="http://localhost:3000")
        alert = _make_alert()
        result = g.format_alert_for_grafana(alert)
        assert isinstance(result, dict)
        assert result["state"] == "alerting"
        assert result["severity"] == "critical"
        assert "qguardian_high_cpu" in result["alertName"]

    def test_create_dashboard_model(self):
        g = GrafanaIntegration()
        metrics = [_make_metric("cpu"), _make_metric("mem")]
        result = g.create_dashboard_model("My Dashboard", metrics)
        assert isinstance(result, dict)
        assert result["title"] == "My Dashboard"
        assert "panels" in result
        assert len(result["panels"]) > 0

    def test_create_dashboard_empty_raises(self):
        g = GrafanaIntegration()
        with pytest.raises(ExporterError):
            g.create_dashboard_model("Empty", [])

    def test_create_annotation(self):
        g = GrafanaIntegration()
        result = g.create_annotation("Test annotation", tags=["deploy"])
        assert isinstance(result, dict)
        assert result["text"] == "Test annotation"
        assert "q-guardian" in result["tags"]
        assert "deploy" in result["tags"]

    def test_get_datasource_config(self):
        g = GrafanaIntegration(api_url="http://prom:9090")
        result = g.get_datasource_config()
        assert isinstance(result, dict)
        assert result["type"] == "prometheus"
        assert result["url"] == "http://prom:9090"


class TestDatadogIntegration:
    def test_format_metrics_for_datadog(self):
        d = DatadogIntegration(api_key="test", app_key="test")
        metrics = [_make_metric("requests", MetricType.COUNTER, [100.0, 200.0])]
        result = d.format_metrics_for_datadog(metrics)
        assert isinstance(result, list)
        assert len(result) == 1
        assert "qguardian.requests" in result[0]["metric"]
        assert result[0]["type"] == "count"

    def test_format_metrics_empty_raises(self):
        d = DatadogIntegration()
        with pytest.raises(ExporterError):
            d.format_metrics_for_datadog([])

    def test_format_alert_for_datadog(self):
        d = DatadogIntegration()
        alert = _make_alert()
        result = d.format_alert_for_datadog(alert)
        assert isinstance(result, dict)
        assert result["alert_type"] == "error"
        assert "[Q-Guardian]" in result["title"]

    def test_create_metric_payload(self):
        d = DatadogIntegration()
        result = d.create_metric_payload("my.metric", [(1000, 42.0)], tags=["env:prod"])
        assert isinstance(result, dict)
        assert "series" in result
        assert len(result["series"]) == 1
        assert result["series"][0]["metric"] == "qguardian.my.metric"

    def test_create_event_payload(self):
        d = DatadogIntegration()
        result = d.create_event_payload("Test Event", "Something happened", alert_type="warning", tags=["env:test"])
        assert isinstance(result, dict)
        assert result["title"] == "Test Event"
        assert result["alert_type"] == "warning"

    def test_create_event_payload_invalid_type(self):
        d = DatadogIntegration()
        result = d.create_event_payload("Title", "Text", alert_type="invalid_type")
        assert result["alert_type"] == "info"

    def test_create_service_check(self):
        d = DatadogIntegration()
        result = d.create_service_check("health", "ok", message="All good", tags=["env:prod"])
        assert isinstance(result, dict)
        assert result["check"] == "q_guardian.health"
        assert result["status"] == "ok"


class TestAzureMonitorIntegration:
    def test_format_metrics_for_azure(self):
        a = AzureMonitorIntegration(workspace_id="ws1", instrumentation_key="ik1")
        metrics = [_make_metric("cpu", MetricType.GAUGE, [80.0])]
        result = a.format_metrics_for_azure(metrics)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["metric"] == "cpu"
        assert result[0]["namespace"] == "QGuardian"

    def test_format_metrics_empty_raises(self):
        a = AzureMonitorIntegration()
        with pytest.raises(ExporterError):
            a.format_metrics_for_azure([])

    def test_format_alert_for_azure(self):
        a = AzureMonitorIntegration()
        alert = _make_alert(severity=AlertSeverity.CRITICAL)
        result = a.format_alert_for_azure(alert)
        assert isinstance(result, dict)
        assert result["severity"] == "Critical"
        assert result["severityNumber"] == 0
        assert "QGuardian/high_cpu" in result["ruleName"]

    def test_create_metric_entry(self):
        a = AzureMonitorIntegration()
        result = a.create_metric_entry("test.metric", 42.0, dimensions={"host": "web1"})
        assert isinstance(result, dict)
        assert result["metric"]["name"] == "test.metric"
        assert result["metric"]["namespace"] == "QGuardian"

    def test_create_log_entry(self):
        a = AzureMonitorIntegration(workspace_id="ws1", instrumentation_key="ik1")
        result = a.create_log_entry("Warning", "Something happened", properties={"Key": "Value"})
        assert isinstance(result, dict)
        assert result["severity"] == "Warning"
        assert result["message"] == "Something happened"
        assert result["properties"]["Key"] == "Value"

    def test_create_log_entry_invalid_severity(self):
        a = AzureMonitorIntegration()
        result = a.create_log_entry("Invalid", "msg")
        assert result["severity"] == "Information"

    def test_create_trace_entry(self):
        a = AzureMonitorIntegration(instrumentation_key="ik1")
        result = a.create_trace_entry("test_op", 150.5, success=True)
        assert isinstance(result, dict)
        assert result["operationName"] == "test_op"
        assert result["success"] is True
        assert result["duration"] == int(150.5 * 1000)
        assert result["resultType"] == 0


class TestCloudWatchIntegration:
    def test_format_metrics_for_cloudwatch(self):
        c = CloudWatchIntegration(region="us-east-1", namespace="QGuardian")
        metrics = [_make_metric("cpu", MetricType.GAUGE, [75.0])]
        result = c.format_metrics_for_cloudwatch(metrics)
        assert isinstance(result, dict)
        assert result["Namespace"] == "QGuardian"
        assert len(result["MetricData"]) == 1
        assert result["MetricData"][0]["MetricName"] == "cpu"

    def test_format_metrics_empty_raises(self):
        c = CloudWatchIntegration()
        with pytest.raises(ExporterError):
            c.format_metrics_for_cloudwatch([])

    def test_format_alert_for_cloudwatch(self):
        c = CloudWatchIntegration(region="eu-west-1")
        alert = _make_alert(severity=AlertSeverity.HIGH)
        result = c.format_alert_for_cloudwatch(alert)
        assert isinstance(result, dict)
        assert result["source"] == "q-guardian"
        assert result["region"] == "eu-west-1"
        assert result["detail"]["severity"] == "high"
        assert result["detail"]["awsSeverity"] == "ERROR"

    def test_create_metric_data(self):
        c = CloudWatchIntegration()
        result = c.create_metric_data("TestMetric", 42.0, unit="Count", dimensions={"Env": "Prod"})
        assert isinstance(result, dict)
        assert result["MetricName"] == "TestMetric"
        assert result["Value"] == 42.0
        assert result["Unit"] == "Count"

    def test_create_event_pattern(self):
        c = CloudWatchIntegration(region="ap-southeast-1")
        result = c.create_event_pattern("Q-Guardian Alert", source="q-guardian")
        assert isinstance(result, dict)
        assert "q-guardian" in result["source"]
        assert "ap-southeast-1" in result["region"]

    def test_create_log_event(self):
        c = CloudWatchIntegration()
        result = c.create_log_event("Test log message")
        assert isinstance(result, dict)
        assert result["logGroupName"] == "/aws/q-guardian/observability"
        assert len(result["logEvents"]) == 1
        assert result["logEvents"][0]["message"] == "Test log message"


class TestPrometheusIntegration:
    def test_format_metrics_for_remote_write(self):
        p = PrometheusIntegration(remote_write_url="http://prom:9090/api/v1/write")
        metrics = [_make_metric("req_count", MetricType.COUNTER, [500.0])]
        result = p.format_metrics_for_remote_write(metrics)
        assert isinstance(result, dict)
        assert "timeseries" in result
        assert result["metadata"]["metricCount"] == 1

    def test_format_metrics_empty_raises(self):
        p = PrometheusIntegration()
        with pytest.raises(ExporterError):
            p.format_metrics_for_remote_write([])

    def test_create_write_request(self):
        p = PrometheusIntegration(remote_write_url="http://prom:9090/api/v1/write")
        metrics = [_make_metric("test", MetricType.GAUGE, [10.0])]
        result = p.create_write_request(metrics)
        assert isinstance(result, dict)
        assert "request" in result
        assert "headers" in result
        assert result["endpoint"] == "http://prom:9090/api/v1/write"
        assert result["headers"]["Content-Type"] == "application/x-protobuf"

    def test_format_alertmanager_payload(self):
        p = PrometheusIntegration()
        alerts = [_make_alert(), _make_alert(rule_name="high_mem", severity=AlertSeverity.CRITICAL)]
        result = p.format_alertmanager_payload(alerts)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["labels"]["alertname"] == "qguardian_high_cpu"
        assert result[1]["labels"]["alertname"] == "qguardian_high_mem"

    def test_format_alertmanager_empty(self):
        p = PrometheusIntegration()
        result = p.format_alertmanager_payload([])
        assert result == []

    def test_create_prometheus_rule(self):
        p = PrometheusIntegration()
        result = p.create_prometheus_rule(
            "high_cpu",
            'qguardian_cpu_usage > 90',
            severity="critical",
            for_duration="5m",
        )
        assert isinstance(result, dict)
        assert result["kind"] == "PrometheusRule"
        assert result["metadata"]["labels"]["severity"] == "critical"
        rules = result["spec"]["groups"][0]["rules"]
        assert rules[0]["alert"] == "qguardian_high_cpu"
        assert rules[0]["for"] == "5m"

    def test_format_health_for_prometheus(self):
        p = PrometheusIntegration()
        report = _make_health_report()
        result = p.format_health_for_prometheus(report)
        assert isinstance(result, dict)
        assert "exposition" in result
        assert result["format"] == "prometheus"
        assert "qguardian_health_overall_score" in result["exposition"]
        assert "qguardian_health_component_score" in result["exposition"]
