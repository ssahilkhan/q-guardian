# 03. Source File Documentation — Q-Gaudrail

> **Document index:** this is document 03 of the Q-Gaudrail technical documentation set.
>
> **Coverage:** every source file under `src/` (301 files: `src/__init__.py` + 300 files in `src/q_guardian/`), one entry each. This is the canonical per-file documentation; every file is documented exactly once across this document set.
>
> **Format:** each entry is `path — short description`. Paths are relative to `src/`.

## 1. Package Root

- `__init__.py` — marker for the src-layout root; makes `src` importable as a namespace root.

## 2. `q_guardian/` (package root)

- `q_guardian/__init__.py` — public SDK re-export surface: `Guardian`, `EventBus`, plugin classes (`Plugin`, `Registry`), `HookManager`, `Adapter`, framework objects (`FrameworkConfig`, `FrameworkContext`, `FrameworkState`), plus runtime, security, ml, quantum, policy, risk, response, and observability exports.

## 3. `q_guardian/adapters/` — agent framework adapters

- `adapters/__init__.py` — adapter package exports.
- `adapters/base.py` — abstract `Adapter` base class defining the adapter contract for agent frameworks.
- `adapters/generic.py` — generic adapter implementation for arbitrary agents.
- `adapters/autogen.py` — Microsoft AutoGen adapter.
- `adapters/crewai.py` — CrewAI adapter.
- `adapters/google_adk.py` — Google Agent Development Kit (ADK) adapter.
- `adapters/langgraph.py` — LangGraph adapter.
- `adapters/openai_agents.py` — OpenAI Agents SDK adapter.
- `adapters/semantic_kernel.py` — Microsoft Semantic Kernel adapter.

## 4. `q_guardian/api/` — HTTP service

- `api/__init__.py` — api package marker/exports.
- `api/app.py` — FastAPI application factory `create_app()`; lifespan (logging config, Mongo connect via `database/client.py`, shutdown disconnect); mounts v1 router and middleware (CorrelationID, ExceptionLogging, ResponseTiming, SecurityHeaders, TrustedHost, CORS).
- `api/v1/__init__.py` — v1 package marker.
- `api/v1/router.py` — `v1` APIRouter; registers endpoints; currently exposes `/health` and `/system`.
- `api/v1/endpoints/__init__.py` — endpoints package marker.
- `api/v1/endpoints/health.py` — `GET /health` liveness + database health endpoint.
- `api/v1/endpoints/system.py` — `GET /system/version` and `GET /system/status` endpoints.

## 5. `q_guardian/config/`

- `config/__init__.py` — config package marker/exports.
- `config/settings.py` — pydantic-settings composite settings; `get_settings()` returns the application settings object (env-driven).

## 6. `q_guardian/core/`

- `core/__init__.py` — core package marker/exports.
- `core/constants.py` — shared project constants.
- `core/framework_state.py` — framework lifecycle state enum/model (`INITIALIZING`, `RUNNING`, `STOPPED`, etc.).

## 7. `q_guardian/database/`

- `database/__init__.py` — database package marker.
- `database/client.py` — MongoDB client management (motor/pymongo); connect/disconnect lifecycle used by the app lifespan.
- `database/health.py` — database health check helper (used by `/health` endpoint).

## 8. `q_guardian/dependencies/`

- `dependencies/__init__.py` — dependencies package marker.
- `dependencies/container.py` — dependency-injection container wiring.

## 9. `q_guardian/events/`

- `events/__init__.py` — events package exports (`EventBus`, base/standard events).
- `events/base.py` — base event class (`DomainEvent`-style) with id, timestamp, and payload fields.
- `events/bus.py` — synchronous `EventBus` implementation: subscribe/publish/dispatch.
- `events/standard.py` — standard framework events (`framework.started`, `framework.stopped`, etc.).

## 10. `q_guardian/exceptions/`

- `exceptions/__init__.py` — exception exports.
- `exceptions/base.py` — base exception hierarchy for the project.
- `exceptions/handlers.py` — exception handlers (e.g. FastAPI/ASGI handler mapping).

## 11. `q_guardian/framework/`

- `framework/__init__.py` — framework package exports.
- `framework/config.py` — `FrameworkConfig` configuration object.
- `framework/context.py` — `FrameworkContext` execution context passed through the framework.

## 12. `q_guardian/hooks/`

- `hooks/__init__.py` — hooks package exports.
- `hooks/manager.py` — `HookManager`: register/fire lifecycle and interception hooks.

## 13. `q_guardian/logging/`

- `logging/__init__.py` — logging package exports.
- `logging/config.py` — structlog configuration (setup_logging-style).
- `logging/middleware.py` — ASGI logging middleware.

## 14. `q_guardian/main.py`

- `main.py` — CLI/service entry point; calls `create_app()` from `api/app.py`.

## 15. `q_guardian/middleware/`

- `middleware/__init__.py` — middleware exports.
- `middleware/correlation.py` — correlation-ID middleware (generates/reads `X-Correlation-ID`).
- `middleware/exception.py` — exception-logging middleware.
- `middleware/timing.py` — response-timing middleware.
- **Note:** `SecurityHeaders`, `TrustedHost`, and `CORS` middleware are in `security/`.

## 16. `q_guardian/ml/` — classical ML

- `ml/__init__.py` — ml package exports.
- `ml/base.py` — ML base classes (model base, pipeline base).
- `ml/config.py` — ML configuration.
- `ml/data.py` — ML data container/structures.
- `ml/enums.py` — ML enums (task types, model types, etc.).
- `ml/events.py` — ML domain events.
- `ml/feature_pipeline.py` — feature extraction/normalization pipeline for ML.
- `ml/plugin.py` — ML plugin integration.
- `ml/storage.py` — ML model storage (persistence of artifacts).
- `ml/datasets/__init__.py` — datasets package marker.
- `ml/datasets/base.py` — dataset loader base.
- `ml/datasets/csv_loader.py` — CSV dataset loader.
- `ml/datasets/json_loader.py` — JSON dataset loader.
- `ml/datasets/huggingface_loader.py` — Hugging Face datasets loader.
- `ml/evaluation/__init__.py` — evaluation package marker.
- `ml/evaluation/metrics.py` — ML evaluation metrics (precision/recall/F1/accuracy, etc.).
- `ml/inference/__init__.py` — inference package marker.
- `ml/inference/engine.py` — model inference engine.
- `ml/models/__init__.py` — models package marker.
- `ml/models/anomaly.py` — anomaly-detection model.
- `ml/models/classifier.py` — classifier model.
- `ml/models/ensemble.py` — ensemble model.
- `ml/models/model_manager.py` — model registry/lifecycle manager.
- `ml/training/__init__.py` — training package marker.
- `ml/training/trainer.py` — model training orchestrator.

## 17. `q_guardian/models/`

- `models/__init__.py` — models package marker.
- `models/base.py` — base Pydantic model classes for domain entities.

## 18. `q_guardian/observability/` — observability

- `observability/__init__.py` — observability package exports.
- `observability/config.py` — observability configuration.
- `observability/data.py` — observability data structures (403 lines).
- `observability/enums.py` — observability enums.
- `observability/events.py` — observability domain events.
- `observability/exceptions.py` — observability exception types.
- `observability/plugin.py` — observability plugin integration.
- `observability/storage.py` — observability storage (persistence of telemetry).
- `observability/alerts/__init__.py` — alerts package marker.
- `observability/alerts/alert_engine.py` — alert evaluation/dispatch engine.
- `observability/alerts/alert_rules.py` — alert rule definitions.
- `observability/alerts/escalation.py` — alert escalation policy.
- `observability/alerts/notifier.py` — alert notifier.
- `observability/alerts/routing.py` — alert routing logic.
- `observability/analytics/__init__.py` — analytics package marker.
- `observability/analytics/analytics_engine.py` — analytics engine (376 lines).
- `observability/analytics/forecasting.py` — forecasting models.
- `observability/analytics/reports.py` — analytics report generation.
- `observability/analytics/statistics.py` — descriptive statistics helpers.
- `observability/analytics/trend_analysis.py` — trend analysis.
- `observability/dashboard/__init__.py` — dashboard package marker.
- `observability/dashboard/api.py` — dashboard API implementation (387 lines).
- `observability/dashboard/dto.py` — dashboard DTOs.
- `observability/dashboard/endpoints.py` — dashboard endpoint definitions.
- `observability/dashboard/filters.py` — dashboard query filters.
- `observability/dashboard/serializers.py` — dashboard serializers.
- `observability/exporters/__init__.py` — exporters package marker.
- `observability/exporters/csv.py` — CSV telemetry exporter.
- `observability/exporters/json.py` — JSON telemetry exporter.
- `observability/exporters/opentelemetry.py` — OpenTelemetry exporter (417 lines).
- `observability/exporters/prometheus.py` — Prometheus exporter.
- `observability/health/__init__.py` — health package marker.
- `observability/health/diagnostics.py` — system diagnostics.
- `observability/health/health_checks.py` — individual health checks.
- `observability/health/health_engine.py` — health evaluation engine.
- `observability/health/health_registry.py` — health check registry.
- `observability/health/heartbeat.py` — heartbeat reporting.
- `observability/integrations/__init__.py` — integrations package marker.
- `observability/integrations/azure_monitor.py` — Azure Monitor integration.
- `observability/integrations/cloudwatch.py` — AWS CloudWatch integration.
- `observability/integrations/datadog.py` — Datadog integration.
- `observability/integrations/grafana.py` — Grafana integration.
- `observability/integrations/prometheus.py` — Prometheus integration (346 lines).
- `observability/metrics/__init__.py` — metrics package marker.
- `observability/metrics/aggregators.py` — metric aggregation.
- `observability/metrics/collectors.py` — metric collection from components.
- `observability/metrics/exporters.py` — metric exporters.
- `observability/metrics/metrics_engine.py` — metrics engine.
- `observability/metrics/registry.py` — metric registry.
- `observability/tracing/__init__.py` — tracing package marker.
- `observability/tracing/context.py` — trace context propagation.
- `observability/tracing/correlation.py` — trace-to-correlation binding.
- `observability/tracing/exporters.py` — trace exporters.
- `observability/tracing/span.py` — span data model.
- `observability/tracing/trace_engine.py` — tracing engine.

## 19. `q_guardian/plugins/`

- `plugins/__init__.py` — plugins package exports.
- `plugins/base.py` — `Plugin` base class (initialize/start/stop lifecycle).
- `plugins/registry.py` — `Registry` of plugins.

## 20. `q_guardian/policy/` — policy engine

- `policy/__init__.py` — policy package exports.
- `policy/config.py` — policy engine configuration.
- `policy/data.py` — policy data structures.
- `policy/engine.py` — `AdvancedPolicyEngine` (330 lines): evaluate/compose/simulate/detect conflicts/version.
- `policy/enums.py` — policy enums.
- `policy/events.py` — policy domain events.
- `policy/exceptions.py` — policy exception types.
- `policy/adapters/__init__.py` — DSL adapters module (466 lines): Rego, Cedar, YAML, JSON policy DSL adapters.
- `policy/composition/__init__.py` — policy composition (161 lines).
- `policy/rbac/__init__.py` — role-based access control (83 lines).
- `policy/storage/__init__.py` — policy storage abstraction (58 lines).
- `policy/core/__init__.py` — core package marker.
- `policy/core/condition_parser.py` — condition parser (303 lines).
- `policy/core/conflict_detector.py` — conflict detection between policies.
- `policy/core/evaluator.py` — policy condition evaluator.
- `policy/core/registry.py` — policy registry.
- `policy/core/simulation.py` — policy simulation ("what-if").
- `policy/core/version_manager.py` — policy versioning.

## 21. `q_guardian/quantum/` — quantum ML

- `quantum/__init__.py` — quantum package exports.
- `quantum/config.py` — quantum configuration.
- `quantum/data.py` — quantum data structures.
- `quantum/enums.py` — quantum enums.
- `quantum/events.py` — quantum domain events.
- `quantum/exceptions.py` — quantum exception types.
- `quantum/plugin.py` — quantum plugin integration.
- `quantum/storage.py` — quantum model storage.
- `quantum/base/__init__.py` — base package (3 lines; marker).
- `quantum/backends/__init__.py` — backends package marker.
- `quantum/backends/base.py` — backend abstraction.
- `quantum/backends/manager.py` — backend manager.
- `quantum/backends/qiskit_backend.py` — Qiskit backend adapter.
- `quantum/backends/simulator.py` — local simulator backend.
- `quantum/evaluation/__init__.py` — evaluation package marker.
- `quantum/evaluation/metrics.py` — quantum model evaluation metrics.
- `quantum/execution/__init__.py` — execution package marker.
- `quantum/execution/executor.py` — circuit/model execution executor.
- `quantum/feature_maps/__init__.py` — feature maps package marker.
- `quantum/feature_maps/base.py` — feature map base.
- `quantum/feature_maps/angle_encoding.py` — angle-encoding feature map.
- `quantum/feature_maps/pauli_feature_map.py` — Pauli feature map.
- `quantum/feature_maps/zz_feature_map.py` — ZZ feature map.
- `quantum/fusion/__init__.py` — fusion package marker.
- `quantum/fusion/adapters.py` — fusion adapters.
- `quantum/fusion/calibrator.py` — fusion calibration.
- `quantum/fusion/engine.py` — hybrid fusion engine.
- `quantum/fusion/prediction.py` — fusion prediction aggregation.
- `quantum/fusion/providers.py` — fusion provider abstraction.
- `quantum/fusion/strategies/__init__.py` — strategies package marker.
- `quantum/fusion/strategies/base.py` — strategy base class.
- `quantum/fusion/strategies/adaptive.py` — adaptive fusion strategy.
- `quantum/fusion/strategies/bayesian.py` — Bayesian fusion strategy.
- `quantum/fusion/strategies/confidence.py` — confidence-weighted strategy.
- `quantum/fusion/strategies/stacking.py` — stacking strategy.
- `quantum/fusion/strategies/weighted_voting.py` — weighted-voting strategy.
- `quantum/inference/__init__.py` — inference package marker.
- `quantum/inference/engine.py` — quantum inference engine.
- `quantum/kernels/__init__.py` — kernels package marker.
- `quantum/kernels/base.py` — kernel base.
- `quantum/kernels/quantum_kernel.py` — quantum kernel implementation.
- `quantum/models/__init__.py` — models package marker.
- `quantum/models/base.py` — quantum model base.
- `quantum/models/manager.py` — quantum model manager.
- `quantum/models/qsvm.py` — Quantum Support Vector Machine model (321 lines).
- `quantum/training/__init__.py` — training package marker.
- `quantum/training/trainer.py` — quantum model trainer.
- `quantum/training/kernel_trainer.py` — quantum kernel trainer (340 lines).

## 22. `q_guardian/repositories/`

- `repositories/__init__.py` — repositories package marker.
- `repositories/base.py` — generic repository base class.

## 23. `q_guardian/response/` — response & recovery

- `response/__init__.py` — response package exports.
- `response/config.py` — response configuration.
- `response/data.py` — response data structures (308 lines).
- `response/enums.py` — response enums (17 enums bundled here).
- `response/events.py` — response domain events (21 event models).
- `response/exceptions.py` — response exceptions (13 exceptions; `TimeoutError as ResponseTimeoutError`).
- `response/plugin.py` — response plugin integration.
- `response/storage.py` — response storage.
- `response/engine/__init__.py` — engine package marker.
- `response/engine/response_engine.py` — `ResponseEngine`.
- `response/engine/orchestration_engine.py` — `OrchestrationEngine`.
- `response/engine/recovery_engine.py` — `RecoveryEngine`.
- `response/engine/rollback_engine.py` — `RollbackEngine`.
- `response/engine/approval_engine.py` — `ApprovalEngine`.
- `response/evidence/__init__.py` — evidence package marker.
- `response/evidence/collector.py` — `EvidenceCollector`.
- `response/evidence/snapshot.py` — `EvidenceSnapshot`.
- `response/evidence/timeline.py` — `EvidenceTimeline`.
- `response/integrations/__init__.py` — integrations package marker.
- `response/integrations/splunk.py` — Splunk integration (`SplunkIntegration`).
- `response/integrations/qradar.py` — IBM QRadar integration (`QRadarIntegration`).
- `response/integrations/sentinel.py` — Microsoft Sentinel integration.
- `response/integrations/cortex.py` — Cortex integration.
- `response/integrations/servicenow.py` — ServiceNow integration.
- `response/notifications/__init__.py` — notifications package marker.
- `response/notifications/notifier.py` — notification dispatcher.
- `response/notifications/email.py` — email notifier.
- `response/notifications/slack.py` — Slack notifier.
- `response/notifications/teams.py` — Microsoft Teams notifier.
- `response/notifications/webhook.py` — generic webhook notifier.
- `response/playbooks/__init__.py` — playbooks package marker.
- `response/playbooks/executor.py` — playbook executor.
- `response/playbooks/parser.py` — playbook definition parser.
- `response/playbooks/registry.py` — playbook registry.
- `response/playbooks/templates.py` — playbook templates.
- `response/playbooks/validator.py` — playbook definition validator.
- `response/quarantine/__init__.py` — quarantine package marker.
- `response/quarantine/quarantine_manager.py` — quarantine lifecycle manager.
- `response/quarantine/session.py` — quarantine session model.
- `response/quarantine/memory.py` — quarantine memory store.
- `response/quarantine/agent.py` — quarantined agent model.
- `response/quarantine/plugin.py` — quarantine plugin integration.

## 24. `q_guardian/risk/` — risk assessment

- `risk/__init__.py` — risk package exports.
- `risk/config.py` — risk configuration.
- `risk/data.py` — risk data structures.
- `risk/enums.py` — risk enums (risk level, severity, decision).
- `risk/events.py` — risk domain events.
- `risk/exceptions.py` — risk exception types.
- `risk/plugin.py` — risk plugin integration.
- `risk/storage.py` — risk storage.
- `risk/actions/__init__.py` — actions package marker.
- `risk/actions/action_engine.py` — risk action engine.
- `risk/actions/audit.py` — audit logging for risk actions.
- `risk/actions/notifier.py` — risk notifications.
- `risk/actions/responders.py` — risk responders.
- `risk/assessment/__init__.py` — assessment package marker.
- `risk/assessment/risk_engine.py` — `RiskAssessmentEngine` (`.assess()` → `RiskAssessment` with score/level/severity/decision/action/reasoning + graph/explanation/notifications).
- `risk/assessment/severity_engine.py` — severity computation.
- `risk/assessment/confidence_engine.py` — confidence scoring.
- `risk/assessment/threat_scorer.py` — threat scoring.
- `risk/assessment/trust_engine.py` — trust scoring.
- `risk/explainability/__init__.py` — explainability package marker.
- `risk/explainability/explanation_engine.py` — explanation generation.
- `risk/explainability/reasoning_graph.py` — reasoning graph construction.
- `risk/explainability/report_generator.py` — explainability reports.
- `risk/policy/__init__.py` — risk policy package marker.
- `risk/policy/evaluator.py` — risk policy evaluator.
- `risk/policy/policies.py` — built-in risk policies.
- `risk/policy/policy_engine.py` — risk policy engine.
- `risk/policy/policy_registry.py` — risk policy registry.

## 25. `q_guardian/runtime/`

- `runtime/__init__.py` — runtime package exports.
- `runtime/enums.py` — runtime enums.
- `runtime/models.py` — runtime data models (302 lines).
- `runtime/context.py` — runtime execution context.
- `runtime/events.py` — runtime domain events.
- `runtime/managers.py` — runtime managers (538 lines; largest file in the package).

## 26. `q_guardian/schemas/`

- `schemas/__init__.py` — schemas package marker.
- `schemas/base.py` — API schema base classes.

## 27. `q_guardian/sdk/`

- `sdk/__init__.py` — sdk package exports.
- `sdk/guardian.py` — `Guardian` public SDK facade (517 lines): composes managers/plugins/hooks/event bus; `start()`/`shutdown()` lifecycle; publishes `framework.started`/`framework.stopped`.

## 28. `q_guardian/security/`

- `security/__init__.py` — security package exports.
- `security/config.py` — security configuration.
- `security/enums.py` — security enums (finding types, detection categories).
- `security/models.py` — security models (findings, detections).
- `security/events.py` — security domain events.
- `security/decision.py` — `SecurityDecisionEngine.decide()`: decision cascade (BLOCK/REVIEW/WARN/ALLOW thresholds).
- `security/pipeline.py` — runtime security pipeline (478 lines): normalize → feature extraction → rules → classic ML → QML → hybrid fusion.
- `security/auth.py` — authentication helpers.
- `security/headers.py` — security response headers middleware.
- `security/cors.py` — CORS middleware.
- `security/extensibility.py` — detector extensibility hooks.
- `security/plugin.py` — security plugin integration.

## 29. `q_guardian/services/`

- `services/__init__.py` — services package marker.
- `services/base.py` — base service abstraction.

## 30. `q_guardian/utils/`

- `utils/__init__.py` — utils package marker.
- `utils/datetime_utils.py` — datetime helpers.
- `utils/env_utils.py` — environment variable helpers.
- `utils/helpers.py` — general helpers.
- `utils/json_utils.py` — JSON helpers.
- `utils/uuid_utils.py` — `generate_uuid`, `generate_correlation_id` (12-char format) helpers.

---

## Coverage Notes

- Total entries documented: **301** (this document), matching the canonical `src/` inventory.
- Every file is described from its actual code/role; where a file's specific behavior could not be determined from inspection alone, the description states its structural role rather than speculative details.
- For the detailed behavior of the largest modules, see `12_Quantum_ML_Documentation.md`, `13_Plugin_System_Events_Hooks_SDK_Documentation.md`, `14_Framework_Core_Infrastructure_Documentation.md`, `15_Policy_Risk_Documentation.md`, `16_Response_Recovery_Documentation.md`, `17_Observability_Operations_Documentation.md`, and `10_Security_Overview.md`.
