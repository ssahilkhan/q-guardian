import pytest
import json
import csv
import io
from datetime import UTC, datetime

from q_guardian.observability.exporters.prometheus import PrometheusExporter
from q_guardian.observability.exporters.opentelemetry import OpenTelemetryExporter
from q_guardian.observability.exporters.json import JsonExporter
from q_guardian.observability.exporters.csv import CsvExporter
from q_guardian.observability.data import Metric, MetricPoint
from q_guardian.observability.enums import MetricType, MetricUnit, ExporterType


def _make_metric(
    name: str = "test_metric",
    metric_type: MetricType = MetricType.COUNTER,
    values: list[float] | None = None,
    labels: dict[str, str] | None = None,
    description: str = "A test metric",
    unit: MetricUnit = MetricUnit.COUNT,
) -> Metric:
    m = Metric(
        name=name,
        metric_type=metric_type,
        unit=unit,
        description=description,
        labels=labels or {},
    )
    for v in (values or [42.0]):
        m.add_point(v)
    return m


class TestPrometheusExporter:
    def test_name(self):
        exp = PrometheusExporter()
        assert exp.name == "prometheus"

    def test_type(self):
        assert PrometheusExporter.exporter_type == ExporterType.PROMETHEUS

    def test_export_metrics(self):
        exp = PrometheusExporter()
        metric = _make_metric("cpu_usage", MetricType.GAUGE, [75.5], labels={"host": "web1"})
        result = exp.export_metrics([metric])
        assert isinstance(result, str)
        assert "cpu_usage" in result
        assert "75.5" in result

    def test_export_counter(self):
        exp = PrometheusExporter()
        result = exp.export_counter("requests_total", 100.0, labels={"method": "GET"})
        assert isinstance(result, str)
        assert "requests_total" in result
        assert "100.0" in result
        assert "method" in result

    def test_export_gauge(self):
        exp = PrometheusExporter()
        result = exp.export_gauge("temperature", 22.5)
        assert isinstance(result, str)
        assert "temperature" in result
        assert "22.5" in result

    def test_export_histogram(self):
        exp = PrometheusExporter()
        result = exp.export_histogram("latency", [0.1, 0.5, 1.0, 2.5], labels={"path": "/api"})
        assert isinstance(result, str)
        assert "_bucket" in result
        assert "_sum" in result
        assert "_count" in result

    def test_sanitize_name_dots(self):
        exp = PrometheusExporter()
        assert exp._sanitize_name("q_guardian.requests.total") == "q_guardian_requests_total"

    def test_sanitize_name_hyphens(self):
        exp = PrometheusExporter()
        assert exp._sanitize_name("my-metric-name") == "my_metric_name"

    def test_sanitize_name_special_chars(self):
        exp = PrometheusExporter()
        result = exp._sanitize_name("metric@#$%name")
        assert result.isalnum() or "_" in result

    def test_format_labels(self):
        exp = PrometheusExporter()
        result = exp._format_labels({"host": "web1", "env": "prod"})
        assert "host=\"web1\"" in result
        assert "env=\"prod\"" in result
        assert result.startswith("{")

    def test_format_labels_empty(self):
        exp = PrometheusExporter()
        assert exp._format_labels({}) == ""

    def test_parse_exposition(self):
        exp = PrometheusExporter()
        text = (
            '# HELP my_counter Total requests\n'
            '# TYPE my_counter counter\n'
            'my_counter{job="api"} 42.0\n'
        )
        result = exp.parse_exposition(text)
        assert "my_counter" in result
        assert result["my_counter"]["help"] == "Total requests"
        assert result["my_counter"]["type"] == "counter"
        assert len(result["my_counter"]["samples"]) == 1
        assert result["my_counter"]["samples"][0]["value"] == 42.0

    def test_parse_exposition_simple_metric(self):
        exp = PrometheusExporter()
        text = 'simple_metric 123.45\n'
        result = exp.parse_exposition(text)
        assert "simple_metric" in result
        assert result["simple_metric"]["samples"][0]["value"] == 123.45

    def test_parse_exposition_round_trip(self):
        exp = PrometheusExporter(prefix="test")
        metric = _make_metric("round_trip_test", MetricType.COUNTER, [10.0, 20.0])
        exported = exp.export_metrics([metric])
        parsed = exp.parse_exposition(exported)
        assert "test_round_trip_test" in parsed
        assert len(parsed["test_round_trip_test"]["samples"]) >= 1


class TestOpenTelemetryExporter:
    def test_name(self):
        exp = OpenTelemetryExporter()
        assert exp.name == "opentelemetry"

    def test_type(self):
        assert OpenTelemetryExporter.exporter_type == ExporterType.OPENTELEMETRY

    def test_export_metrics(self):
        exp = OpenTelemetryExporter()
        metric = _make_metric("otlp_test", MetricType.GAUGE, [99.0])
        result = exp.export_metrics([metric])
        assert isinstance(result, dict)
        assert "resourceMetrics" in result
        assert "schemaUrl" in result

    def test_export_trace(self):
        exp = OpenTelemetryExporter()
        trace_data = {
            "trace_id": "abc123",
            "spans": [
                {
                    "span_id": "span-1",
                    "name": "test_span",
                    "kind": "server",
                    "start_time": datetime.now(UTC).isoformat(),
                    "end_time": datetime.now(UTC).isoformat(),
                    "status": {"code": 0, "message": "OK"},
                    "attributes": {"key1": "val1"},
                    "events": [],
                }
            ],
        }
        result = exp.export_trace(trace_data)
        assert isinstance(result, dict)
        assert "resourceSpans" in result
        spans = result["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans) == 1
        assert spans[0]["name"] == "test_span"

    def test_export_alert(self):
        exp = OpenTelemetryExporter()
        alert_data = {
            "alert_id": "alert-1",
            "rule_id": "rule-1",
            "rule_name": "high_cpu",
            "state": "firing",
            "severity": "high",
            "message": "CPU too high",
            "alert_type": "threshold",
            "labels": {"host": "web1"},
            "annotations": {"summary": "High CPU"},
        }
        result = exp.export_alert(alert_data)
        assert isinstance(result, dict)
        assert "resourceLogs" in result

    def test_create_resource(self):
        exp = OpenTelemetryExporter(service_name="my-service")
        resource = exp._create_resource()
        assert isinstance(resource, dict)
        assert "attributes" in resource
        attrs = resource["attributes"]
        assert any(a["key"] == "service.name" for a in attrs)


class TestJsonExporter:
    def test_export_metrics_returns_valid_json(self):
        exp = JsonExporter()
        metric = _make_metric("json_test", MetricType.GAUGE, [50.0])
        result = exp.export_metrics([metric])
        data = json.loads(result)
        assert "metrics" in data
        assert len(data["metrics"]) == 1
        assert data["metrics"][0]["name"] == "json_test"

    def test_export_trace_returns_valid_json(self):
        exp = JsonExporter()
        trace = {"trace_id": "t1", "spans": []}
        result = exp.export_trace(trace)
        data = json.loads(result)
        assert "trace" in data
        assert data["trace"]["trace_id"] == "t1"

    def test_export_alerts_returns_valid_json(self):
        exp = JsonExporter()
        alerts = [{"alert_id": "a1", "severity": "high"}]
        result = exp.export_alerts(alerts)
        data = json.loads(result)
        assert "alerts" in data
        assert len(data["alerts"]) == 1

    def test_export_health_returns_valid_json(self):
        exp = JsonExporter()
        health = {"status": "healthy", "score": 0.95}
        result = exp.export_health(health)
        data = json.loads(result)
        assert "health" in data
        assert data["health"]["status"] == "healthy"

    def test_export_all_returns_valid_json(self):
        exp = JsonExporter()
        payload = {"metrics": [], "health": {}, "alerts": []}
        result = exp.export_all(payload)
        data = json.loads(result)
        assert "metrics" in data
        assert "health" in data
        assert "_metadata" in data


class TestCsvExporter:
    def test_export_metrics_returns_csv_string(self):
        exp = CsvExporter()
        metric = _make_metric("csv_test", MetricType.COUNTER, [10.0])
        result = exp.export_metrics([metric])
        assert isinstance(result, str)
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) >= 2
        assert rows[0][1] == "name"

    def test_export_alerts_with_headers(self):
        exp = CsvExporter()
        alerts = [
            {"alert_id": "a1", "rule_id": "r1", "rule_name": "test", "state": "firing",
             "severity": "high", "alert_type": "threshold", "message": "msg",
             "created_at": "", "updated_at": "", "resolved_at": None,
             "evaluation_value": None, "escalation_level": 0, "labels": {}, "annotations": {}}
        ]
        result = exp.export_alerts(alerts)
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0][0] == "alert_id"

    def test_export_traces(self):
        exp = CsvExporter()
        traces = [
            {"trace_id": "t1", "correlation_id": "c1", "status": "completed",
             "start_time": "", "end_time": "", "duration_ms": 100.0, "span_count": 3,
             "labels": {"env": "test"}}
        ]
        result = exp.export_traces(traces)
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0][0] == "trace_id"

    def test_handles_empty_data(self):
        exp = CsvExporter()
        result = exp.export_metrics([])
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 1
