# 17 - Observability & Operations Platform

> Module: `src\q_guardian\observability\` (Module 10). An enterprise observability and
> operations platform: metrics, distributed tracing, health, analytics, alerting,
> dashboards, exporters, and third-party integrations. 55 source files: 8 root files +
> 47 files across 8 subpackages (`alerts`, `analytics`, `dashboard`, `exporters`,
> `health`, `integrations`, `metrics`, `tracing`).

---

## 1. Platform Overview

```
 Q-Guardian plugins / event bus
        │
        ▼
 ObservabilityPlugin  (name="observability", interfaces=["observability","metrics",
                        "health","tracing","analytics","alerting"])
   │   subscribes to event bus "*" (priority 100)
   │   counts "observability.events.total" per event_type
   ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │ MetricsEngine      │ TraceEngine        │ HealthEngine          │
 │  counters/gauges/  │  traces & spans    │  checks + registry +  │
 │  histograms/timers │  W3C propagation   │  heartbeat (stale)    │
 ├────────────────────┼────────────────────┼───────────────────────┤
 │ AnalyticsEngine    │ AlertEngine        │ DashboardAPI          │
 │  trends, usage,    │  rules, cooldowns, │  JSON facade over all │
 │  provider accuracy │  routing, escalate │  engines + DTOs       │
 │  forecasting       │  notifiers         │                       │
 ├────────────────────┴────────────────────┴───────────────────────┤
 │ Exporters: Json / Csv / Prometheus / OpenTelemetry               │
 │ Integrations: Azure Monitor / CloudWatch / Datadog / Grafana / Prometheus │
 └─────────────────────────────────────────────────────────────────┘
```

---

## 2. Configuration — `config.py`

All configs `extra="allow"`; `ObservabilityConfig` aggregates the rest.

| Config | Key defaults |
|---|---|
| `MetricsConfig` | `enabled=True`, `collection_interval_seconds=10`, `default_window_size=60`, `max_series_per_metric=10_000`, `histogram_bucket_count=20`, `enable_percentiles=True`, `percentiles=[50, 95, 99]` |
| `TracingConfig` | `enabled=True`, `max_spans_per_trace=500`, `max_trace_duration_seconds=3600`, `sample_rate=1.0`, `propagation_format="w3c"` (w3c/b3/jaeger) |
| `HealthConfig` | `enabled=True`, `heartbeat_interval_seconds=30`, `heartbeat_timeout_seconds=90`, `unhealthy_threshold=3`, `degraded_threshold=1` |
| `AnalyticsConfig` | `enabled=True`, `default_granularity="hour"`, `retention_days=90`, `enable_forecasting=True`, `forecast_horizon_hours=24`, `max_report_size=10_000` |
| `AlertConfig` | `enabled=True`, `evaluation_interval_seconds=30`, `suppression_window_seconds=300`, `max_active_alerts=1000`, `default_severity="medium"`, `enable_escalation=True`, `escalation_timeout_seconds=600` |
| `DashboardConfig` | `enabled=True`, `api_prefix="/api/v1/observability"`, `max_results=500`, `default_time_range_seconds=3600` |
| `ExporterConfig` | `enabled=True`, `active_exporters=["json"]`, `export_interval_seconds=60`, `batch_size=100` |

---

## 3. Metrics — `metrics\`

**`MetricsEngine`** — central registry (thread-safe, RLock):
- Metric mgmt: `create_metric(name, type, description, unit, labels)`,
  `register_metric`, `get_metric`, `remove_metric`, `list_metrics`,
  `get_all_metrics() -> list[dict]`.
- Recording: `record_value` / `record_point` (requires `initialize()`), `increment`,
  `decrement`, `set_gauge`, `observe` (histogram).
- Timers: `start_timer(name) -> timer_id`, `stop_timer`, `timer(name)` context manager.
- Aggregation/stats: `aggregate`, `get_average/sum/min/max`, `get_stats(name) ->
  MetricStats` (mean/std/p95/p99/min/max/sum/count), `export`, `check_alerts`.
- Events: subscribes to bus `"*"` (priority 100); `_on_any_event` records `MetricEvent`
  and calls `check_alerts`.

Supporting classes: `MetricRegistry` (name set), `MetricAggregator` (rolling window:
mean/min/max/sum/count/std_dev/p95/p99/latest), `MetricCollector` (callable/registry
source + daemon-thread interval collection), metric exporters (`InMemoryMetricExporter`,
`JsonMetricExporter`, `CsvMetricExporter`).

**Metric types** (`MetricType`): counter, gauge, histogram, timer.
**Units** (`MetricUnit`): none, count, percentage, seconds, milliseconds, microseconds,
bytes, kilobytes, megabytes, requests_per_second, per_second.

---

## 4. Tracing — `tracing\`

**`TraceEngine`** — trace lifecycle + TTL store:
- Constants: `DEFAULT_MAX_TRACES=10_000`, `DEFAULT_TRACE_TTL_SECONDS=3600`.
- `start_trace(name, correlation_id, execution_id, service, labels) -> TraceContext`
  (creates Trace + root span; evicts oldest beyond max via TTL).
- `finish_trace` / `fail_trace`, `start_span` / `finish_span`, `add_span_event`,
  `add_trace_event`.
- Queries: `get_trace`, `get_all_traces` (sorted desc), `get_traces_by_status`,
  `get_traces_by_correlation_id`, `search_traces(name/status/service)`.
- Export/stats: `export_traces`, `set_exporter`, `get_trace_stats` (total/by-status/avg
  duration/error rate), `clear_old_traces` (TTL), `get_traces_for_execution`.

Supporting: `TraceContext` (frozen dataclass, `with_span`/`from_dict`),
`SpanManager` (create/finish spans, `span_started`/`span_finished` events),
`CorrelationManager` (correlation ↔ execution ↔ trace maps), trace exporters
(`InMemory`, `Json`, `Console`).

Trace statuses: active, completed, error, timeout. Span kinds: internal, server,
client, producer, consumer. Propagation format: w3c / b3 / jaeger.

---

## 5. Health — `health\`

**`HealthEngine`** — `register_check` / `unregister_check` / `list_checks` /
`run_checks() -> HealthReport` / `get_health_report()` (cached, `cached=True` flag) /
`get_component_status` / `get_overall_health`.

- **`HealthReport.calculate_overall()`** — overall score = mean; status precedence
  UNHEALTHY > DEGRADED > HEALTHY (mixed → DEGRADED).
- **`HealthStatusModel.update_level()`** — score → level: `>=0.9` EXCELLENT,
  `>=0.7` GOOD, `>=0.5` FAIR, `>=0.3` POOR, else CRITICAL.
- **`HealthRegistry`** — thread-safe per-component status; `get_unhealthy_components`.
- **`HeartbeatManager`** — `record_heartbeat`, `is_heartbeat_stale`,
  `get_stale_components`.
- **`DiagnosticEngine`** — `diagnose_threads` (incl. deadlock count), `diagnose_memory`
  (RSS via resource/psutil best-effort), `diagnose_event_bus`, `run_diagnostics`.
- **Built-in checks**: `FrameworkHealthCheck`, `PluginManagerHealthCheck`,
  `StorageHealthCheck`, `MetricsHealthCheck`, `AIProviderHealthCheck`.
- **Status helpers**: `status_to_score` (HEALTHY=1, DEGRADED=0.5, UNKNOWN=0.5,
  UNHEALTHY=0), `is_healthy/is_degraded/is_unhealthy`.

Health statuses: healthy, degraded, unhealthy, unknown, maintenance.
Health levels: excellent, good, fair, poor, critical.

---

## 6. Alerts — `alerts\`

**`AlertEngine`** (thread-safe):
- Rules: `add_rule` (raises `AlertError` on duplicate id), `remove_rule`, `update_rule`,
  `get_rule`, `list_rules`.
- Evaluation: `evaluate_rules() -> list[Alert]`, `evaluate_rule(rule_id)`. Per-rule
  cooldown (`rule.cooldown_seconds`, default 300) suppresses re-firing.
- Alert ops: `get_active_alerts` (excludes RESOLVED/SUPPRESSED), `get_alert`,
  `acknowledge_alert`, `resolve_alert` (moves to history), `suppress_alert`,
  `get_alert_history`, `get_alert_events`, `to_dict`, `shutdown`.
- On fire: creates `Alert` (state FIRING, message `"Rule 'X' triggered: cond threshold
  (value=Y)"`), routes via `AlertRouter`, notifies all notifiers, escalates via
  `EscalationManager`, records `AlertEvent`.

**`AlertRuleManager`** — `create_rule`, `add_rule`, `remove_rule`, `update_rule`,
`validate_rule`. Valid conditions: `{"gt","lt","eq","gte","lte"}`. Rule fields:
`metric_name`, `condition`, `threshold`, `duration_seconds`, `cooldown_seconds`,
`labels`, `annotations`.

**Escalation** (`EscalationManager`): per-severity `EscalationPolicy` step chains.
Default chains: CRITICAL 3 steps (0s/60s/300s, log→webhook), HIGH 2 steps (0s/120s),
MEDIUM 2 steps (0s/300s log), LOW/INFO 1 step (0s log). `escalate(alert)` advances
step index and calls `alert.escalate()` (level+1, state ESCALATED).

**Notifiers**: `AlertNotifier` (ABC) → `LogNotifier` (name="log"),
`WebhookNotifier` (name="webhook", stores payloads), `CallbackNotifier`
(name="callback", invokes callable).

**`AlertRouter`** — maps severity → channels with `default_channels` fallback.

Alert severities: info, low, medium, high, critical. Alert states: pending, firing,
acknowledged, suppressed, resolved, escalated. Alert types: threshold, health, latency,
failure, security, custom.

---

## 7. Analytics — `analytics\`

**`AnalyticsEngine`** — `ingest_event(event)`, `record_metric_event`, `generate_report()`
-> `AnalyticsReport`, trend getters, usage counters, top-N, forecasting, `to_dict`.
- Event categorization (substring on lowercased type): "threat"→threat, "policy"→policy,
  "risk"→risk, "response"→response, "provider"/"accuracy"→provider, "plugin"→plugin,
  "quantum"→quantum, "fusion"/"strategy"→fusion, "session"→session, "agent"→agent.
- `get_provider_accuracy()` — mean accuracy per provider/source.
- `get_plugin_usage` / `get_quantum_usage` / `get_fusion_strategy_usage` — Counters.
- Top-N (limit 10): `get_top_threat_types`, `get_top_policies`,
  `get_most_active_sessions`, `get_most_active_agents`.

**`TrendAnalyzer`** — `analyze` (slope/r² via linear regression, `classify_direction`),
`detect_anomalies(values, threshold=2.0)` (z-score), `compute_moving_trend`.
Direction: increasing, decreasing, stable, volatile.

**`ForecastEngine`** — three methods, all producing `ForecastResult` (method +
forecast/lower/upper points, `confidence_level=0.95`):
- `linear_forecast` — slope/intercept/r²; margin `1.96·std·sqrt(1+1/n)`.
- `moving_average_forecast(values, horizon, window=5)`.
- `exponential_smoothing_forecast(values, horizon, alpha=0.3)` — predicted =
  `level + trend·i`.

**`StatisticsEngine`** — pure stdlib stats: mean/median/mode/std_dev/variance/
percentile/min/max/count/sum, `linear_regression`, `moving_average`, EMA.

**`ReportGenerator`** — summaries (events, threats, performance, health) +
`format_report(report)` for export.

---

## 8. Dashboard — `dashboard\`

**`DashboardAPI`** — JSON facade over the engines, defensive wrapping (errors re-raised
as `DashboardError`):
`get_metrics`, `get_health`, `get_analytics`, `get_runtime`, `get_providers`,
`get_incidents(limit=50)`, `get_responses(limit=50)`, `get_policies`, `get_plugins`,
`get_alerts`, `get_snapshot`.

- **`DashboardEndpoints`** — thin wrappers translating errors per endpoint.
- **`DashboardSerializer`** — internal dicts → dashboard-shaped JSON
  (`serialize_metric/health/alert/trace/analytics/plugin/snapshot`,
  `serialize_list(items, serializer)`, `format_timestamp`).
- **Filters**: `DashboardFilter` (start/end/severity/status/limit/offset/format),
  `TimeRangeFilter` (`to_time_window()`), `MetricFilter`.
- **DTOs** (all `populate_by_name=True`, `timestamp` factory): `MetricsResponseDTO`,
  `HealthResponseDTO`, `AnalyticsResponseDTO`, `RuntimeResponseDTO`,
  `IncidentsResponseDTO`, `PoliciesResponseDTO`, `PluginsResponseDTO`,
  `ProvidersResponseDTO`, `ResponsesResponseDTO`, `AlertsResponseDTO`,
  `DashboardSnapshotDTO`.

Dashboard formats: json, compact, detailed. Granularity: minute, hour, day, week, month.

---

## 9. Exporters & Integrations

**Exporters** (all raise `ExporterError` on empty metrics / write failure):

| Exporter | Format |
|---|---|
| `JsonExporter` | envelope `{version, exported_at, metric_count, metrics}` |
| `CsvExporter` | columns `metric_id,name,timestamp,value,unit,labels` (labels as JSON) |
| `PrometheusExporter` | text exposition: `# HELP`/`# TYPE` + `name{labels} value timestamp_ms` |
| `OpenTelemetryExporter` | envelope `{resource, scope, metrics}`; `_OTLP_SCHEMA_URL` = schema 1.21.0 |

**Integrations** (`integrations\`, all export to local stores — no real network calls):

| Integration | Init / gating | Payload shape |
|---|---|---|
| `AzureMonitorIntegration` | `workspace_id` required | metrics validated for name/timestamp/value |
| `CloudWatchIntegration` | `initialize(namespace="QGuardian")` | `{MetricName, Value, Timestamp, Unit, Dimensions}` |
| `DatadogIntegration` | api_key + app_key required | `{series: [{metric, points, type, tags}]}` |
| `GrafanaIntegration` | api_url + api_key required | dashboard JSON `{dashboard: {..., schemaVersion: 36}, overwrite: true}` |
| `PrometheusIntegration` | `initialize(port=9090)` | `{name, value, labels, timestamp}`; `get_metrics_endpoint()` |

---

## 10. Events, Storage & Plugin

**Events** (extend framework `Event`, fixed `event_type` via `Field(init=False)`):

| Event | event_type |
|---|---|
| `MetricRecorded` | `observability.metric.recorded` |
| `HealthChanged` | `observability.health.changed` |
| `TraceStarted` | `observability.trace.started` |
| `TraceCompleted` | `observability.trace.completed` |
| `AlertRaised` | `observability.alert.raised` |
| `AlertResolved` | `observability.alert.resolved` |
| `DashboardUpdated` | `observability.dashboard.updated` |
| `AnalyticsGenerated` | `observability.analytics.generated` |

**`ObservabilityStorage`** — JSON persistence under `observability_storage/` with
subdirs `metrics/`, `traces/`, `alerts/`, `alert_events/`, `health/`, `analytics/`;
save/load/list/delete per type; `get_storage_stats()`.

**`ObservabilityPlugin`** — `name="observability"`, `version="1.0.0"`,
`interfaces=["observability","metrics","health","tracing","analytics","alerting"]`.
`initialize(context)` sets up the 5 engines; `start()` subscribes bus to `"*"`
(priority 100); `stop()` shuts down trace then alert engine. `_on_any_event` increments
`observability.events.total` (label `event_type`) and feeds `analytics_engine.ingest_event`.

---

## 11. Data Models at a Glance

- **`Metric` / `MetricPoint` / `MetricSeries` / `AggregatedMetric`** — series of
  `{timestamp, value, labels}`.
- **`Trace` / `Span` / `SpanStatus`** — `Span.finish(status)`, `add_event`,
  `set_attribute`; `Trace.add_span/get_root_spans/get_child_spans/finish`.
- **`HealthStatusModel` / `HealthCheckResult` / `HealthReport`** — per-component
  status/score/level + aggregate report.
- **`AlertRule` / `Alert` / `AlertEvent`** — rule `evaluate(value)` uses condition
  lambdas; alert `acknowledge/resolve/escalate/suppress`.
- **`TrendData` / `ForecastResult` / `AnalyticsReport`** — trends, forecasts, and the
  full report (threat/policy/risk/response trends, provider accuracy, usage counters,
  top lists, summary).
- **`RuntimeStatistics` / `PerformanceMetrics` / `ResourceMetrics`** — runtime,
  latency (prompt/detection/fusion/quantum/ml/policy/response + p50/p95/p99), and
  resource snapshots.
- **`DashboardSnapshot`** — combines runtime + performance + resources + health +
  alerts + top metrics.

---

## 12. Quick Start

```python
from q_guardian.observability import MetricsEngine, TraceEngine, AlertEngine, AlertRule

metrics = MetricsEngine()
metrics.initialize()
metrics.increment("requests.total")
metrics.record_value("latency_ms", 42)

trace = TraceEngine()
ctx = trace.start_trace("scan_prompt", correlation_id="abc")
trace.finish_trace(ctx.trace_id)

alerts = AlertEngine()
alerts.initialize(metrics_engine=metrics)
alerts.add_rule(AlertRule(name="high-latency", metric_name="latency_ms",
                          condition="gt", threshold=100))
alerts.evaluate_rules()          # fires when threshold crossed (respecting cooldown)
```

---

## 13. Exceptions

`ObservabilityError(ApplicationException)` with `code` per area:
`METRIC_ERROR` (MetricError), `TRACE_ERROR`, `HEALTH_ERROR`, `ANALYTICS_ERROR`,
`ALERT_ERROR`, `EXPORTER_ERROR`, `DASHBOARD_ERROR`, `OBSERVABILITY_STORAGE_ERROR`
(StorageError, exported as `ObservabilityStorageError`), `CONFIGURATION_ERROR`.
