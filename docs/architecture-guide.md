# Architecture Guide

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Core Components](#core-components)
3. [Data Flow](#data-flow)
4. [Plugin Architecture](#plugin-architecture)
5. [Event-Driven Architecture](#event-driven-architecture)
6. [Security Layers](#security-layers)
7. [Quantum-Classical Hybrid Design](#quantum-classical-hybrid-design)
8. [Enterprise Integration Points](#enterprise-integration-points)

---

## System Architecture

### High-Level Overview

Q-Guardian follows a layered, plugin-driven architecture organized into six modules. Each module builds on the previous, connected through an async event bus and plugin registry.

```
+---------------------------------------------------------------+
|                    Application Layer                           |
|   FastAPI Endpoints | REST API | OpenAPI Documentation        |
+---------------------------------------------------------------+
|                    SDK Layer (Guardian Facade)                  |
|   Plugin Management | Event Dispatch | Session Control         |
+---------------------------------------------------------------+
|  Module 6    |  Module 5    |  Module 4    |  Module 3        |
|  Quantum     |  Classical   |  Prompt      |  Runtime         |
|  Analysis    |  ML Security |  Security    |  Abstraction     |
+---------------------------------------------------------------+
|                    Module 2: Framework Core                    |
|   EventBus | PluginRegistry | HookManager | StateMachine      |
+---------------------------------------------------------------+
|                    Module 1: Enterprise Foundation             |
|   FastAPI | Middleware | Database | Logging | Config           |
+---------------------------------------------------------------+
```

### Design Principles

- **Clean Architecture** -- strict dependency rule; outer layers never import inner layers
- **Plugin Architecture** -- every capability is a plugin; nothing is hard-coded
- **Event-Driven** -- async pub/sub event bus with wildcard support
- **Async-First** -- all I/O is async; compatible with high-concurrency agent workloads
- **Type-Safe** -- comprehensive type hints; Pydantic v2 validation; mypy strict mode
- **Zero Trust** -- every input is validated, normalized, and scored before action

---

## Core Components

### Guardian Facade (SDK Layer)

The `Guardian` class is the primary entry point. It wraps all subsystems behind a clean API.

```
Guardian
    |-- FrameworkStateMachine (lifecycle)
    |-- EventBus (pub/sub)
    |-- PluginRegistry (plugin management)
    |-- HookManager (pre/post hooks)
    |-- SessionManager (agent sessions)
    |-- RequestManager (request tracking)
    |-- ToolExecutionTracker (tool monitoring)
    |-- MemoryTracker (memory auditing)
```

Key responsibilities:
- Manage framework lifecycle (start, stop, error recovery)
- Route method calls to appropriate plugins
- Coordinate event publishing and hook execution
- Maintain runtime context for current agent/session

### Framework State Machine

```
INITIALIZING -> STARTING -> RUNNING -> STOPPING -> STOPPED
                     |          |
                     v          v
                   ERROR <------+
```

States are managed by `FrameworkStateMachine` and exposed through `Guardian.state`.

### Event Bus

The `EventBus` provides async publish/subscribe messaging:

```
Publisher -> EventBus -> Subscriber A
                      -> Subscriber B
                      -> Subscriber C
```

Features:
- Wildcard subscriptions (`threat.*`, `*`)
- Priority ordering for handlers
- Propagation control (stop handlers)
- Error isolation (one handler failure does not affect others)

### Plugin Registry

The `PluginRegistry` manages plugin lifecycle:

```
register_plugin() -> REGISTERED
    |
initialize_all() -> INITIALIZING -> REGISTERED
    |
start_all() -> RUNNING
    |
stop_all() -> STOPPED
```

Supports:
- Interface-based plugin lookup (`get_plugins_by_interface`)
- Auto-discovery via Python entry points
- Enable/disable without unregistering
- Health checking

### Hook Manager

The `HookManager` provides pre/post processing points:

```
before_prompt -> [handler_a, handler_b] -> after_prompt
before_scan   -> [handler_c]            -> after_scan
```

Handlers execute in registration order and can modify shared context.

---

## Data Flow

### Prompt Scanning Pipeline

```
User Input
    |
    v
Guardian.scan_prompt(prompt)
    |
    +-- HookManager.execute_hook("before_prompt")
    |
    +-- EventBus.publish(BeforePrompt)
    |
    +-- PluginRegistry.get_plugins_by_interface("prompt_scanner")
    |       |
    |       v
    |   PromptScannerPlugin.scan_prompt(prompt)
    |       |
    |       +-- PromptNormalizer.normalize(prompt)
    |       |       -> normalized_text
    |       |
    |       +-- PromptValidator.validate(normalized_text)
    |       |       -> validation_status, validation_errors
    |       |
    |       +-- PromptFeatureExtractor.extract(normalized_text)
    |       |       -> PromptFeatures (32-dim vector)
    |       |
    |       +-- RuleEngine.analyze(normalized_text, features)
    |       |       -> list[PromptFinding]
    |       |
    |       +-- SecurityDecisionEngine.decide(analysis)
    |       |       -> PromptDecision (allow, review, block)
    |       |
    |       v
    |   PromptAnalysis result
    |
    +-- HookManager.execute_hook("after_prompt")
    |
    +-- EventBus.publish(AfterPrompt)
    |
    v
Aggregated Results
```

### ML-Enhanced Pipeline

```
Prompt Input
    |
    v
ThreatAnalysisPlugin.scan_prompt(prompt)
    |
    +-- [Layer 1] Rule-Based Analysis
    |       RuleEngine.analyze()
    |       -> rule_findings
    |
    +-- [Layer 2] Classical ML
    |       InferenceEngine.run()
    |       -> IsolationForestDetector (anomaly)
    |       -> RandomForestThreatClassifier (classification)
    |       -> EnsembleDetector (combined)
    |       -> ml_findings
    |
    +-- [Layer 3] Merge Findings
    |       analysis.findings.extend(ml_findings)
    |
    +-- [Layer 4] Decision
    |       SecurityDecisionEngine.decide(analysis)
    |
    v
PromptAnalysis with rule + ML findings
```

### Quantum-Enhanced Pipeline

```
Prompt Input
    |
    v
ThreatAnalysisPlugin.scan_prompt(prompt)
    |
    +-- [Layer 1] Rule-Based Analysis
    |
    +-- [Layer 2] Classical ML
    |
    +-- [Layer 3] Quantum Analysis
    |       QuantumAnalysisPlugin.analyze_quantum()
    |       -> QuantumFeatureMap.encode(features)
    |       -> QuantumBackend.execute_circuit()
    |       -> QuantumKernelEstimator / QSVM / VQC
    |       -> quantum_findings
    |
    +-- [Layer 4] Hybrid Fusion
    |       HybridFusionEngine.fuse(
    |           rule_findings,
    |           ml_findings,
    |           quantum_findings
    |       )
    |       -> FusionStrategy (weighted, stacking, adaptive)
    |       -> FusedPrediction
    |
    +-- [Layer 5] Decision
    |
    v
PromptAnalysis with fused findings
```

---

## Plugin Architecture

### Plugin Interface

Every plugin must implement:

```python
class Plugin(ABC):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def initialize(self, context: FrameworkContext) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...
```

Optional overrides:
- `health()` -- return health status
- `configuration()` -- describe configuration options
- `interfaces` -- list of interface identifiers

### Plugin Discovery

Plugins can be discovered through:

1. **Manual registration** -- `guardian.register_plugin(plugin)`
2. **Entry points** -- pip-installable plugins under `q_guardian.plugins` group

```toml
# In plugin's pyproject.toml
[project.entry-points."q_guardian.plugins"]
my_plugin = "my_package:MyPlugin"
```

### Built-in Plugins

| Plugin | Interface | Purpose |
|--------|-----------|---------|
| PromptScannerPlugin | prompt_scanner | Rule-based prompt scanning |
| ThreatAnalysisPlugin | prompt_scanner | Rule + ML threat analysis |
| QuantumAnalysisPlugin | quantum_analyzer | Quantum-enhanced analysis |
| ObservabilityPlugin | observability, metrics, tracing | Full observability stack |

---

## Event-Driven Architecture

### Event Types

```
Framework Events:
    FrameworkStarted, FrameworkStopped, FrameworkError
    PluginLoaded, PluginUnloaded

Security Events:
    ThreatDetected, PromptReceived, PromptScanned
    PolicyViolation, AnomalyDetected
    PromptBlocked, PromptAllowed

Runtime Events:
    SessionStarted, SessionEnded
    RequestReceived, ResponseCompleted

Quantum Events:
    QuantumCircuitCreated, QuantumMeasurementMade
    QuantumStateCollapsed

Observability Events:
    MetricsUpdated, AlertTriggered
```

### Event Flow

```
Component A --publish(event)--> EventBus --deliver--> Handler 1
                                                  -> Handler 2
                                                  -> Handler 3
```

### Propagation Control

```python
async def exclusive_handler(event):
    event.stop_propagation()  # No further handlers receive this event
```

---

## Security Layers

### Layer 1: Input Normalization

- Unicode normalization
- Whitespace collapsing
- Encoding detection and conversion
- Control character filtering

### Layer 2: Input Validation

- Length limits (min/max)
- Line count limits
- Encoding validation
- Content structure checks

### Layer 3: Feature Extraction

- 32-dimensional feature vector
- Statistical features (length, entropy, ratios)
- Keyword features (suspicious keyword counts)
- Pattern features (code blocks, URLs, encoding)
- Character distribution features

### Layer 4: Rule-Based Detection

- Pattern matching rules
- Category-based classification
- Severity scoring
- Configurable thresholds

### Layer 5: ML Detection

- Anomaly detection (Isolation Forest)
- Multi-class classification (Random Forest, XGBoost)
- Ensemble voting
- Confidence calibration

### Layer 6: Quantum Analysis

- Quantum feature encoding
- Quantum kernel estimation
- Variational quantum classification
- Hybrid fusion strategies

---

## Quantum-Classical Hybrid Design

### Backend Abstraction

```
QuantumBackend (ABC)
    |-- LocalSimulatorBackend
    |-- QiskitBackend
    |-- PennyLaneBackend
    |-- CUDAQBackend (optional)
```

### Feature Encoding

```
Classical Features (32-dim)
    |
    +-- AngleEncodingMap -> Rx(theta) rotations
    +-- ZZFeatureMap -> Entangling gates
    +-- PauliFeatureMap -> Pauli rotations
    |
    v
Quantum Circuit
```

### Fusion Strategies

```
FusionStrategy (ABC)
    |-- WeightedVotingStrategy (simple weighted average)
    |-- ConfidenceFusionStrategy (confidence-based)
    |-- AdaptiveFusionStrategy (learns optimal weights)
    |-- StackingFusionStrategy (meta-learner, default)
    |-- BayesianFusionStrategy (probabilistic)
```

### Graceful Degradation

The system operates at different capability levels:

1. **Rules Only** -- no ML or quantum dependencies
2. **Rules + Classical ML** -- requires scikit-learn
3. **Rules + ML + Quantum** -- requires quantum backend

Each level is fully functional. Higher levels provide improved detection.

---

## Enterprise Integration Points

### REST API

FastAPI-based API with versioned endpoints:

```
GET  /                  -> Application info
GET  /api/v1/health     -> Health check (liveness probe)
GET  /api/v1/version    -> Version information
GET  /api/v1/status     -> Operational status
```

OpenAPI documentation available at `/docs` (Swagger) and `/redoc`.

### Middleware Stack

```
Request
    |
    v
CorrelationIDMiddleware (add request ID)
    |
    v
ResponseTimingMiddleware (measure latency)
    |
    v
ExceptionLoggingMiddleware (log errors)
    |
    v
SecurityHeadersMiddleware (security headers)
    |
    v
CORSMiddleware (cross-origin)
    |
    v
TrustedHostMiddleware (host validation)
    |
    v
Route Handler
```

### Database Integration

Async MongoDB via Motor:

```
DatabaseClient
    |-- connect()
    |-- disconnect()
    |-- get_collection(name)
    |-- health_check()
```

### Structured Logging

JSON-formatted logs via structlog:

```json
{
    "event": "prompt_scanned",
    "plugin": "prompt-scanner",
    "decision": "block",
    "risk_score": 0.85,
    "findings_count": 3,
    "processing_time_ms": 12.5
}
```

### Observability Stack

The `ObservabilityPlugin` provides:

- **Metrics** -- counters, gauges, histograms
- **Tracing** -- distributed trace context
- **Analytics** -- event ingestion and analysis
- **Alerts** -- threshold-based alerting
- **Health** -- component health monitoring

Integrates with Prometheus, Grafana, Datadog, and CloudWatch through exporter adapters.
