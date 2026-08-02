# 18 - Tests, Scripts & Examples

> Repository: `tests\` (2,339 tests / 107 files), `scripts\`, and `examples\`.
> Companion doc for the Q-Guardrail documentation set — covers the test suite, the
> developer tooling under `scripts/` (prompt CLI, training, benchmarks, load tests,
> profiling, packaging), the runnable examples under `examples/`, and the docs/root
> files they build upon.

---

## 1. Test Suite Overview

```
 tests\
 ├── conftest.py             (root: env bootstrap + shared fixtures, 105 lines)
 ├── fixtures\conftest.py    (duplicate fixture set for package-local import safety)
 ├── integration\            (2 files: FastAPI app + Guardian lifecycle)
 ├── response\               (9 files: engines, evidence, quarantine, playbooks, ...)
 ├── observability\          (24 files: metrics, tracing, health, alerts, dashboard, ...)
 └── unit\                   (70 files: config, events, framework, fusion, hooks, ml,
                             plugins, policy, quantum, risk, runtime, sdk, security, utils)
```

| Category | Count |
|---|---|
| Total test functions | **2,339** |
| — synchronous (`def test_`) | 2,120 |
| — asynchronous (`async def test_`) | 219 |
| `@pytest.mark.asyncio` markers | 160 |
| `@pytest.fixture` definitions (incl. conftest) | 53 |
| `@pytest_asyncio.fixture` definitions | 3 |
| `@pytest.mark.parametrize` / `unit` / `integration` / `slow` / `skip` / `xfail` | **0** |

There are **no** registered pytest markers: classification is by directory
(`tests\unit\`, `tests\integration\`). Async tests always carry an explicit
`@pytest.mark.asyncio` (no global `asyncio_mode = auto`); the `anyio_backend`
fixtures return `"asyncio"`.

| Directory | Test files | Coverage areas |
|---|---|---|
| `tests\integration\` | 2 | FastAPI app + Guardian lifecycle |
| `tests\observability\` | 24 | alerting, metrics, tracing, health, dashboard, storage, exporters, plugin |
| `tests\response\` | 9 | engines, evidence, integrations, notifications, orchestration, playbooks, plugin/storage, quarantine, response engine |
| `tests\unit\` | 70 | config, events, framework, fusion, hooks, ml, plugins, policy (9), quantum (13), risk (7), runtime (5), sdk, security (4), utils |
| **Total** | **105 test files + 2 conftest** | |

---

## 2. Shared Test Configuration — `conftest.py`

**`tests\conftest.py` (root)** makes fixtures available to all subdirectories and
bootstraps async: on Windows it installs `asyncio.WindowsSelectorEventLoopPolicy()`
at import time.

| Fixture | Scope | Returns / Purpose |
|---|---|---|
| `_set_test_environment` | function, `autouse=True` | Sets `ENVIRONMENT=testing`, `DEBUG=true`, `MONGODB_URL=mongodb://localhost:27017`, `MONGODB_DATABASE=q_guardian_test` before every test; pops them after. |
| `anyio_backend` | session | `"asyncio"` — selects the async backend for pytest-asyncio. |
| `app` | session | Lazily imported `q_guardian.api.app.create_app` FastAPI instance. |
| `client` | function, `@pytest_asyncio.fixture` | `httpx.AsyncClient` via `ASGITransport`, `base_url="http://test"`. |
| `settings` | function | `get_settings()` composite settings object. |
| `sample_uuid` | function | Fresh UUID v4 string via `q_guardian.utils.uuid_utils.generate_uuid`. |
| `sample_correlation_id` | function | Fresh 12-char correlation ID via `generate_correlation_id`. |

**`tests\fixtures\conftest.py`** duplicates the same seven fixtures for package-local
import safety (identical semantics; `app` imports `create_app` at module top).

---

## 3. Test Inventory

### 3.1 `tests\integration\` (2 files)

- **`test_api.py`** — FastAPI app endpoints, 7 tests. `TestRootEndpoint` (root returns
  200, app-info body), `TestHealthEndpoint` (200, `status`/`timestamp` structure,
  correlation id + 12-char format, debug/testing reflection).
- **`test_framework_lifecycle.py`** — `Guardian` + plugin hooks via a
  `LifecycleTrackerPlugin` stub, 5 tests. `start()` initializes/starts plugins,
  `shutdown()` stops them, state moves INITIALIZING → RUNNING → STOPPED,
  `framework.started`/`framework.stopped` events published.

### 3.2 `tests\response\` (9 files)

| File (subject) | Tests | Highlights |
|---|---|---|
| `test_engines.py` (`response.engines`) | 22 | Rollback (record/restore/unknown/metadata), Recovery (recommend/execute/order), Approval (request/approve/reject/timeout/permission/delegation), EngineRegistry (register/get/list/unknown), engine health/metrics/errors/cancellation. |
| `test_evidence.py` (`response.evidence`) | 15 | Collector (capture/tags/list/errors), Snapshot (create/immutable/restore), Timeline (append/order/query/export), dedupe, TTL, hashing, health. |
| `test_integrations.py` (`response.integrations`) | 18 | Sentinel/Splunk/QRadar/Cortex/ServiceNow clients: connect/send, timeout/retry/auth/payload shape, async, circuit breaker, metrics, batch, attachment. |
| `test_notifications.py` (`response.notifications`) | 14 | Notifier routing/selection/history/retry/severity filter/priority, email/webhook/Slack/Teams channels, disabled/failed channels, config, health. |
| `test_orchestration.py` (`response.orchestration`) | 20 | Workflow create/add/execute, failure/rollback/retry/timeout/parallel/sequential/condition/state, events/metrics/health, cancel/resume/priority/dedupe/audit/error detail. |
| `test_playbooks.py` (`response.playbooks`) | 24 | Registry (register/get/unknown/list), parser (YAML/JSON/invalid), executor (run/steps/skip/failure), validator (valid/missing name/missing steps), built-ins (templates/quarantine/rollback/notify), variables/timeout/metrics/events/health/export. |
| `test_plugin_storage.py` (`response.plugin` + `.storage`) | 16 | Plugin metadata/health/config, registry register/unregister/get/list, storage save/load/missing/list/delete/persist/stats/clear/error handling. |
| `test_quarantine.py` (`response.quarantine`) | 18 | Manager init/add/remove/list/release-all, session/agent/plugin/memory providers, policy, TTL, events/metrics/health, unknown/duplicate, reason, audit. |
| `test_response_engine.py` (`response.response_engine`) | 21 | Init/handle/clean/threat, pipeline order, playbook binding, quarantine-on-block, notify-on-threat, evidence, recovery, rollback, timeout, events/metrics/health, config, errors, audit, history, batch, plugin hooks. |

### 3.3 `tests\observability\` (24 files)

| File (subject) | Tests | Highlights |
|---|---|---|
| `test_alert_engine.py` | 20 | Rule evaluation/trigger/recovery/dedupe/rate-limit, batch, custom rules, suppression, severity, cooldown, labels/annotations, events/metrics/health/history. |
| `test_alert_helpers.py` | 24 | `AlertRuleManager` (add/remove/list/get/enable/validate), `AlertRouter` (route/match/default), notifiers (send/channels/failure/retry), escalation (levels/chain/max/timer), rule parser, intervals, health/stats/eval-time. |
| `test_analytics_engine.py` | 14 | Record/query/aggregate/time-bucket/rollup/filter/group, empty data, batch, events/metrics/health, error handling. |
| `test_config.py` | 18 | Defaults/custom for engine/alert/tracing/metrics/exporter/health configs, validation, `model_dump`/`model_validate` roundtrips, thresholds, sample-rate/interval/batch-size validation, merge, immutability, validation status. |
| `test_dashboard.py` | 28 | Data assembly + time ranges, metric/alert/trace/health panels, serializers + roundtrip, DTOs, filters (metric/alert/trace/composite/empty), limit/offset/sort/aggregate/export, error/auth, events/health/config/empty-state. |
| `test_data_models.py` | 20 | `TimeWindow`, `Alert`, `Metric`, `Trace`, `Span`, `HealthStatus`, `HealthCheck` + roundtrip/deep-copy/equality/hash/defaults/optional/metadata/timestamps/enum defaults/ValidationError. |
| `test_enums.py` | 12 | Values for AlertSeverity/AlertStatus/MetricType/TraceStatus/HealthStatus/EventType/ExportFormat, membership, `from_value`, serialization, completeness. |
| `test_events.py` | 14 | Alert/Metric/Trace/Health event types, base fields (id/timestamp/source), data payload, serialization, subscribe/dispatch, bus integration, error containment, priority, dedup, retention, health. |
| `test_exceptions.py` | 8 | Base exception code/message, hierarchy, per-area errors, structured `to_dict`. |
| `test_exporters.py` | 18 | Prometheus (text/histogram/labels), OpenTelemetry (+traces), JSON/CSV (+header), batch/empty/error, stats/health, registry/selector, chunking/encoding/roundtrip. |
| `test_health_engine.py` | 16 | Check registration/run/aggregate, healthy/degraded/unhealthy status, timeout, cron scheduling, dependencies, details, config, events/metrics/health. |
| `test_health_helpers.py` | 18 | `HealthRegistry`, `HeartbeatManager` (start/stop/interval/stale/events), `DiagnosticEngine` (run/collect/report/error/recommendation), health + metrics. |
| `test_integrations.py` | 16 | Grafana/Datadog/Azure Monitor/CloudWatch/Prometheus clients: push/remote-write, auth/timeout/retry/failure containment, usage metrics, health, config, async. |
| `test_metric_aggregators.py` | 16 | Sum/avg/min/max/count/percentile/p95/histogram, empty/NaN, label/time-aware, registry/selector/composite, health. |
| `test_metric_collectors.py` | 16 | CPU/memory/disk/network/process collectors, interval/labels/schema/error, registry/selector/start-stop/batch/metrics/health/async. |
| `test_metric_registry.py` | 12 | Register/get/list/duplicate/unregister/exists, label lookup, query by type/labels, clear/count/health/events. |
| `test_metrics_engine.py` | 22 | Record/collect/query/aggregate/export, alert-engine integration, labels/time-range/bucket, empty/batch/error/retention/dedup/compression/rollup/thresholds, events/metrics/health/config. |
| `test_performance.py` | 18 | Latency record/stats, throughput, percentiles, thread safety, async ops, worker pool, queue, backpressure, timeouts, cancel/error/config, cleanup. |
| `test_plugin.py` | 14 | Observability plugin metadata/health/config, initialize/start/stop, metric/trace/alert/dashboard/export methods, `MockContext`, error handling, events. |
| `test_statistics.py` | 12 | Mean/median/mode/stddev/variance/min-max/quartiles/moving average/correlation/regression, empty input, health. |
| `test_storage.py` | 18 | File-backed storage for metrics/traces/alerts (+alert events): save/load/list/delete/exists/count/clear/persist/stats/error/health. Local fixtures `storage_root`, `storage`, `sample_metric/trace/alert/alert_event`. |
| `test_trace_engine.py` | 18 | Start/end trace, add spans, parent/child hierarchy, get/list/search/export, sampling, max spans/traces, retention, events/metrics/health/error, async. |
| `test_tracing_helpers.py` | 18 | `TraceContext`, `CorrelationManager` (generate/lookup/link/root), `SpanManager` (start/end/child/tags/logs/active/clear), events/metrics/health/async. |
| `test_trend_forecast.py` | 16 | `TrendAnalyzer` (direction/slope/flat/noise/window), `ForecastEngine` (linear/polynomial/confidence/horizon/errors/seasonal/insufficient), events/metrics/health. |

### 3.4 `tests\unit\` (70 files)

Unit tests are grouped into `TestXxx` classes (one per subject). Heaviest clusters:

| Cluster | Files | Notable coverage |
|---|---|---|
| **policy** (9 files) | condition DSL parser (47), engine (38), core data/enums (66), evaluator (16), registry (21), RBAC (15), simulation (14), storage (13), version manager (18), conflict detector (12), composition (16), DSL adapters (22) | Full module-8 coverage: operator semantics, priority sorting, conflict detection, version bumping, RBAC roles, Rego/Cedar/YAML/JSON adapters, template/inherit/merge composition. |
| **quantum** (13 files) | backends (35), feature maps (48), QSVM (43), kernel trainer (28), model manager (32), inference engine (34), storage (24), kernels (17), models+training (24), config/data (37), events (16), execution+plugin (17), phase-2 events (11) | Gate-level simulator (h/x/y/z/rx/ry/rz/cx/cz), ZZ/Pauli/angle feature maps, Phase-2 QSVM lifecycle, kernel grid/random search, model registry. |
| **risk** (7 files) | core (50), assessment (46), policy (33), actions (30), explainability (21), engine (15), plugin+storage (20) | Threat/trust/confidence/severity engines, 4 built-in policies, ActionEngine responders, reasoning graph + explanation formats. |
| **ml** (12 files) | detectors (18), config/events (16), datasets (16), training (16), model manager (16), storage (14), fusion-adjacent (strategies 24, adapters 20, engine 20, calibrator 14, events 14, prediction 12) | IsolationForest/RandomForest/XGBoost, ensemble voting, k-fold CV, feature pipelines, `ThreatPrediction`/`ReasoningTrace`. |
| **runtime** (5 files) | models (66), managers (37), context (17), events (13), SDK integration (15) | `Agent`/`AgentSession`/`AgentRequest`/`AgentResponse`/`TokenUsage`/`ToolInvocation`/`MemoryAccess`/`SecurityContext`/`ThreatContext`/`RiskContext` + enum completeness. |
| **security** (4 files) | pipeline (42), models (22), plugin+SDK (15), decision (13) | Normalizer/validator/feature extractor/rule engine; allow/block/review/warn decision matrix; `PromptScannerPlugin` + Guardian integration. |
| **sdk** (2 files + integration) | `test_sdk.py` (18), `test_runtime_sdk.py` (15) | `Guardian` init/lifecycle/plugins/events/adapters/hooks; runtime wiring (set_agent, create/close session, manager access). |
| **singles** | config (~16), event_bus (~18), exceptions (~12), framework config/state (~26), hooks (~18), utils (24) | Settings roundtrips + env overrides, pub/sub incl. wildcard + `publish_sync`, `GuardianError` hierarchy, `FrameworkConfig`/`FrameworkState`, hook manager, `uuid_utils`/`datetime_utils`/`json_utils`/`helpers`. |

---

## 4. Test Helpers, Fixtures & Conventions

**Module-level `_`-prefixed factory helpers** (per file): `_policy(...)` (composition/
engine/storage/version_manager), `_rule(...)` (conflict detector), `_make_policy(...)`
(evaluator/registry), `_policy_with_rules()` (simulation), `_make_decision(...)` /
`_make_assessment(...)` (risk actions), `_make_prediction(...)` (risk), `_make_finding(...)`
(security decision), `_pred(...)` / `_invalid_pred(...)` (fusion), `_make_features(...)`
/ `_make_training_data(...)` (ml detectors), `_make_request(...)` (response engine),
`_make_metric(...)` (exporters), `_init_*_engine(...)` (performance), `_step(...)` /
`_playbook(...)` (orchestration).

**In-file stub classes**: `DummyQuantumBackend`, `DummyFeatureMap`, `DummyKernel`,
`DummyQuantumModel`, `SimpleQuantumModel`, `DummyThreatModel`, `DummyModel`,
`DummySklearnModel`, `SimplePlugin`/`AnotherPlugin`/`FailingInitPlugin`, `SamplePlugin`,
`LifecycleTrackerPlugin`, `ConcreteEvent`, `SimpleProvider`/`FailingProvider`, `MockContext`.

**Module-scope fixture sets** live with their subsystem (not global conftest): quantum
engines (`backend`, `feature_map`, `kernel`, `engine`, `trained_qsvm*`), quantum storage
(`tmp_storage`, `sample_state`, `sample_metadata`), observability storage, runtime managers
(per-class `mgr`/`tracker`), event bus (`bus`).

**Conventions**: class-grouped tests; docstringed modules (`test_sdk.py`, `test_utils.py`
add per-test docstrings); randomness seeded (`np.random.default_rng(42)`, `random.Random(42)`,
quantum `sample_data` = 20×4 features uniform in `[-π, π]`); temp files via
`tempfile.TemporaryDirectory()`/`tmp_path`; numeric tolerance via `pytest.approx`; heavy
stubs imported lazily; no `@pytest.mark.parametrize` (loops instead).

---

## 5. Scripts — `scripts\`

```
 scripts\
 ├── __init__.py                 (0-byte package marker)
 ├── prompt_cli.py                interactive prompt tester (REPL)
 ├── train_data.py                train ML + QSVM from a labeled dataset
 ├── build_dataset.py             download deepset/prompt-injections + export CLI memory
 ├── benchmarks\                  benchmark_runner / benchmarks / run_benchmarks / __main__
 ├── loadtest\                    load_tester / reporter / scenarios / run_loadtest / __main__
 ├── packaging\                   build / validate / __main__
 └── profile\                     memory_profiler / optimization_report / run_profiler
```

### 5.1 Prompt tooling — `prompt_cli.py`, `train_data.py`, `build_dataset.py`

**`prompt_cli.py`** — interactive Q-Guardian prompt tester with persistent memory +
learning. Dynamically imports `examples/prompt_test_harness.py` for its `Pipeline` class
(`importlib.util.spec_from_file_location`, module name `"prompt_test_harness"`).

- Functions: `load_memory(path)` (JSONL reader, skips malformed lines), `append_memory`,
  `rewrite_memory`, `auto_label(action)` (`0` if `action.upper()=="ALLOW"` else `1`),
  `verdict_for(action)` (`ALLOW`→SAFE, `REVIEW`→SUSPICIOUS, else UNSAFE), `print_verdict`
  (per-path breakdowns grouped into Classical ML / Quantum QSVM / Rules), `main()`.
- REPL commands: `:quit/:exit/:q`, `:simple/:verbose` (output mode), `:label`
  (correct the auto label → sets `auto: False` + rewrites memory), `:learn` (retrain on
  the built-in corpus + all labeled memory), `:memory` (counts + last 10 records with
  `B`/`M`/`?` flags). `--forget` must be run outside the REPL.
- State: `examples/qg_memory.jsonl` + `examples/qg_state/` (`scaler.pkl`, `anomaly.pkl`,
  `rf.pkl`, `qsvm.json`, `corpus.json`); `--state-dir DIR` overrides.

```bash
python scripts/prompt_cli.py                  # interactive REPL
python scripts/prompt_cli.py "my prompt"      # single-shot
python scripts/prompt_cli.py --verbose "my prompt"
python scripts/prompt_cli.py --forget         # wipe memory + saved models
```

**`train_data.py`** — trains Isolation Forest + RandomForest + QSVM from a labeled dataset
(CSV / JSONL / NDJSON / JSON). `parse_label(raw)` maps booleans, 0/1, and string aliases
(`benign/safe/allow/ok/good` → 0; `malicious/unsafe/threat/escalate/block/deny/bad/attack`
→ 1). Per-class caps keep QSVM fast (defaults `--max-samples 200`, `--qsvm-samples 80`),
shuffle seed 42, optional built-in 20-prompt demo corpus (`--base`), RF self-check
accuracy printed. Outputs to `--state-dir` (default `examples/qg_state/`).

```bash
python scripts/train_data.py my_dataset.csv
python scripts/train_data.py my_dataset.jsonl --base
python scripts/train_data.py my_dataset.json --replace --max-samples 500
```

**`build_dataset.py`** — "makes the fuel": downloads the `deepset/prompt-injections`
benchmark (662 rows, Apache-2.0) over plain HTTP via the HF datasets-server rows API
(`https://datasets-server.huggingface.co/rows`; no `datasets`/pandas dependency) and/or
exports deduplicated CLI memory (`examples/qg_memory.jsonl`). Can chain directly into
`train_data.py` with `--train` (`subprocess.run`). Outputs `data/prompt_injections.jsonl`,
optionally `data/user_collected.jsonl`.

```bash
python scripts/build_dataset.py                      # download benchmark
python scripts/build_dataset.py --from-memory        # also export CLI prompts
python scripts/build_dataset.py --train              # download + train right away
```

### 5.2 Benchmarks — `scripts\benchmarks\`

**`benchmark_runner.py`** — core infrastructure. `BenchmarkResult` dataclass (ns timings +
µs properties via `/1_000`, `ops_per_sec`, `to_dict`/`to_json`/`summary_line`),
`compute_stats` (total/avg/stddev via `statistics.stdev`, p50/p95/p99 via linear-interp
`_percentile`), `benchmark`/`async_benchmark` (default `iterations=100`, `warmup=10`,
`time.perf_counter_ns()`), and `BenchmarkSuite` (context manager, JSON persistence,
`print_table`, `compare_with(baseline)` flagging `"regression"` when `avg_delta > 10.0`).

**`benchmarks.py`** — concrete suites registered in `ALL_BENCHMARKS` (7 entries:
`startup`, `prompt_security`, `policy`, `event_bus`, `runtime`, `observability`, `ml`).
Each class has `__init__(iterations=100, warmup=10)` + `async run()`. Highlights:
`PromptSecurityBenchmark` uses 10 curated safe + 10 malicious prompts; `PolicyBenchmark`
benchmarks low/high/critical risk evaluations via `PolicyEvaluator` +
`create_default_policy()`; `MLEngineBenchmark` returns a skipped result
(`metadata={"skipped": "ML deps unavailable"}`) when ML imports fail.

**`run_benchmarks.py`** + **`__main__.py`** — CLI (`python -m scripts.benchmarks`).
Flags: `--iterations/-n` (100), `--warmup/-w` (10), `--output-format/-f` (json/text/both),
`--output/-o`, `--suites`, `--compare`/`--baseline`. Saves `scripts/benchmarks/
results_<unix_timestamp>.json` by default; direct runs produce
`scripts/benchmarks/_individual_results.json` and a `_runner_smoke.json` noop-baseline.

```bash
python -m scripts.benchmarks --iterations 50 --warmup 5 --suites startup policy
python -m scripts.benchmarks --compare scripts/benchmarks/results_<ts>.json --output results.json
```

### 5.3 Load tests — `scripts\loadtest\`

**`load_tester.py`** — async engine. `LoadTestConfig` (frozen/slots; defaults
`concurrent_sessions=100`, `duration_seconds=30.0`, `ramp_up_seconds=5.0`,
`target_sessions=100`; validates concurrent ≥1, duration >0, 0 ≤ ramp ≤ duration).
`LoadTestResult` (totals, error rate, avg/p50/p95/p99/peak latency, `throughput_rps`,
memory via `tracemalloc` (+optional `psutil` RSS), `summary_dict()`). `LoadTestScenario`
ABC (`name`, `setup`, `execute_session`, `teardown`). `LoadTestEngine.run` runs a
producer/consumer loop with `asyncio.Semaphore(concurrent_sessions)`, ramp-up scaling,
`_percentile` latency stats.

**`scenarios.py`** — 4 concrete scenarios over `_SAMPLE_PROMPTS` (30 mixed prompts):
`PromptScanScenario` (`prompt_scan`; normalizer→validator→features→rule engine),
`SessionLifecycleScenario` (`session_lifecycle`; shared `SessionManager` +
`Agent(name="loadtest-agent", framework="loadtest")`), `MixedWorkloadScenario`
(`mixed_workload`; rolls <0.5 prompt scan, <0.8 session lifecycle, else policy eval with
`risk_score = mean(finding.confidence)`), `BurstScenario` (`burst`; default
`burst_size=200`, concurrency produces the burst).

**`reporter.py`** — `LoadTestReporter` (static): `to_markdown` (summary/latency/memory/
errors/configuration tables), `compare_markdown`, `to_json` (latencies capped 1000,
errors capped 100), `detect_regressions(baseline, current)` — error rate +5 pts, avg/p95
ratio ≥1.5, throughput ratio ≤0.7, peak-memory ratio ≥2.0.

**`run_loadtest.py`** + **`__main__.py`** — CLI. `--profile` quick/medium/heavy/extreme
(concurrent/target/duration/ramp: 50/100/15/3 · 200/500/30/5 · 500/1000/60/10 ·
1000/5000/120/20), `--scenario`, explicit `--concurrency/--duration/--ramp-up/--target`,
`--output` (json/markdown/both), `--save`, `--compare`. Results saved to
`scripts/loadtest/results/<scenario>_<YYYYMMDD_HHMMSS>.json`.

```bash
python -m scripts.loadtest --profile medium
python -m scripts.loadtest --scenario prompt_scan --duration 60
python -m scripts.loadtest --concurrency 500 --target 5000 --output json
```

Sample persisted results show e.g. `burst_20260719_035126.json`: 63 requests, 0.87 ms
avg, ~62.9 rps over 1.0 s; `prompt_scan_...`: 190 requests, 0.77 ms avg, ~63.2 rps over
3.0 s; `mixed_workload_...`: 64 requests, 5.73 ms avg (p95 16.9 ms), ~62 rps.

### 5.4 Packaging — `scripts\packaging\`

**`build.py`** — builds wheel + sdist via `python -m build` after cleaning `dist/`,
`build/`, and `*.egg-info` (`_clean`), then lists artifact sizes + contents
(`_list_wheel` via zipfile, `_list_sdist` via tarfile). Constants `ROOT = parents[2]`,
`DIST = ROOT/"dist"`, `BUILD = ROOT/"build"`.

```bash
python scripts/packaging/build.py      # or: python -m scripts.packaging build
```

**`validate.py`** — metadata/structure validator: required `pyproject.toml` fields
(`REQUIRED_PYPROJECT_FIELDS = ["name","version","description","license",
"requires-python"]`), version consistency with `src/q_guardian/__init__.py` (`__version__`
line scan), non-empty `LICENSE`/`README.md`, and that every `__all__` export resolves to
an import. `sys.exit(1)` on any failure.

**`__main__.py`** — dispatcher: `python -m scripts.packaging <build|validate>`.

### 5.5 Profiling — `scripts\profile\`

**`memory_profiler.py`** — stdlib-only memory toolkit. `MemorySnapshot` (total/resident/
heap MB, object count, GC counts), `AllocationInfo`, `take_snapshot()` (GC stats,
tracemalloc heap, optional psutil RSS), `MemoryProfiler` (`start`/`stop` with daemon
`_poll_loop`, `top_allocations`, `detect_leak` — suspect if `heap_slope > 0.1 MB/s` or
`obj_slope > 100/s` with ≥3 snapshots, `gc_statistics`, `generate_report`),
`AllocationTracker` (≥1 MiB threshold, per-file `find_patterns`), `LeakDetector`
(`baseline_interval=5.0`, `detection_threshold=0.2`, least-squares heap-trend slope).

**`optimization_report.py`** — turns `generate_report()` output into `Finding`s
(category/severity info|warning|critical/title/description/recommendation/details) and
`OptimizationReport` with 4 checks (large allocations ≥1 MB, GC pressure >5
collections/snapshot, memory growth on leak-suspect, object-count growth >20%);
`to_markdown`/`to_json`/`save(path, fmt)`.

**`run_profiler.py`** — 4 subcommands:

```bash
python -m scripts.profile.run_profiler snapshot
python -m scripts.profile.run_profiler monitor --duration 30 --interval 1
python -m scripts.profile.run_profiler leak-detect --duration 60
python -m scripts.profile.run_profiler analyze --output report.json
```

---

## 6. Examples — `examples\`

### 6.1 `prompt_test_harness.py`

End-to-end prompt harness: normalize → validate → feature extraction → rules → classical
ML → quantum QSVM → hybrid fusion → risk assessment → strict policy → response action,
with per-stage timing and a reusable `Pipeline` class (dynamically imported by
`scripts/prompt_cli.py` and `scripts/train_data.py`).

- **Fusion wiring** — `HybridFusionEngine(WeightedVotingStrategy())` registers
  `_RuleProvider` (0.15), `_AnomalyProvider` (0.15), `_ClassifierProvider` (0.55),
  `_QuantumProvider` (0.15). RF is weighted highest "because rules fire only on exact
  keywords and the QSVM has ~0.5 neutral confidence".
- **Risk weights** — `RiskConfig(scoring_weights=ScoringWeights(probability=0.60,
  confidence=0.10, reliability=0.10, agreement=0.05, diversity=0.05, severity=0.10))`
  — re-weighted vs. stock defaults, which floor threat scores around 0.575.
- **Training** — `train()` fits `StandardScaler`, `IsolationForestDetector(
  n_estimators=50, contamination=0.2)`, `RandomForestThreatClassifier(n_estimators=50)`,
  then QSVM via `LocalSimulatorBackend(num_qubits=5, shots=1024)`,
  `AngleEncodingMap(num_qubits=5)`, `QuantumKernelEstimator(...)` (only the first
  `QUANTUM_FEATURE_COUNT = 5` ML features are angle-encoded).
- **Pipeline run** — 8 logged stages; policy step uses `strict-security`
  (`blocks at HIGH+`); returns dict with `features`, `fused`, `fused_label`,
  `confidence`, `providers`, `path_breakdown`, `rules`, `risk_level`, `risk_score`,
  `policy`, `action`, `timings_ms`.
- **State** — `save_state(state_dir)` pickles `scaler.pkl`/`anomaly.pkl`/`rf.pkl`,
  writes `qsvm.json` + `corpus.json`; `load_state` reverses it.

```bash
python examples/prompt_test_harness.py
python examples/prompt_test_harness.py "Your prompt here" "Another prompt"
```

### 6.2 Framework integration examples (all use mock framework types, no external deps)

All examples follow the same secured pattern: start `Guardian(FrameworkConfig())` →
register `PromptScannerPlugin()` → per request `scan_prompt` → `calculate_risk` →
`enforce_policy` → block/warn/execute (tracking tool invocations via
`guardian.tool_tracker`) → `monitor(...)`.

| Example | Framework label | Shows |
|---|---|---|
| `crewai/crewai_example.py` | `"crewai"` | 2-agent crew (researcher/writer), 3 tasks (one injection attempt), block/warn/allow, tool tracking, observability summary. |
| `google_adk/google_adk_example.py` | `"google_adk"` | Router→sub-agent delegation with cycle-protection (`visited` set), function-call tracking, cross-agent threat correlation. |
| `hybrid_multiagent/hybrid_multiagent_example.py` | `langgraph` / `crewai` / `openai_agents` / `google_adk` | `SecurityCoordinator` securing a 4-framework fleet; unified policy, cross-agent `ThreatContext`s, aggregate dashboard (agents/block-rate/threats/events/runtime stats). |
| `langgraph/langgraph_example.py` | `"langgraph"` | 4-node graph (ingest→reason→tool_call→respond); per-node scanning, `set_agent` + `create_session`, block-at-node, per-node observability. |
| `openai_agents/openai_agents_example.py` | `"openai_agents"` | `_detect_threats` maps high/critical findings to `ThreatContext` (`PROMPT_INJECTION`/`JAILBREAK`/`DATA_EXFILTRATION` by category), dashboard. |
| `semantic_kernel/semantic_kernel_example.py` | `"semantic_kernel"` | Plugin/function-level enforcement, chat-context scanning (`context="chat"`), per-plugin observability (total/allowed/blocked, per-plugin avg risk). |

### 6.3 `examples\qg_state\` — persisted model artifacts

| File | Content |
|---|---|
| `anomaly.pkl` (105,595 B) | Pickled `IsolationForestDetector` (binary; loaded via `pickle.load`). |
| `rf.pkl` (59,338 B) | Pickled `RandomForestThreatClassifier`. |
| `scaler.pkl` (1,474 B) | Pickled fitted `sklearn.preprocessing.StandardScaler`. |
| `qsvm.json` (4,151 B) | `QSVMModel.save()` output: `name`, `version` (`"1.0.0"`), `train_X`/`train_y` (20 samples, 5-dim), `support_vectors`, `support_labels`, `dual_coeffs`, `bias`, `classes`, `trained`, `training_time_s`, `kernel_time_s`, `kernel_name`, `feature_map_name`. |
| `corpus.json` (1,364 B) | The 20-prompt demo corpus as `[text, label]` pairs (10 benign + 10 malicious). |

### 6.4 `examples\qg_memory.jsonl`

Persistent prompt-memory written by `scripts/prompt_cli.py`. One JSON object per line:
`ts` (`%Y-%m-%d %H:%M:%S`), `text`, `label` (0/1), `auto` (True=auto-assigned,
False=user-corrected via `:label`), `action`, `risk_level`, `risk_score` (4 dp).
The shipped sample illustrates why `:label`/`:learn` exist: default `ScoringWeights` floor
often scores even benign prompts ~0.60 ("high"), and auto-labels can misfire.

---

## 7. `docs\`, Root Files & Build Artifacts

### 7.1 `docs\` — maintained guides

| File | Topic |
|---|---|
| `api-reference.md`, `architecture-guide.md`, `configuration-guide.md`, `deployment-guide.md`, `developer-guide.md` | REST + SDK reference; layered plugin-driven architecture; layered config + env precedence; Docker/Compose/MongoDB deployment; dev setup, testing, style. |
| `event-system.md`, `framework-architecture.md` | Async pub/sub bus (wildcards, `"threat.*"`, `"*"`); `FrameworkStateMachine` (INITIALIZING/RUNNING/STOPPED/ERROR), plugins, hooks. |
| `migration-guide.md`, `security-review.md`, `troubleshooting-guide.md` | Version compatibility + breaking changes (0.8.x→0.10.0); automated security review (2026-07-19, v0.9.0, "Moderate" posture); common error fixes. |
| `ml-security.md`, `quantum-analysis-research.md`, `operations-guide.md` | Module 5 ML layout; Module 6 research doc (IEEE-quality, v0.1.0); Prometheus/Grafana/alerting/backup. |
| `plugin-dev-guide.md`, `plugin-development.md`, `runtime-architecture.md`, `user-guide.md` | Full + concise plugin lifecycle; runtime abstraction layer (no detection logic); end-user install/quick-start. |

### 7.2 Root repository files

- **`LICENSE`** — MIT, Copyright (c) 2026 Q-Guardian Research Team (development license).
- **`LICENSE_PENDING.md`** — private-research phase; final public license TBD before v1.0.0.
- **`CODE_OF_CONDUCT.md`** — Contributor Covenant v2.1.
- **`CONTRIBUTING.md`** — venv + `pip install -e ".[dev]"`, `pytest tests/ -v [--cov=...]`,
  `ruff check/format src/ tests/`.
- **`SECURITY.md`** — vulnerability reporting (ack in 48h, assessment in 1 week), scope,
  deployment best practices.

### 7.3 `src\q_guardian.egg-info\` — build artifacts

Regenerated automatically by PEP 517/518 builds and cleaned by `scripts/packaging/build.py`;
not hand-maintained.

- **`PKG-INFO`** (482 lines) — `Name: q-guardian`, `Version: 0.10.0rc1`, MIT, Python
  >=3.12, classifiers (Dev Status 4-Beta), full dependency list with extras
  (`ml`, `ml-xgboost`, `datasets`, `quantum`, `quantum-pennylane`, `dev`) + embedded README.
- **`requires.txt`** (41 lines) — base runtime deps (fastapi, uvicorn[standard], pydantic,
  pydantic-settings, python-dotenv, motor, pymongo, structlog, httpx, python-jose
  [cryptography], passlib[bcrypt], orjson) + extra sections mirroring `Requires-Dist`.
- **`SOURCES.txt`** (310 lines) — sdist file list: LICENSE, README, pyproject.toml, all
  `src/q_guardian/**` modules, and the egg-info files themselves.

---

## 8. Quick Start

```bash
# 1) Run the whole suite (Windows event-loop policy is auto-installed)
pytest tests/ -v

# 2) Interactive prompt tester (trains + saves models on first run)
python scripts/prompt_cli.py

# 3) Re-train models from a labeled dataset, then scan prompts
python scripts/build_dataset.py --from-memory --train
python scripts/prompt_cli.py --forget

# 4) Benchmark / load-test / profile
python -m scripts.benchmarks --suites startup policy
python -m scripts.loadtest --profile quick
python -m scripts.profile.run_profiler monitor --duration 30

# 5) Package validation + build
python -m scripts.packaging validate
python -m scripts.packaging build
```

---

## 9. Key Conventions

- Test discovery is directory-based (`tests\unit\`, `tests\response\`,
  `tests\observability\`, `tests\integration\`); no pytest markers are registered.
- Async is always explicit (`@pytest.mark.asyncio`); the root conftest installs the
  Windows selector event-loop policy on `win32`.
- Helpers/stubs are prefixed `_` and kept at module scope; heavy imports are lazy;
  randomness is seeded for determinism; storage tests write only to temp dirs.
- All scripts run as `python -m scripts.<sub> ...` modules; `prompt_cli.py` and
  `train_data.py` share the harness `Pipeline` via dynamic import — no source edits.
- Build artifacts under `egg-info` and benchmark/loadtest result JSON files are generated
  outputs, cleaned or overwritten by the tooling.
