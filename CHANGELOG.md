# Changelog

All notable changes to Q-Guardian will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

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
