# 01. Project Structure — Q-Gaudrail

> **Document index:** this is document 01 of the Q-Gaudrail technical documentation set. See `00_Project_Overview.md` for the index.

## 1. Repository Layout

The repository uses a **src layout**: the installable package lives under `src/q_guardian/`, tests live under `tests/`, tooling under `scripts/`, and runnable demos under `examples/`.

```
Q_Gaudrail/
├── .github/workflows/        CI, release, and benchmark GitHub Actions
├── docker/                   Container build files
├── docs/                     Markdown guides (17 user guides + this 00–18 set)
├── examples/                 Runnable examples + generated state artifacts
├── logs/                     Runtime log directory (q_guardian.log, effectively empty)
├── models/ml/                ML artifact directory (present, effectively empty)
├── scripts/                  Benchmarks, load testing, packaging, profiling, CLIs
├── src/q_guardian/           The q_guardian package (all production code)
├── tests/                    pytest suite (unit, response, observability, integration)
├── pyproject.toml            Build system, dependencies, project metadata
├── requirements.txt          Pin file (with the extras)
├── docker-compose.yml        Local compose service definitions
├── Makefile                  Dev task runner
├── .env.example              Environment variable template
└── *.md, LICENSE*            Community and project files
```

## 2. Full Folder Tree

The tree below covers every tracked project file (the 490 non-cache files in the canonical inventory; `.pytest_cache/` contents and `__pycache__`/`*.pyc` build artifacts are excluded).

```
Q_Gaudrail/
├── .dockerignore
├── .env.example
├── .github/
│   └── workflows/
│       ├── benchmark.yml
│       ├── ci.yml
│       └── release.yml
├── .gitignore
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── docker/
│   └── Dockerfile
├── docker-compose.yml
├── docs/
│   ├── api-reference.md
│   ├── architecture-guide.md
│   ├── configuration-guide.md
│   ├── deployment-guide.md
│   ├── developer-guide.md
│   ├── event-system.md
│   ├── framework-architecture.md
│   ├── migration-guide.md
│   ├── ml-security.md
│   ├── operations-guide.md
│   ├── plugin-development.md
│   ├── plugin-dev-guide.md
│   ├── quantum-analysis-research.md
│   ├── runtime-architecture.md
│   ├── security-review.md
│   ├── troubleshooting-guide.md
│   └── user-guide.md
├── examples/
│   ├── crewai/
│   │   └── crewai_example.py
│   ├── google_adk/
│   │   └── google_adk_example.py
│   ├── hybrid_multiagent/
│   │   └── hybrid_multiagent_example.py
│   ├── langgraph/
│   │   └── langgraph_example.py
│   ├── openai_agents/
│   │   └── openai_agents_example.py
│   ├── semantic_kernel/
│   │   └── semantic_kernel_example.py
│   ├── prompt_test_harness.py
│   ├── qg_memory.jsonl
│   └── qg_state/
│       ├── anomaly.pkl
│       ├── corpus.json
│       ├── qsvm.json
│       ├── rf.pkl
│       └── scaler.pkl
├── LICENSE
├── LICENSE_PENDING.md
├── logs/
│   └── q_guardian.log
├── Makefile
├── pyproject.toml
├── README.md
├── requirements.txt
├── scripts/
│   ├── __init__.py
│   ├── benchmarks/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── benchmark_runner.py
│   │   ├── benchmarks.py
│   │   └── run_benchmarks.py
│   ├── loadtest/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── load_tester.py
│   │   ├── reporter.py
│   │   ├── results/                 # generated load-test reports
│   │   │   ├── burst_20260719_035126.json
│   │   │   ├── mixed_workload_20260719_035125.json
│   │   │   ├── prompt_scan_20260719_035029.json
│   │   │   ├── prompt_scan_20260719_035112.json
│   │   │   ├── prompt_scan_20260719_035123.json
│   │   │   └── session_lifecycle_20260719_035124.json
│   │   ├── run_loadtest.py
│   │   └── scenarios.py
│   ├── packaging/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── build.py
│   │   └── validate.py
│   ├── profile/
│   │   ├── __init__.py
│   │   ├── memory_profiler.py
│   │   ├── optimization_report.py
│   │   └── run_profiler.py
│   ├── prompt_cli.py
│   └── train_data.py
├── SECURITY.md
├── src/
│   ├── __init__.py
│   └── q_guardian/
│       ├── __init__.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── autogen.py
│       │   ├── base.py
│       │   ├── crewai.py
│       │   ├── generic.py
│       │   ├── google_adk.py
│       │   ├── langgraph.py
│       │   ├── openai_agents.py
│       │   └── semantic_kernel.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py
│       │   └── v1/
│       │       ├── __init__.py
│       │       ├── router.py
│       │       └── endpoints/
│       │           ├── __init__.py
│       │           ├── health.py
│       │           └── system.py
│       ├── benchmark/
│       │   ├── __init__.py
│       │   ├── download.py
│       │   ├── metrics.py
│       │   ├── preprocessing.py
│       │   ├── registry.py
│       │   ├── report.py
│       │   ├── run.py
│       │   └── validate.py
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── constants.py
│       │   └── framework_state.py
│       ├── database/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   └── health.py
│       ├── dependencies/
│       │   ├── __init__.py
│       │   └── container.py
│       ├── embeddings/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── benchmark.py
│       │   ├── errors.py
│       │   ├── explain.py
│       │   ├── fusion.py
│       │   ├── integration.py
│       │   ├── manager.py
│       │   └── providers/
│       │       ├── __init__.py
│       │       ├── cloud.py
│       │       ├── hasher.py
│       │       └── sentence_transformers.py
│       ├── events/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── bus.py
│       │   └── standard.py
│       ├── evaluation/
│       │   ├── __init__.py
│       │   ├── benchmark.py
│       │   ├── dataset.py
│       │   ├── metrics.py
│       │   ├── pipeline.py
│       │   └── report.py
│       ├── exceptions/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── handlers.py
│       ├── framework/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── context.py
│       ├── hooks/
│       │   ├── __init__.py
│       │   └── manager.py
│       ├── logging/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── middleware.py
│       ├── main.py
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── correlation.py
│       │   ├── exception.py
│       │   └── timing.py
│       ├── ml/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── config.py
│       │   ├── data.py
│       │   ├── datasets/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── csv_loader.py
│       │   │   ├── huggingface_loader.py
│       │   │   └── json_loader.py
│       │   ├── enums.py
│       │   ├── evaluation/
│       │   │   ├── __init__.py
│       │   │   └── metrics.py
│       │   ├── events.py
│       │   ├── feature_pipeline.py
│       │   ├── inference/
│       │   │   ├── __init__.py
│       │   │   └── engine.py
│       │   ├── models/
│       │   │   ├── __init__.py
│       │   │   ├── anomaly.py
│       │   │   ├── classifier.py
│       │   │   ├── ensemble.py
│       │   │   └── model_manager.py
│       │   ├── plugin.py
│       │   ├── storage.py
│       │   └── training/
│       │       ├── __init__.py
│       │       └── trainer.py
│       ├── models/
│       │   ├── __init__.py
│       │   └── base.py
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── alerts/
│       │   │   ├── __init__.py
│       │   │   ├── alert_engine.py
│       │   │   ├── alert_rules.py
│       │   │   ├── escalation.py
│       │   │   ├── notifier.py
│       │   │   └── routing.py
│       │   ├── analytics/
│       │   │   ├── __init__.py
│       │   │   ├── analytics_engine.py
│       │   │   ├── forecasting.py
│       │   │   ├── reports.py
│       │   │   ├── statistics.py
│       │   │   └── trend_analysis.py
│       │   ├── config.py
│       │   ├── dashboard/
│       │   │   ├── __init__.py
│       │   │   ├── api.py
│       │   │   ├── dto.py
│       │   │   ├── endpoints.py
│       │   │   ├── filters.py
│       │   │   └── serializers.py
│       │   ├── data.py
│       │   ├── enums.py
│       │   ├── events.py
│       │   ├── exceptions.py
│       │   ├── exporters/
│       │   │   ├── __init__.py
│       │   │   ├── csv.py
│       │   │   ├── json.py
│       │   │   ├── opentelemetry.py
│       │   │   └── prometheus.py
│       │   ├── health/
│       │   │   ├── __init__.py
│       │   │   ├── diagnostics.py
│       │   │   ├── health_checks.py
│       │   │   ├── health_engine.py
│       │   │   ├── health_registry.py
│       │   │   └── heartbeat.py
│       │   ├── integrations/
│       │   │   ├── __init__.py
│       │   │   ├── azure_monitor.py
│       │   │   ├── cloudwatch.py
│       │   │   ├── datadog.py
│       │   │   ├── grafana.py
│       │   │   └── prometheus.py
│       │   ├── metrics/
│       │   │   ├── __init__.py
│       │   │   ├── aggregators.py
│       │   │   ├── collectors.py
│       │   │   ├── exporters.py
│       │   │   ├── metrics_engine.py
│       │   │   └── registry.py
│       │   ├── plugin.py
│       │   ├── storage.py
│       │   └── tracing/
│       │       ├── __init__.py
│       │       ├── context.py
│       │       ├── correlation.py
│       │       ├── exporters.py
│       │       ├── span.py
│       │       └── trace_engine.py
│       ├── plugins/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── registry.py
│       ├── policy/
│       │   ├── __init__.py
│       │   ├── adapters/
│       │   │   └── __init__.py
│       │   ├── composition/
│       │   │   └── __init__.py
│       │   ├── config.py
│       │   ├── core/
│       │   │   ├── __init__.py
│       │   │   ├── condition_parser.py
│       │   │   ├── conflict_detector.py
│       │   │   ├── evaluator.py
│       │   │   ├── registry.py
│       │   │   ├── simulation.py
│       │   │   └── version_manager.py
│       │   ├── data.py
│       │   ├── engine.py
│       │   ├── enums.py
│       │   ├── events.py
│       │   ├── exceptions.py
│       │   ├── rbac/
│       │   │   └── __init__.py
│       │   └── storage/
│       │       └── __init__.py
│       ├── quantum/
│       │   ├── __init__.py
│       │   ├── backends/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── manager.py
│       │   │   ├── qiskit_backend.py
│       │   │   └── simulator.py
│       │   ├── base/
│       │   │   └── __init__.py
│       │   ├── config.py
│       │   ├── data.py
│       │   ├── enums.py
│       │   ├── evaluation/
│       │   │   ├── __init__.py
│       │   │   └── metrics.py
│       │   ├── events.py
│       │   ├── exceptions.py
│       │   ├── execution/
│       │   │   ├── __init__.py
│       │   │   └── executor.py
│       │   ├── feature_maps/
│       │   │   ├── __init__.py
│       │   │   ├── angle_encoding.py
│       │   │   ├── base.py
│       │   │   ├── pauli_feature_map.py
│       │   │   └── zz_feature_map.py
│       │   ├── fusion/
│       │   │   ├── __init__.py
│       │   │   ├── adapters.py
│       │   │   ├── calibrator.py
│       │   │   ├── engine.py
│       │   │   ├── prediction.py
│       │   │   ├── providers.py
│       │   │   └── strategies/
│       │   │       ├── __init__.py
│       │   │       ├── adaptive.py
│       │   │       ├── base.py
│       │   │       ├── bayesian.py
│       │   │       ├── confidence.py
│       │   │       ├── stacking.py
│       │   │       └── weighted_voting.py
│       │   ├── inference/
│       │   │   ├── __init__.py
│       │   │   └── engine.py
│       │   ├── kernels/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   └── quantum_kernel.py
│       │   ├── models/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── manager.py
│       │   │   └── qsvm.py
│       │   ├── plugin.py
│       │   ├── storage.py
│       │   └── training/
│       │       ├── __init__.py
│       │       ├── kernel_trainer.py
│       │       └── trainer.py
│       ├── repositories/
│       │   ├── __init__.py
│       │   └── base.py
│       ├── response/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── data.py
│       │   ├── engine/
│       │   │   ├── __init__.py
│       │   │   ├── approval_engine.py
│       │   │   ├── orchestration_engine.py
│       │   │   ├── recovery_engine.py
│       │   │   ├── response_engine.py
│       │   │   └── rollback_engine.py
│       │   ├── enums.py
│       │   ├── events.py
│       │   ├── evidence/
│       │   │   ├── __init__.py
│       │   │   ├── collector.py
│       │   │   ├── snapshot.py
│       │   │   └── timeline.py
│       │   ├── exceptions.py
│       │   ├── integrations/
│       │   │   ├── __init__.py
│       │   │   ├── cortex.py
│       │   │   ├── qradar.py
│       │   │   ├── sentinel.py
│       │   │   ├── servicenow.py
│       │   │   └── splunk.py
│       │   ├── notifications/
│       │   │   ├── __init__.py
│       │   │   ├── email.py
│       │   │   ├── notifier.py
│       │   │   ├── slack.py
│       │   │   ├── teams.py
│       │   │   └── webhook.py
│       │   ├── playbooks/
│       │   │   ├── __init__.py
│       │   │   ├── executor.py
│       │   │   ├── parser.py
│       │   │   ├── registry.py
│       │   │   ├── templates.py
│       │   │   └── validator.py
│       │   ├── plugin.py
│       │   ├── quarantine/
│       │   │   ├── __init__.py
│       │   │   ├── agent.py
│       │   │   ├── memory.py
│       │   │   ├── plugin.py
│       │   │   ├── quarantine_manager.py
│       │   │   └── session.py
│       │   └── storage.py
│       ├── risk/
│       │   ├── __init__.py
│       │   ├── actions/
│       │   │   ├── __init__.py
│       │   │   ├── action_engine.py
│       │   │   ├── audit.py
│       │   │   ├── notifier.py
│       │   │   └── responders.py
│       │   ├── assessment/
│       │   │   ├── __init__.py
│       │   │   ├── confidence_engine.py
│       │   │   ├── risk_engine.py
│       │   │   ├── severity_engine.py
│       │   │   ├── threat_scorer.py
│       │   │   └── trust_engine.py
│       │   ├── config.py
│       │   ├── data.py
│       │   ├── enums.py
│       │   ├── events.py
│       │   ├── exceptions.py
│       │   ├── explainability/
│       │   │   ├── __init__.py
│       │   │   ├── explanation_engine.py
│       │   │   ├── reasoning_graph.py
│       │   │   └── report_generator.py
│       │   ├── plugin.py
│       │   ├── policy/
│       │   │   ├── __init__.py
│       │   │   ├── evaluator.py
│       │   │   ├── policies.py
│       │   │   ├── policy_engine.py
│       │   │   └── policy_registry.py
│       │   └── storage.py
│       ├── runtime/
│       │   ├── __init__.py
│       │   ├── context.py
│       │   ├── enums.py
│       │   ├── events.py
│       │   ├── managers.py
│       │   └── models.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── base.py
│       ├── sdk/
│       │   ├── __init__.py
│       │   └── guardian.py
│       ├── security/
│       │   ├── __init__.py
│       │   ├── auth.py
│       │   ├── config.py
│       │   ├── cors.py
│       │   ├── decision.py
│       │   ├── enums.py
│       │   ├── events.py
│       │   ├── extensibility.py
│       │   ├── headers.py
│       │   ├── models.py
│       │   ├── pipeline.py
│       │   └── plugin.py
│       ├── services/
│       │   ├── __init__.py
│       │   └── base.py
│       └── utils/
│           ├── __init__.py
│           ├── datetime_utils.py
│           ├── env_utils.py
│           ├── helpers.py
│           ├── json_utils.py
│           └── uuid_utils.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── __init__.py
    │   └── conftest.py
    ├── integration/
    │   ├── __init__.py
    │   ├── test_api.py
    │   └── test_framework_lifecycle.py
    ├── observability/
    │   ├── __init__.py
    │   └── test_*.py (24 files)
    ├── response/
    │   ├── __init__.py
    │   └── test_*.py (9 files)
    └── unit/
        ├── __init__.py
        └── test_*.py (70 files)
```

## 3. Package (`q_guardian`) Module Map

The package is organized into 12 top-level capability domains plus infrastructure:

| Domain | Path | Purpose |
|---|---|---|
| Adapters | `src/q_guardian/adapters/` | Integrations for agent frameworks (AutoGen, CrewAI, LangGraph, Google ADK, OpenAI Agents, Semantic Kernel, generic) |
| API | `src/q_guardian/api/` | FastAPI application, v1 router, endpoints |
| Benchmark | `src/q_guardian/benchmark/` | Third-party benchmark platform (registry, download, validation, preprocessing, runner, reports) |
| Config | `src/q_guardian/config/` | Settings (pydantic-settings) |
| Core | `src/q_guardian/core/` | Constants + framework state |
| Database | `src/q_guardian/database/` | MongoDB client + health |
| Embeddings | `src/q_guardian/embeddings/` | Embedding providers, caching manager, mode fusion, explainability |
| Events | `src/q_guardian/events/` | Event bus, base/standard events |
| Evaluation | `src/q_guardian/evaluation/` | Detection evaluation harness (datasets, metrics, hybrid evaluator, K-fold benchmark, reporting) |
| Exceptions | `src/q_guardian/exceptions/` | Exception hierarchy + handlers |
| Framework | `src/q_guardian/framework/` | Framework config + context |
| Hooks / Plugins | `src/q_guardian/hooks/`, `plugins/` | Hook manager, plugin base + registry |
| Logging / Middleware | `src/q_guardian/logging/`, `middleware/` | Structured logging, ASGI middleware |
| ML | `src/q_guardian/ml/` | Classical ML (models, datasets, feature pipeline, training, inference) |
| Models / Repositories | `src/q_guardian/models/`, `repositories/` | Base models + repository abstraction |
| Observability | `src/q_guardian/observability/` | Metrics, tracing, health, analytics, alerts, dashboard, exporters, integrations |
| Policy | `src/q_guardian/policy/` | Policy engine, DSL adapters, RBAC, composition, core evaluators |
| Quantum | `src/q_guardian/quantum/` | Qiskit backends, feature maps, kernels, QSVM, fusion strategies, training |
| Response | `src/q_guardian/response/` | Response/orchestration/recovery/rollback/approval engines, playbooks, quarantine, integrations |
| Risk | `src/q_guardian/risk/` | Risk assessment, severity/confidence/trust engines, explainability, actions |
| Runtime | `src/q_guardian/runtime/` | Runtime models, context, managers, events |
| SDK | `src/q_guardian/sdk/` | `Guardian` public SDK |
| Security | `src/q_guardian/security/` | Security pipeline, decision engine, auth, headers, CORS |
| Utils | `src/q_guardian/utils/` | datetime/env/helpers/json/uuid utilities |

## 4. Directory Counts (files per top-level directory)

| Directory | Non-`.pyc` files |
|---|---|
| `src/q_guardian/` | 326 Python files (306 pre-existing + 8 `benchmark/` + 12 `embeddings/` files) |
| `tests/` | 131 files (123 `test_*.py` + 6 `__init__.py` + 2 conftest) |
| `scripts/` | 29 files (23 `.py` + 6 `.json`) |
| `examples/` | 13 files |
| `docs/` | 38 `.md` files (17 pre-existing guides + 00-20 numbered docs, incl. `19_Benchmark_Platform_Documentation.md` + `20_Embedding_Pipeline.md`) |
| root files | 14 |
| `.github/workflows/` | 3 |
| `docker/` | 1 |
| `logs/` | 1 (effectively empty) |
| **Total (canonical inventory)** | **544** (excluding `.pytest_cache/`) |

## 5. File Inventory Notes

- The canonical inventory file used to validate "every project file documented exactly once" contains **541 entries**; the extra 5 are the `.pytest_cache/` artifacts (`v/cache/*`, `CACHEDIR.TAG`, etc.) which are test-runner caches and are excluded from per-file documentation.
- `models/ml/` appears in tree generation only if present; it contains no files.
- `src/__init__.py` exists as a marker for the src-layout root.
- `policy/adapters/`, `policy/composition/`, `policy/rbac/`, `policy/storage/`, `quantum/base/`, `sdk/`, `schemas/` contain their primary logic in single modules or `__init__.py` files (see `03_Source_File_Documentation.md`).

## 6. Appendix — Validation Method

- File inventory produced by recursively listing `D:\Projects\Quantum\Q_Gaudrail`, excluding `.git`, `__pycache__`, and `*.pyc`.
- Counts verified against the file inventory in `00_Project_Overview.md` §6.
- Per-file documentation coverage is tracked across `03_Source_File_Documentation.md`, `04_Configuration_File_Documentation.md`, `05_Test_File_Documentation.md`, and the module guides (`12`–`18`).
