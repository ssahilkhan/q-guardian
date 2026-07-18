# Changelog

All notable changes to Q-Guardian will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

---

## [0.9.0] — 2026-07-19

### Autonomous Response & Recovery Engine

**Module 9** — source-agnostic autonomous incident response orchestration with playbooks, quarantine, evidence collection, notifications, SOAR integrations, and recovery.

#### Added

- **Response Engine** — consumes PolicyDecision/RiskAssessment/ActionPlan → ResponseResult, idempotency, action mapping, source-agnostic
- **Orchestration Engine** — playbook execution with dependency management, parallel steps, failure recovery (stop/skip/retry/rollback), step handlers
- **Recovery Engine** — 7 recovery actions (resume_session, restore_runtime, restore_plugins, restore_memory, retry_request, restore_policy, restart_agent) with retry and custom handlers
- **Rollback Engine** — checkpoint-based rollback with max checkpoint limits, target-specific queries, rollback-to-latest
- **Approval Engine** — automatic, manual, multi-level, timeout, quorum approvals with approve/reject/cancel/expire
- **Playbook Registry** — register/unregister, lookup by name/trigger, enabled/disabled filtering
- **Playbook Parser** — parse YAML-like, JSON, and dict formats into PlaybookDefinition
- **Playbook Executor** — execute playbooks through orchestration engine, trigger-based dispatch
- **Playbook Validator** — validate definitions (names, dependencies, timeouts, retry counts, max steps)
- **Built-in Playbook Templates** — block-threat, quarantine-agent, escalate-incident, rollback-operation
- **Quarantine Manager** — timed release, manual release, auto-release expired, max duration caps
- **Session/Agent/Plugin/Memory Quarantine** — target-specific convenience wrappers with appropriate blocked actions
- **Evidence Collector** — collect, query by correlation/type, immutable records
- **Evidence Snapshot** — point-in-time state snapshots linked to evidence records
- **Evidence Timeline** — chronological event timelines with filtering (type, severity) and export (JSON, Markdown, CSV)
- **Notification Notifier** — route notifications to channel handlers, record sent/failed status
- **Email/Webhook/Slack/Teams Notifiers** — pluggable notification handlers with priority support
- **SOAR Integrations** — Sentinel, Splunk, QRadar, Cortex XSOAR, ServiceNow (incidents, alerts, cases, change requests)
- **Response Plugin** — pluggable response handlers with action binding
- **Response Storage** — JSON file persistence for responses, quarantines, playbooks, evidence, recovery, rollbacks
- 21 data models, 19 events, 13 exceptions, 19 enums
- 173 unit tests, all passing

---

## [0.8.0] — 2026-07-19

### Advanced Policy Engine

**Module 8** — standalone policy-as-code framework with advanced condition parsing, versioning, conflict detection, simulation, external DSL adapters, RBAC, and policy composition.

#### Added

- `AdvancedPolicyEngine` — full-featured orchestrator with registry, evaluator, conflict detector, version manager, simulation engine, DSL adapters, RBAC, and composition
- **Condition Parser** — recursive-descent parser supporting AND/OR/NOT, parentheses, regex (`=~`, `!~`), temporal (`after`, `before`), membership (`in`, `not_in`), string ops (`contains`, `starts_with`, `ends_with`), existence (`exists`)
- **Policy Registry** — in-memory with optional JSON file persistence, status management (draft/active/suspended/retired)
- **Policy Evaluator** — collects ALL matching rules (not just first), priority-based winning, action parameters, temporal validity windows
- **Conflict Detector** — detects redundant, contradicting, shadowed, and overlapping rules across and within policies
- **Version Manager** — semantic versioning (major/minor/patch), snapshots, rollback, max version limits
- **Simulation Engine** — dry-run evaluation, batch simulation, replay, policy comparison, rule overrides
- **DSL Adapters** — Rego (OPA), Cedar (AWS), YAML, JSON import/export with adapter registry
- **RBAC Manager** — admin/editor/viewer roles, custom roles, permission checking, built-in role protection
- **Policy Composer** — templates, inheritance with depth limits, merge strategies (override/append/interleave), variable substitution
- **Policy Storage** — JSON file persistence with save/load/delete/clear
- 7 data models, 8 events, 8 exceptions, 8 enums
- 266 unit tests, all passing

---

## [0.7.0] — 2026-07-19

### Risk & Decision Intelligence Engine

**Module 7** — transforms raw detections into intelligent, explainable security decisions.

#### Added

- `RiskAssessmentEngine` — top-level orchestrator for the full risk pipeline
- **Assessment** — ThreatScorer, TrustEngine, ConfidenceEngine, SeverityEngine
- **Policy** — PolicyEngine, PolicyRegistry, PolicyEvaluator, 4 built-in policies
- **Actions** — ActionEngine, 6 responders, AuditTrail, Notifier
- **Explainability** — ExplanationEngine, ReasoningGraphBuilder, ReportGenerator (JSON/Markdown/Text/Structured)
- **Plugin** — RiskAnalysisPlugin for framework integration
- **Storage** — RiskStorage (JSON persistence)
- 229 unit tests, all passing

---

## [0.6.0] — 2026-07-19

### Hybrid Quantum Intelligence

**Module 6** — complete quantum computing layer with hybrid fusion.

#### Added

**Phase 1 — Quantum Infrastructure:**
- `QuantumBackend` ABC and `BackendManager` with fallback ordering and health checks
- `LocalSimulatorBackend` — pure-Python statevector simulator (no external dependencies)
- `QiskitAerBackend` and `QiskitRuntimeBackend` — Qiskit integration isolated to single file
- Quantum feature maps: `AngleEncodingMap`, `ZZFeatureMap`, `PauliFeatureMap`
- `QuantumKernel` ABC and `QuantumKernelEstimator` with circuit-level kernel computation
- `CircuitExecutor` for backend-agnostic circuit execution
- `BaseQuantumModel` ABC inheriting `BaseThreatModel` + `ThreatClassifier`
- `QuantumTrainer` and `QuantumEvaluator` for training/evaluation pipelines
- `QuantumAnalysisPlugin` for plugin system integration
- 16 event types for backend, circuit, model, and training lifecycle
- 12 exception classes with structured hierarchy
- 9 enumerations for backends, encoding, models, and fusion strategies

**Phase 2 — Quantum Learning:**
- `QSVMModel` — quantum support vector machine classifier
- `QuantumKernelTrainer` — hyper-parameter grid/random search with cross-validation
- `QuantumInferenceEngine` — multi-model inference with fallback
- `QuantumModelManager` — lifecycle management with tags, versioning, and health
- `QuantumModelStorage` — JSON persistence with versioning and rollback
- 9 learning lifecycle events
- Extended `QuantumModelMetadata` and `QuantumTrainingResult`

**Phase 3 — Hybrid Fusion Engine:**
- `PredictionProvider` ABC — standardized interface for all prediction sources
- `ThreatPrediction` — lingua franca output with label, confidence, probabilities, reasoning trace
- `ReasoningTrace` — explainability metadata with steps, evidence, rules, and feature importances
- `FusionStrategy` ABC and `FusedPrediction` data model
- `ConfidenceCalibrator` — normalization via none, temperature, min-max, or z-score methods
- `HybridFusionEngine` — orchestrator with provider/strategy registration and runtime switching
- `WeightedVotingStrategy` — majority voting with configurable weights
- `ConfidenceFusionStrategy` — confidence-weighted fusion
- `AdaptiveFusionStrategy` — sliding-window accuracy-based weight adjustment
- `StackingFusionStrategy` — logistic regression meta-learner (default strategy)
- `BayesianFusionStrategy` — interface-only (implementation deferred)
- Provider adapters: `RuleEngineProvider`, `ClassicalModelProvider`, `QuantumModelProvider`, `GenericProvider`
- 5 hybrid fusion events
- 129 unit tests covering providers, calibration, all strategies, engine, adapters, and events

---

## [0.5.0] — 2026-07-18

### Classical Machine Learning Security

**Module 5** — classical ML-based threat detection.

#### Added

- `BaseThreatModel` ABC and `ModelRegistry` for model lifecycle
- `IsolationForestDetector` — anomaly-based threat detection
- `RandomForestThreatClassifier` — supervised multi-class threat classification
- `XGBoostThreatClassifier` — gradient boosting with graceful import handling
- `EnsembleDetector` — weighted voting across multiple detectors
- `ModelManager` — registration, lazy loading, versioning, health
- `InferenceEngine` — orchestrates inference across detectors and classifiers
- `ModelTrainer` and `CrossValidator` for training pipelines
- `MLFeatureProvider` — 44-dimensional feature extraction
- `ModelStorage` — JSON-based model persistence
- `ThreatAnalysisPlugin` — unified scan pipeline (rules + ML + quantum)
- `BenchmarkMetrics` and `ResearchMetrics` for evaluation
- 139 unit tests

---

## [0.4.0] — 2026-07-17

### Prompt Security Engine

**Module 4** — rule-based prompt threat detection.

#### Added

- `PromptNormalizer` — Unicode normalization, whitespace handling, encoding detection
- `PromptValidator` — length, format, and structural validation
- `PromptFeatureExtractor` — statistical, keyword, and pattern feature extraction
- `RuleEngine` — configurable pattern-based threat detection
- `SecurityDecisionEngine` — ALLOW/WARN/REVIEW/BLOCK decisions
- `PromptScannerPlugin` — plugin integration
- Extensibility ABCs: `PromptDetector`, `PromptClassifier`, `FeatureProvider`, `ThreatClassifier`
- `PromptAnalysis`, `PromptFinding`, `PromptFeatures` data models
- `PromptCategory` and `PromptSeverity` enumerations
- 94 unit tests

---

## [0.3.0] — 2026-07-16

### Runtime Abstraction Layer

**Module 3** — framework-agnostic runtime concepts.

#### Added

- `Agent`, `AgentSession`, `AgentRequest`, `AgentResponse` models
- `RuntimeContext` — per-execution agent/session/request state
- `SessionManager` — session lifecycle management
- `RequestManager` — request tracking and history
- `ToolExecutionTracker` — tool invocation lifecycle
- `MemoryTracker` — memory operation tracking
- `RiskContext`, `SecurityContext`, `ThreatContext` models
- Runtime enumerations: `AgentStatus`, `SessionStatus`, `ToolType`, `ThreatType`, `ThreatSeverity`
- 133 unit tests

---

## [0.2.0] — 2026-07-15

### Framework Core

**Module 2** — reusable security framework engine.

#### Added

- `EventBus` — async pub/sub with wildcard support and priority ordering
- `Plugin` ABC and `PluginRegistry` — plugin lifecycle management
- `HookManager` — pre/post processing hooks
- `FrameworkStateMachine` — IDLE → INITIALIZING → RUNNING → STOPPING → STOPPED
- `FrameworkContext` — shared context passed to all plugins
- `FrameworkConfig` — structured configuration with validation
- `Adapter` ABC for AI framework integrations
- Standard event types: `PluginRegistered`, `PluginStarted`, `PluginStopped`, `HookRegistered`
- 87 unit tests

---

## [0.1.0] — 2026-07-14

### Enterprise Foundation

**Module 1** — production-grade FastAPI foundation.

#### Added

- FastAPI application factory with versioned API
- Structured logging with structlog
- Request tracking middleware (correlation IDs, timing)
- CORS and security headers
- MongoDB async connection (Motor)
- Health check endpoints
- Environment-aware configuration (pydantic-settings)
- Dependency injection container
- Docker and docker-compose setup
- Makefile for common operations
- 48 unit tests
