# 05. Test File Documentation — Q-Gaudrail

> **Document index:** this is document 05 of the Q-Gaudrail technical documentation set.
>
> **Coverage:** every test file under `tests/` (133 `test_*.py` + `conftest.py`/`__init__.py`), one entry each. **2,751 test functions** in total (per the current CI test run).

## 1. Suite Overview

| Directory | Test files | Test count (functions) | Focus |
|---|---|---|---|
| `tests/integration/` | 2 | 12 | FastAPI app endpoints, Guardian lifecycle |
| `tests/observability/` | 24 | ~390 | alerts, metrics, tracing, health, analytics, dashboard, exporters, integrations |
| `tests/response/` | 9 | ~168 | response engines, evidence, playbooks, quarantine, notifications, integrations |
| `tests/unit/` | 98 | ~2,181 | policy, quantum, risk, ml, fusion, runtime, sdk, security, core, benchmark, embeddings, training pipeline |
| **Total** | **133 `test_*.py`** | **2,751** | |

Global conventions (see §5 below): class-based `TestXxx` grouping, module-level `_`-prefixed helper factories, local module-scope fixtures, explicit `@pytest.mark.asyncio`, seeded RNG (`np.random.default_rng(42)`), tempfile isolation, no `@pytest.mark.parametrize`.

## 2. Shared Configuration

### 2.1 `tests/conftest.py` (root, 105 lines)
Global fixtures for the whole suite; installs `asyncio.WindowsSelectorEventLoopPolicy()` on Windows.

| Fixture | Scope | Purpose |
|---|---|---|
| `_set_test_environment` | function (autouse) | Sets `ENVIRONMENT=testing`, `DEBUG=true`, `MONGODB_URL=mongodb://localhost:27017`, `MONGODB_DATABASE=q_guardian_test` before each test; pops after. |
| `anyio_backend` | session | Returns `"asyncio"` |
| `app` | session | `create_app()` FastAPI instance |
| `client` | function | `httpx.AsyncClient` via `ASGITransport`, `base_url="http://test"` |
| `settings` | function | `get_settings()` |
| `sample_uuid` | function | UUID v4 string |
| `sample_correlation_id` | function | 12-char correlation ID |

### 2.2 `tests/fixtures/conftest.py` (84 lines)
Package-local duplicate of the root conftest fixtures (same semantics).

### 2.3 `__init__.py` files
- `tests/__init__.py` — empty marker.
- `tests/fixtures/__init__.py`, `tests/integration/__init__.py`, `tests/observability/__init__.py`, `tests/response/__init__.py`, `tests/unit/__init__.py` — package markers.

## 3. `tests/integration/` (2 files)

| File | Subject | Count | Tests cover |
|---|---|---|---|
| `test_api.py` | `q_guardian.api.app` | 7 | Root endpoint 200 + app info; `/health` 200, structure (`status`/`timestamp`), correlation id + 12-char format, debug payload |
| `test_framework_lifecycle.py` | `q_guardian.sdk.guardian.Guardian` + hooks | 5 | `LifecycleTrackerPlugin` stub: start initializes plugins, start calls plugin start, shutdown stops plugins, state transitions INITIALIZING→RUNNING→STOPPED, `framework.started`/`stopped` events |

## 4. `tests/response/` (9 files)

| File | Subject | Count | Key coverage |
|---|---|---|---|
| `test_engines.py` | `response.engines` | 22 | Rollback (state record/restore/unknown raises/metadata), Recovery (recommend/execute/complete/step order), Approval (request/approve/reject/timeout/delegation/permissions), EngineRegistry (register/get/list/unknown), engine health/metrics/errors/cancellation |
| `test_evidence.py` | `response.evidence` | 15 | EvidenceCollector (capture/tags/list/errors), EvidenceSnapshot (create/immutable/restore), EvidenceTimeline (append/order/query/export), dedupe, TTL, hashing, health |
| `test_integrations.py` | `response.integrations` | 18 | Sentinel (connect/send/payload), Splunk (forward/batch), QRadar (offense), Cortex (alert), ServiceNow (ticket/attachment); timeouts, retry, health, failure mode, auth, payload shape, async, circuit breaker, metrics |
| `test_notifications.py` | `response.notifications` | 14 | Notifier (send/channel selection/history/retry/severity filter/priority/config/health); Email, Webhook, Slack (blocks), Teams (cards); disabled/failed channels |
| `test_orchestration.py` | `response.orchestration` | 20 | Workflow create/add-step/execute, failure handling, rollback, retry, timeout, parallel/sequential, conditional, state, events, metrics, health, cancel, resume, priority, dedupe, audit, error detail |
| `test_playbooks.py` | `response.playbooks` | 24 | Registry (register/get/unknown/list); Parser (YAML/JSON/invalid); Executor (run/steps/skip/failure/metrics/events/variables/timeout/export); Validator (valid/missing name/missing steps); built-in templates (quarantine, rollback, notify); health |
| `test_plugin_storage.py` | `response.plugin` + `response.storage` | 16 | ResponsePlugin (metadata/health/config); PluginRegistry (register/unregister/get/list); ResponseStorage (save/load/missing/list/delete/persist/stats/clear/error handling) |
| `test_quarantine.py` | `response.quarantine` | 18 | QuarantineManager (init/add/remove/list/release_all/events/metrics/health/unknown/duplicate/reason/audit); Session/Agent/Plugin/Memory providers; policy; TTL |
| `test_response_engine.py` | `response.response_engine` | 21 | Engine init/handle; clean→allow, threat→block; pipeline order; playbook binding; quarantine on block; notify on threat; evidence collection; recovery/rollback triggers; timeout; events; metrics; health; config; error containment; audit; history; batch; plugin hook |

## 5. `tests/observability/` (24 files)

| File | Subject | Count | Key coverage |
|---|---|---|---|
| `test_alert_engine.py` | `observability.alert_engine` | 20 | Evaluate metric vs rules, trigger/no-trigger, rule registry, recovery, dedupe, rate limit, events, metrics, health, batch, custom rules, error handling, history, suppression, severity, cooldown, labels, annotations |
| `test_alert_helpers.py` | alert helpers (rules/router/notifier/escalation) | 24 | AlertRuleManager (add/remove/list/get/enable/disable/validate/parser/interval/eval time); AlertRouter (route/match/default/no-match/stats/health); notifier (send/channels/failure/retry); escalation (levels/chain/max/timer) |
| `test_analytics_engine.py` | `observability.analytics_engine` | 14 | Record/query/aggregate/time-bucket/rollup/filter/group, empty data, events, metrics, health, batch, error handling |
| `test_config.py` | `observability.config` | 18 | Default/custom configs, alert/tracing/metrics/exporter/health configs, validation, serialization roundtrips, thresholds, sample rate, interval, batch size, merge, immutable, health |
| `test_dashboard.py` | `observability.dashboard` | 28 | Data assembly, time range, metric/alert/trace/health panels; serializers (metric/alert/trace/roundtrip); DTO defaults/validation; filters (metric/alert/trace/composite/empty); limit/offset/sort/aggregate/export/error/auth/events/health/config/empty-state |
| `test_data_models.py` | `observability.data` | 20 | `TimeWindow`, `Alert`, `Metric`, `Trace`, `Span`, `HealthStatus`, `HealthCheck`: fields, validation, roundtrip, deep copy, equality, hash, defaults, optional, metadata, timestamps, enum defaults, ValidationError |
| `test_enums.py` | `observability.enums` | 12 | AlertSeverity/Status, MetricType, TraceStatus, HealthStatus, EventType, ExportFormat: values, membership, from_value, serialization/deserialization, completeness |
| `test_events.py` | `observability.events` | 14 | Alert/Metric/Trace/Health event types, base fields, data payload, serialization, dispatch, bus integration, error containment, priority, dedup, retention, health |
| `test_exceptions.py` | `observability.exceptions` | 8 | Base exception, hierarchy, Alert/Metric/Trace/Export/Storage errors, structured dict |
| `test_exporters.py` | `observability.exporters` | 18 | Prometheus (text format/histogram/labels/remote), OpenTelemetry (metrics/traces), JSON, CSV (header); batch, empty, errors, metrics, health, registry, selector, chunking, encoding, roundtrip |
| `test_health_engine.py` | `observability.health_engine` | 16 | Register checks, run, aggregate, status (healthy/degraded/unhealthy), timeout, events, metrics, health, cron schedule, error handling, dependencies, details, config |
| `test_health_helpers.py` | health helpers | 18 | HealthRegistry (register/get/list/unknown/health); HeartbeatManager (start/stop/interval/stale/events/health); DiagnosticEngine (run/collect/report/error/recommendation/health); helper metrics |
| `test_integrations.py` | `observability.integrations` | 16 | Grafana (push/dashboard), Datadog (metrics/events), Azure Monitor, CloudWatch (metrics/alarms), Prometheus remote write; auth, timeout, retry, failure, metrics, health, config, async |
| `test_metric_aggregators.py` | `observability.metrics.aggregators` | 16 | Sum/avg/min/max/count/percentile/p95/histogram; empty, NaN, labels, time-window, registry, selector, composite, health |
| `test_metric_collectors.py` | `observability.metrics.collectors` | 16 | CPU/memory/disk/network/process collectors; interval, labels, schema, error, registry, selector, start/stop, batch, metrics, health, async |
| `test_metric_registry.py` | `observability.metrics.registry` | 12 | Register/get/list/duplicate/unregister/exists/labels/query/clear/count/health/events |
| `test_metrics_engine.py` | `observability.metrics.metrics_engine` | 22 | Record/collect/query/aggregate/export/alert-integration, labels, time range, bucket, empty, events, metrics, health, config, batch, error, retention, dedup, compression, rollup, thresholds |
| `test_performance.py` | `observability.performance` | 18 | Latency record/stats, throughput, percentiles, thread safety, async, metrics, health, events, cleanup, pool, queue, backpressure, timeout, cancel, error, config |
| `test_plugin.py` | `observability.plugin` | 14 | Plugin metadata/health/config, initialize/start/stop, metric/trace/alert/dashboard/export methods, MockContext, error handling, events |
| `test_statistics.py` | `observability.statistics` | 12 | Mean/median/mode/stddev/variance/min-max/quartiles/moving average/correlation/regression, empty, health |
| `test_storage.py` | `observability.storage` | 18 | File-backed storage: init, save/load metric/trace/alert, list, delete, exists, count, clear, persist, stats, corrupt file, health |
| `test_trace_engine.py` | `observability.trace_engine` | 18 | Start/end trace, add span, span hierarchy, get/list/search/export, events, metrics, health, errors, sampling, max spans/traces, retention, async |
| `test_tracing_helpers.py` | tracing helpers | 18 | TraceContext (defaults/span/parent), CorrelationManager (generate/lookup/link/root), SpanManager (start/end/child/tags/logs/active/clear), events, metrics, health, async |
| `test_trend_forecast.py` | `observability.trend_forecast` | 16 | TrendAnalyzer (direction/slope/flat/noise/window/events/metrics/health); ForecastEngine (linear/polynomial/confidence/horizon/errors/seasonal/insufficient/health) |

## 6. `tests/unit/` (75 files)

### 6.1 Core framework
| File | Subject | Count | Coverage |
|---|---|---|---|
| `test_config.py` | `config.settings` | ~16 | Defaults, env overrides, `ENVIRONMENT` mapping, `DEBUG`, MongoDB fields, secrets, roundtrips, unknown-field rejection, per-env validation, `get_settings()` caching |
| `test_event_bus.py` | `events.bus` | ~18 | Subscribe/publish/unsubscribe, wildcard `"*"`, handler error isolation, ordering, dedup, `publish_sync`, subscriber counts, clear, re-entrant publish |
| `test_exceptions.py` | `exceptions` | ~12 | `GuardianError` hierarchy: message/code/details, `to_dict`/`from_dict`, subclass codes, `__cause__` chaining, non-ASCII, deep details |
| `test_framework_config.py` | `framework.config` | ~14 | `FrameworkConfig` defaults, plugin dirs, enable flags (ml/quantum/security/observability/response/risk), event-bus/hook settings, roundtrips, validation, profile loading, per-plugin overrides |
| `test_framework_state.py` | `framework.state` | ~12 | `FrameworkState` enum + transitions INITIALIZING→RUNNING→STOPPED, invalid transitions, labels, `is_running`/`is_stopped`, serialization, thread-safe reads |
| `test_hooks.py` | `hooks` | ~18 | Hook registration/execution, async hooks, kwargs, error isolation, priority, removal, result chaining, metadata |
| `test_plugins.py` | `plugins` | ~18 | `SimplePlugin`/`AnotherPlugin`/`FailingInitPlugin` + registry: register/get/unregister/list, enable/disable, lifecycle, init-failure handling |
| `test_sdk.py` | `sdk.guardian` | 18 | `SamplePlugin`: init (default/custom config), lifecycle (start/shutdown/events), plugins (register/unregister/list/enable/disable), events delegation, adapters, hooks |
| `test_utils.py` | `utils` | 24 | `uuid_utils` (format/uniqueness, correlation id), `datetime_utils` (utc now/timestamp/iso), `json_utils` (bytes dump/roundtrip/string load), `helpers` (mask_sensitive, chunk_list + ValueError, flatten_list, none_if_empty) |

### 6.2 ML (`tests/unit/test_ml_*.py`, 12 files)
| File | Subject | Count | Coverage |
|---|---|---|---|
| `test_ml_base.py` | `ml.base` | ~12 | `DummyThreatModel` contract: name/version/train/predict/is_trained lifecycle, metadata |
| `test_ml_config_events.py` | `ml.config` + `ml.events` | ~16 | `MLConfig` defaults/validation/serialization; ML event types |
| `test_ml_data.py` | `ml.data` | ~14 | `ModelMetadata`, `TrainingMetrics`, `InferenceResult`, `Prediction` |
| `test_ml_datasets.py` | `ml.datasets` | ~16 | CSV/JSON/HuggingFace loaders, schema inference, label column, feature split, missing file, empty, validation |
| `test_ml_detectors.py` | `ml.models` | ~18 | IsolationForest/RandomForest/XGBoost detectors: train/predict, thresholds, untrained, scoring |
| `test_ml_ensemble.py` | `ml.models.ensemble` | ~14 | Hard/soft voting, weights, member failure, registration, aggregation |
| `test_ml_evaluation.py` | `ml.evaluation` | ~14 | Accuracy/precision/recall/F1, confusion matrix, CV summary, serialization |
| `test_ml_features.py` | `ml.feature_pipeline` | ~12 | Feature provider: vector building, normalization, names, empty input |
| `test_ml_inference.py` | `ml.inference` | ~14 | `InferenceEngine`: registry, single/batch, untrained handling, latency, error containment, fallback |
| `test_ml_model_manager.py` | `ml.models.model_manager` | ~16 | `ModelManager`: register/get/unregister/list, tags, best-model, save/load, health |
| `test_ml_plugin.py` | `ml.plugin` | ~14 | `ThreatAnalysisPlugin`: metadata, lifecycle, analyze/threat classification, health, events |
| `test_ml_storage.py` | `ml.storage` | ~14 | `MLStorage`: save/load/list/delete/persist/version/stats |
| `test_ml_training.py` | `ml.training` | ~16 | `ModelTrainer`, `CrossValidator`: train, k-fold CV, metrics, early stopping, insufficient data, history |

### 6.3 Policy (`tests/unit/test_policy_*.py`, 9 files)
| File | Subject | Count | Coverage |
|---|---|---|---|
| `test_policy_composition.py` | `policy.composition` | 16 | `PolicyComposer`: templates, inheritance (+overrides by field/rule/action/index), merge (override/append/interleave), variable substitution, chain + cycles, deep copy |
| `test_policy_condition_parser.py` | `policy.core.condition_parser` | 47 | Advanced DSL: comparisons (eq/neq/gt/gte/lt/lte/matches/not_matches/in/not_in/contains/starts/ends), quoted values, AND/OR/NOT, nesting, temporal (`after`/`before`), existence, parse errors |
| `test_policy_conflict_detector.py` | `policy.core.conflict_detector` | 12 | `ConflictDetector`: no-conflict, redundant, contradicting, shadowed, disabled ignored, cross-policy, internal, resolution strategy, empty, multiple |
| `test_policy_core.py` | `policy` core (enums/data/config/events/exceptions) | 66 | Operators/logical ops/condition types/statuses; `Condition` + `CompoundCondition` evaluation; `AdvancedRule`; `AdvancedPolicyDefinition`; `PolicyVersion`, `ConflictResult`, `SimulationResult`, `PolicyEvaluationResult`, `RBACPermission`, `DSLAdapterResult`; `PolicyEngineConfig`; events; exceptions |
| `test_policy_dsl_adapters.py` | `policy.adapters` | 22 | `RegoAdapter`, `CedarAdapter`, `YAMLAdapter`, `JSONAdapter`, `get_adapter`: parse/export, warnings, invalid JSON, format selection, unknown format raises |
| `test_policy_engine.py` | `policy.engine` | 38 | `AdvancedPolicyEngine`: register/evaluate, default action, activate/deactivate, list/update, simulate (+batch), conflict detection, versioning, rollback, DSL import/export, RBAC, composition, condition parsing, events, auto-conflict block, persistence, full lifecycle |
| `test_policy_evaluator.py` | `policy.core.evaluator` | 16 | `PolicyEvaluator`: no-rules default, single-rule match/no-match, priority, multiple matches, disabled skipped, compound conditions, action params, execution time, context/version in result |
| `test_policy_rbac.py` | `policy.rbac` | 15 | `RBACManager`: default role, assign/revoke, unknown role, admin/editor/viewer permissions, `require_permission`, custom roles, built-in protection, listing |
| `test_policy_registry.py` | `policy.core.registry` | 21 | `PolicyRegistry`: register/get, duplicate raises, unregister, list/by-status, list_active, activate/deactivate, update, count, clear, has, persistence |
| `test_policy_simulation.py` | `policy.core.simulation` | 14 | `SimulationEngine`: simulate, no-match, history, batch, overrides, disabled, replay, compare, metadata, context capture |
| `test_policy_storage.py` | `policy.storage` | 13 | `PolicyStorage` (tempfile): save/load, save_all/load_all, missing, delete, exists, count, clear, persist |
| `test_policy_version_manager.py` | `policy.core.version_manager` | 18 | `VersionManager`: snapshot, get_versions/get/not-found, latest, rollback, bump patch/minor/major, max-versions, count, clear, deep copies, invalid format |

### 6.4 Quantum (`tests/unit/test_quantum_*.py`, 13 files)
| File | Subject | Count | Coverage |
|---|---|---|---|
| `test_quantum_backends.py` | `quantum.backends` | 35 | Backend ABC, `LocalSimulatorBackend` + `_LocalCircuit` (h/x/y/z/rx/ry/rz/cx/cz gates), `BackendManager` (register/unregister/active/fallback/health/default) |
| `test_quantum_config_data.py` | `quantum` (enums/config/data/exceptions) | 37 | Enums (backend types, encoding, circuits, measurement, optimizers, models, statuses, fusion strategies); config classes; data models (`CircuitResult`, `QuantumCircuitInfo`, `QuantumModelMetadata`, `FusedResult`, `BackendInfo`, …); exceptions |
| `test_quantum_events.py` | `quantum.events` | 16 | Event types: backend connected/disconnected/health, circuit compiled/executed/failed, model registered/trained/prediction, inference/fusion/evaluation, feature encoded, kernel computed |
| `test_quantum_execution_plugin.py` | `quantum.execution` + `quantum.plugin` | 17 | `CircuitExecutor` (execute, counts, avg time, backend selection, health); `QuantumAnalysisPlugin` (model registry, lifecycle, config) |
| `test_quantum_feature_maps.py` | `quantum.feature_maps` | 48 | `AngleEncodingMap`, `ZZFeatureMap`, `PauliFeatureMap`: encoding, rotation gates, entanglement (linear/circular/full), depth, normalization, empty-feature errors, metadata |
| `test_quantum_inference_engine.py` | `quantum.inference.engine` | 34 | `QuantumInferenceEngine`: zero-state, registration/priority, get/select (name/auto/fallback), inference, batch, fallback on error, performance stats, history, health |
| `test_quantum_kernels.py` | `quantum.kernels` | 17 | Kernel ABC + `QuantumKernelEstimator`: evaluate, matrix symmetry/diagonal, circuit info, cache clear, health |
| `test_quantum_kernel_trainer.py` | `quantum.training.kernel_trainer` | 28 | `KernelHyperparams`; `KernelCandidate` composite score; grid/random search, train_kernel, cross_validate, info |
| `test_quantum_models_training.py` | `quantum.models` + `training` + `evaluation` | 24 | `BaseQuantumModel` contract, `QuantumTrainer` (supervised/validation/CV), `QuantumEvaluator` (evaluate/compare/empty) |
| `test_quantum_model_manager.py` | `quantum.models.manager` | 32 | Registration (tags/metadata/duplicate no-op), unregister, get, list (all/trained/type/tags), inference recording, best-model, health, save_state, clear |
| `test_quantum_phase2_events.py` | `quantum.events` | 11 | Learning lifecycle events: training started/completed/failed, prediction, model saved/loaded, version, health |
| `test_quantum_qsvm.py` | `quantum.models.qsvm` | 43 | `QSVMModel`: construction, train (binary/multiclass/errors/time), metadata, prediction (scores/probabilities), classify_quantum, save/load, health, `THREAT_CATEGORIES` |
| `test_quantum_storage.py` | `quantum.storage` | 24 | Save/load (+versions), load errors, metadata, exists, list, delete, rollback, stats |

### 6.5 Risk (`tests/unit/test_risk_*.py`, 7 files)
| File | Subject | Count | Coverage |
|---|---|---|---|
| `test_risk_actions.py` | `risk.actions` | 30 | Responders (Continue/Block/AuditLog/Alert/NotifyAdmin/Webhook), `Notifier`, `AuditTrail`, `ActionEngine` |
| `test_risk_assessment.py` | `risk.assessment` | 46 | `ThreatScorer` (weights/score/components/level/reasoning/batch), `TrustEngine` (adjust/record/decay/reset/reliability), `ConfidenceEngine` (normalize/aggregate/interval/reset), `SeverityEngine` (classify/thresholds/batch) |
| `test_risk_assessment_engine.py` | `risk.assessment.risk_engine` | 15 | `RiskAssessmentEngine`: assess (basic/high/low), sub-scores (threat/severity/confidence/trust), reasoning, sources, batch, clamping, trust read, level mapping |
| `test_risk_core.py` | `risk` (enums/data/config/exceptions/events) | 50 | Risk enums; data models (`NormalizedPrediction`, `ThreatScore`, `RiskAssessment`, `PolicyDecision`, `ReasoningGraph`, `Explanation`, …); configs (`RiskConfig`, `ScoringWeights`, `SeverityMapping`, `TrustConfig`, `ConfidenceConfig`); exceptions; events |
| `test_risk_explainability.py` | `risk.explainability` | 21 | `ReasoningGraphBuilder`, `ReportGenerator` (structured/json/markdown/text), `ExplanationEngine` (explain/action/batch/graph) |
| `test_risk_plugin_storage.py` | `risk.plugin` + `risk.storage` | 20 | `RiskAnalysisPlugin` (metadata/health/config/engines/assess/batch/stop); `RiskStorage` (dirs/save+load/audit/explanation/list/delete/stats) |
| `test_risk_policy.py` | `risk.policy` | 33 | `PolicyRegistry`, `PolicyEvaluator`, built-in policies (default/strict/permissive/quarantine), `PolicyEngine` (load defaults/evaluate/count/specific) |

### 6.6 Runtime / SDK / Security (`tests/unit/test_runtime_*.py`, `test_sdk.py`, `test_security_*.py`)
| File | Subject | Count | Coverage |
|---|---|---|---|
| `test_runtime_context.py` | `runtime.context` | 17 | `RuntimeContext`: defaults, agent/session/prompt shortcuts, blocked state, tool/memory tracking, threats, snapshot, JSON roundtrip |
| `test_runtime_events.py` | `runtime.events` | 13 | Event types (session/request/response/tool/memory/agent), serialization |
| `test_runtime_managers.py` | `runtime.managers` | 37 | `SessionManager`, `RequestManager`, `ToolExecutionTracker`, `MemoryTracker`; local fixtures; async via event-loop helpers |
| `test_runtime_models.py` | `runtime.models` + `enums` | 66 | `Agent`, `AgentSession`, `AgentRequest`, `TokenUsage`, `AgentResponse`, `ToolInvocation`, `MemoryAccess`, `SecurityContext`, `ThreatContext`, `RiskContext`, enum completeness |
| `test_runtime_sdk.py` | `sdk.guardian` runtime integration | 15 | `Guardian` runtime integration: runtime None before start, set_agent, create/close session (+events), context updates, manager access, full lifecycle |
| `test_security_decision.py` | `security.decision` | 13 | `SecurityDecisionEngine`: allow/block/review/warn matrix, mixed severity, risk score, recommendation, custom thresholds |
| `test_security_models.py` | `security` (models/config/events) | 22 | `PromptFeatures`, `PromptFinding`, `PromptRule`, `PromptAnalysis`, `PromptSecurityConfig`, security events, `DetectionResult`, enums |
| `test_security_pipeline.py` | `security.pipeline` | 42 | `PromptNormalizer` (whitespace/unicode/hidden/collapse/tabs), `PromptValidator` (valid/empty/oversized/null bytes), `PromptFeatureExtractor` (code blocks/urls/entropy/ratios), `RuleEngine` (default rules/add/remove/keyword/pattern/case) |
| `test_security_plugin.py` | `security.plugin` + `sdk.guardian` | 15 | `PromptScannerPlugin` (metadata/lifecycle/scan safe/injection/empty/health/custom config); Guardian integration (scan, block injection, events, agent+session) |

### 6.7 Fusion (`tests/unit/test_fusion_*.py`, 6 files)
| File | Subject | Count | Coverage |
|---|---|---|---|
| `test_fusion_adapters.py` | `fusion.adapters` | ~20 | Provider adapters (`RuleEngineProvider`, `ClassicalModelProvider`, `QuantumModelProvider`, `GenericProvider`): normalization, provider_id, confidence, label mapping, error fallback, batch, validity |
| `test_fusion_calibrator.py` | `fusion.calibrator` | ~14 | `FusionCalibrator`: weight calibration, recalibration, per-provider reliability, drift detection, metadata |
| `test_fusion_engine.py` | `fusion.engine` | ~20 | `FusionEngine`: fused decision, provider registration, strategy selection, fallback, confidence aggregation, risk scoring, events, history/health |
| `test_fusion_events.py` | `fusion.events` | ~14 | Fusion event types, payload fields, serialization |
| `test_fusion_prediction.py` | `fusion.prediction` | ~12 | `ThreatPrediction`/`ReasoningTrace`: fields, defaults, threat-level evaluation, reasoning, serialization |
| `test_fusion_strategies.py` | `fusion.strategies` | ~24 | `WeightedVoting`, `ConfidenceWeighted`, `Adaptive`, `Stacking`, `Bayesian`: tie-breaking, empty/single-provider, weight normalization |

### 6.8 Benchmark (`tests/unit/test_benchmark_*.py`, 5 files)
| File | Subject | Count | Coverage |
|---|---|---|---|
| `test_benchmark_registry.py` | `benchmark.registry` | 6 | `DatasetSpec` (defaults, `to_dict`), `DatasetRegistry` (builtin/get/all sorted/public/gated/public_ids, unknown → `KeyError`) |
| `test_benchmark_download.py` | `benchmark.download` | 9 | `httpx.MockTransport` HF rows pagination, gated-without-token → `DatasetError` (mentions `gated`), gated-with-token `Authorization` header, HTTP error → `DatasetError`, local jsonl/csv/json passthrough, `max_samples` cap, cache filename sanitization |
| `test_benchmark_validate.py` | `benchmark.validate` | 6 | `DatasetValidator`: row schema (JSON object), non-empty text, resolvable 0/1 label, category, `valid` flag, per-issue detail |
| `test_benchmark_preprocessing.py` | `benchmark.preprocessing` | 6 | `extract_text`/`resolve_label`/`extract_category`, string `label_map`, split-derived labels+categories, `default_label` (benign corpus), bad-row skipping, empty → `ValueError` |
| `test_benchmark_runner.py` | `benchmark.run` | 8 | End-to-end local dataset run (`k=2`, `{"quantum": False, "n_estimators": 20}`) → `BenchmarkReport` (validation + provider metrics + ranking), `run_all` over public IDs, unknown dataset → `KeyError` |

### 6.9 Embeddings (`tests/unit/test_embeddings_*.py`, 10 files)
| File | Subject | Count | Coverage |
|---|---|---|---|
| `test_embeddings_errors.py` | `embeddings.errors` | 7 | Exception hierarchy: `EmbeddingError` base + `NotLoaded`/`NotAvailable`/`ProviderError` subclasses, catchable-as-base, message preservation |
| `test_embeddings_hasher.py` | `embeddings.providers.hasher` | 22 | `hash_vector` (deterministic, dimension, L2-normalized, seed changes vector, whitespace-insensitive, empty text, cap); `HashEmbeddingProvider` lifecycle/embed/batch/metadata |
| `test_embeddings_base.py` | `embeddings.base` | 18 | `EmbeddingProvider` ABC: abstract enforcement, load-guard on `embed`/`embed_batch`, idempotent load/unload, rolling latency window, `metadata` record |
| `test_embeddings_providers.py` | `embeddings.providers` | 27 | `SentenceTransformersProvider` via fake model factory (dimension probe, batch, unload, missing-library → `EmbeddingNotAvailableError`), `_as_floats`, cloud placeholders (identity/env/dimension, load guard, unimplemented `embed`, metadata `implemented=False`) |
| `test_embeddings_cache.py` | `embeddings.manager.EmbeddingCache` | 12 | JSON disk cache: save/load roundtrip, corrupted file → empty, float coercion, `contains`, per-provider/global `clear`, `snapshot`, overwrite |
| `test_embeddings_manager.py` | `embeddings.manager` | 52 | Registration (duplicates → `EmbeddingError`, aliases, default selection, `unregister`), lazy load, embed + `embed_with_meta` (cache flags, latency), LRU eviction, stats, batching + chunking, fallback (single + batch, event/error records), disk-cache persistence across instances, `EmbeddingManager.default`, `build_manager` |
| `test_embeddings_explain.py` | `embeddings.explain` | 16 | `EmbeddingMeta` (frozen, `to_dict`/`from_dict`, `is_cache_hit`), `EmbeddingTrace` (records, unique providers/models, latency stats ignoring cached, p95, `to_dict`, clear) |
| `test_embeddings_fusion.py` | `embeddings.fusion` | 35 | `FeatureMode` (StrEnum, coercion), `ModeFeatureExtractor` (43/16/59-dim vectors, feature names, per-call mode override, handcrafted parity vs `HybridEvaluator`), `EmbeddingFeatureProvider.extract_features` per mode, `ModeHybridEvaluator` parity |
| `test_embeddings_integration.py` | `embeddings.integration` | 9 | `ModeTrainingAdapter` (matrix/names built, trainer kwargs forwarded, anomaly path), `ModeQuantumAdapter` (vector forwarding, optional labels) with injected fake trainers |
| `test_embeddings_benchmark.py` | `embeddings.benchmark` | 28 | `ModeDetectionBenchmark` (report shape per mode, evaluator kwargs, ablation, out-of-fold scores), comparison helpers (`_build_comparison`, `_recommendation`, `_fmean_or_zero`, `_stdev_or_zero`), `ModeComparisonReport` (winner/`as_dict`/`as_benchmark_reports`), `ModeComparisonRunner` end-to-end on a local dataset |

### 6.10 Evaluation (`tests/unit/test_evaluation_*.py`, 4 files)

| File | Module under test | Tests | Coverage |
|---|---|---|---|
| `test_evaluation_dataset.py` | `evaluation.dataset` | 10 | `PromptBenchmarkDataset` construction, columns, serialization |
| `test_evaluation_metrics.py` | `evaluation.metrics` | 21 | Probability-based detection metrics (AUC, precision/recall, thresholds, aggregates) |
| `test_evaluation_benchmark.py` | `evaluation.benchmark` | 6 | Cross-validation benchmark and report rendering |
| `test_evaluation_pipeline.py` | `evaluation.pipeline` | 9 | Hybrid pipeline evaluator (classical path); `save_state`/`load_state` checkpoint round-trip + `score_texts` persistence |

### 6.11 Training pipeline (`tests/unit/test_training_*.py`, 10 files)

| File | Module under test | Tests | Coverage |
|---|---|---|---|
| `test_training_schema.py` | `training.schema` | 4 | `DatasetRecord` (defaults, `to_dict`/`from_dict` round-trip, metadata) |
| `test_training_normalize.py` | `training.normalize` | 6 | `DatasetRecordPreprocessor`: label mapping, split-derived labels, `malicious` fallback category, bad-row dropping, source/category preservation |
| `test_training_config.py` | `training.config` | 11 | Defaults use registry ids; JSON file round-trip/missing → raise; token masking in `as_dict`; `evaluator_kwargs`; seed validation |
| `test_training_dedup.py` | `training.dedup` | 20 | `normalized_text` (NFKC/control-char stripping), `exact_hash`/`text_hash`, `dedup_records` (exact/normalized, keep-first/last), `detect_leakage`, `remove_leaked` |
| `test_training_splitting.py` | `training.splitting` | 12 | Seeded stratified `split_by_label`, `assign_groups` official-test routing + unlisted → external, `split_train_pool`, `cap_records` |
| `test_training_artifacts.py` | `training.artifacts` | 4 | Pretty JSON writes, label/category distributions, `write_json`/`read_splits` round-trip, missing-split skip |
| `test_training_prepare.py` | `training.prepare` | 8 | End-to-end local-dataset prepare (pools + artifacts + valid JSONL), external leakage removal, required-unavailable → raise, optional-unavailable skipped, include-only |
| `test_training_train.py` | `training.train` | 5 | Real `HybridEvaluator` fit + checkpoint + metrics, evaluator kwargs, per-class cap, no-data raise, validation threshold |
| `test_training_evaluate.py` | `training.evaluate` | 7 | Matrix (test/validation/external + `available: false` rows), threshold analysis, artifacts, empty-test skip, no-evaluator raise, per-category rows |
| `test_training_cli.py` | `cli` | 20 | Parser per subcommand, `_load_config` overrides + file, `_resolve_token`, `dataset prepare/validate`, `model train` (prepare-on-missing / reuse splits), `model evaluate` no-checkpoint exit, `benchmark` reports + defaults |

## 7. Shared Test Infrastructure

### 7.1 Module-level helper factories (`_`-prefixed)
`_policy(...)` (policy tests), `_rule(...)` (conflict detector), `_make_policy(...)` (evaluator/registry), `_policy_with_rules()` (simulation), `_make_decision(...)`/`_make_assessment(...)` (risk actions), `_make_prediction(...)` (risk), `_make_finding(...)` (security decision), `_pred(...)`/`_invalid_pred(...)` (fusion), `_make_features(...)`/`_make_training_data(...)` (ml detectors), `_make_request(...)` (response engine), `_make_metric(...)` (exporters), `_step(...)`/`_playbook(...)` (orchestration), `_init_*_engine(...)` (performance).

### 7.2 Stub classes
`DummyQuantumBackend`, `DummyFeatureMap`, `DummyKernel`, `DummyQuantumModel`, `SimpleQuantumModel`, `DummyThreatModel`, `DummyModel`, `DummySklearnModel`, `SimplePlugin`/`AnotherPlugin`/`FailingInitPlugin`, `SamplePlugin`, `LifecycleTrackerPlugin`, `ConcreteEvent`, `SimpleProvider`/`FailingProvider`, `MockContext`, `RuleEngineProvider`/`ClassicalModelProvider`/`QuantumModelProvider`/`GenericProvider`.

### 7.3 Module-scope fixtures
Defined in `test_quantum_inference_engine.py` (`backend`, `feature_map`, `kernel`, `engine`, `trained_qsvm`, `trained_qsvm2`), `test_quantum_kernel_trainer.py`, `test_quantum_model_manager.py`, `test_quantum_qsvm.py` (`sample_data`, `multiclass_data`), `test_quantum_storage.py`, `test_observability/test_storage.py` (`storage_root`, `storage`, `sample_metric`, …), `test_runtime_managers.py`, `test_event_bus.py`.

## 8. Totals & Counts (whole suite)

| Metric | Count |
|---|---|
| Total test functions | **2,650** |
| — synchronous (`def test_`) | 2,415 |
| — asynchronous (`async def test_`) | 235 |
| `@pytest.mark.asyncio` | 160 |
| `@pytest.fixture` definitions (incl. conftest) | 53 |
| `@pytest_asyncio.fixture` definitions | 3 |
| `@pytest.mark.parametrize` | 0 |
| `@pytest.mark.unit`/`integration`/`slow` | 0 |
| `@pytest.mark.skip`/`xfail` | 0 |

## 9. Coverage Representation Notes

- **Most extensively tested:** observability (~390 tests), quantum (13 files, ~320 tests), policy (9 files, ~240 tests), risk (7 files, ~220 tests).
- **Least directly represented:** `api.app` (only integration `test_api.py`), `hooks` (single file), `utils` (single file), `config.settings` (via fixture + `test_config.py`).
- Classification is **by directory**, not pytest markers (the `unit`/`integration`/`slow` markers declared in `pyproject.toml` are unused).
- Async tests rely on explicit `@pytest.mark.asyncio`; `anyio_backend` fixtures return `"asyncio"`.

## 10. Source-Coverage Cross-Reference

See `18_Tests_Scripts_Examples_Documentation.md` §1–§3 for test counts and per-file inventory, and `03_Source_File_Documentation.md` for the production modules these tests exercise.
