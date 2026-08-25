# API Reference

## Table of Contents

1. [REST API Endpoints](#rest-api-endpoints)
2. [Python SDK (Guardian Class)](#python-sdk)
3. [Plugin API](#plugin-api)
4. [Event System API](#event-system-api)
5. [Configuration API](#configuration-api)
6. [Public Classes Reference](#public-classes-reference)

---

## REST API Endpoints

### Base URL

```
http://localhost:8000/api/v1
```

### GET /

Returns basic application information.

**Response:**

```json
{
  "application": "Q-Guardian",
  "version": "1.1.0",
  "docs": "/docs",
  "redoc": "/redoc",
  "health": "/api/v1/health"
}
```

### GET /api/v1/health

Health check endpoint. Used as liveness probe.

**Response:**

```json
{
  "status": "healthy",
  "application": "Q-Guardian",
  "version": "1.1.0",
  "environment": "production",
  "timestamp": "2026-07-19T12:00:00Z",
  "database": {
    "status": "healthy",
    "latency_ms": 2
  }
}
```

Status values: `healthy`, `degraded`

### GET /api/v1/version

Returns version and system information.

**Response:**

```json
{
  "success": true,
  "message": "Version information retrieved successfully",
  "data": {
    "application": "Q-Guardian",
    "version": "1.1.0",
    "environment": "production",
    "python_version": "3.12.4",
    "timestamp": "2026-07-19T12:00:00Z"
  }
}
```

### GET /api/v1/status

Returns operational status.

**Response:**

```json
{
  "success": true,
  "message": "Application is operational",
  "data": {
    "status": "operational"
  }
}
```

### OpenAPI Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## Python SDK

### Guardian Class

The main entry point for the Q-Guardian framework.

#### Constructor

```python
Guardian(config: FrameworkConfig | None = None)
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `state` | `FrameworkState` | Current framework state |
| `events` | `EventBus` | Event bus instance |
| `plugins` | `PluginRegistry` | Plugin registry instance |
| `config` | `FrameworkConfig` | Framework configuration |
| `runtime` | `RuntimeContext \| None` | Current runtime context |
| `current_agent` | `Agent \| None` | Currently active agent |
| `current_session` | `AgentSession \| None` | Currently active session |
| `session_manager` | `SessionManager` | Session manager |
| `request_manager` | `RequestManager` | Request manager |
| `tool_tracker` | `ToolExecutionTracker` | Tool execution tracker |
| `memory_tracker` | `MemoryTracker` | Memory tracker |

#### Lifecycle Methods

```python
async def start() -> None
```

Start the framework. Transitions through INITIALIZING, STARTING, RUNNING states. Initializes and starts all registered plugins.

```python
async def shutdown() -> None
```

Shut down the framework. Stops all plugins in reverse order, clears event bus and hooks.

#### Plugin Management

```python
def register_plugin(plugin: Plugin) -> None
def unregister_plugin(name: str) -> None
def enable_plugin(name: str) -> None
def disable_plugin(name: str) -> None
def list_plugins() -> list[PluginMetadata]
def get_plugin(name: str) -> Plugin
```

#### Event Methods

```python
async def publish(event: Event) -> Event
async def subscribe(event_type: str, handler: EventHandler, priority: int = 0) -> int
async def unsubscribe(subscription_id: int) -> bool
```

#### Hook Methods

```python
async def register_hook(hook_name: str, handler: Callable) -> None
async def execute_hook(hook_name: str, **kwargs) -> dict[str, Any]
```

#### Adapter Methods

```python
def register_adapter(adapter: Adapter) -> None
def get_adapter(name: str) -> Adapter
```

#### Convenience Methods

```python
async def scan_prompt(prompt: str, **kwargs) -> dict[str, Any]
async def monitor(event_data: dict[str, Any]) -> dict[str, Any]
async def calculate_risk(data: dict[str, Any]) -> dict[str, Any]
async def enforce_policy(data: dict[str, Any]) -> dict[str, Any]
```

#### Runtime Methods

```python
async def create_session(
    agent_id: str = "",
    conversation_id: str = "",
    user_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> AgentSession

async def close_session() -> bool
def set_agent(agent: Agent) -> None
def get_runtime_context() -> RuntimeContext | None
```

---

## Plugin API

### Plugin ABC

```python
from q_guardian.plugins.base import Plugin


class MyPlugin(Plugin):
    @property
    def name(self) -> str: ...  # Required

    @property
    def version(self) -> str: ...  # Required

    async def initialize(self, context: FrameworkContext) -> None: ...  # Required
    async def start(self) -> None: ...  # Required
    async def stop(self) -> None: ...  # Required

    # Optional
    @property
    def author(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def dependencies(self) -> list[str]: ...
    @property
    def interfaces(self) -> list[str]: ...
    def health(self) -> dict[str, Any]: ...
    def configuration(self) -> dict[str, Any]: ...
```

### PluginMetadata

```python
from q_guardian.plugins.base import PluginMetadata

metadata = PluginMetadata(
    name="my-plugin",
    version="1.0.0",
    author="Developer",
    description="My plugin",
    dependencies=["other-plugin"],
    status=PluginStatus.REGISTERED,
    interfaces=["prompt_scanner"],
)
```

### PluginStatus

```python
from q_guardian.plugins.base import PluginStatus

# Values:
PluginStatus.REGISTERED
PluginStatus.INITIALIZING
PluginStatus.RUNNING
PluginStatus.STOPPED
PluginStatus.ERROR
PluginStatus.DISABLED
```

### PluginRegistry

```python
from q_guardian.plugins.registry import PluginRegistry

registry = PluginRegistry()
registry.register_plugin(plugin)
registry.unregister_plugin("my-plugin")
registry.get_plugin("my-plugin")
registry.has_plugin("my-plugin")
registry.get_plugins_by_interface("prompt_scanner")
registry.list_plugins(status=PluginStatus.RUNNING)
registry.enable_plugin("my-plugin")
registry.disable_plugin("my-plugin")
await registry.initialize_all(context)
await registry.start_all()
await registry.stop_all()
await registry.health_check()
```

---

## Event System API

### EventBus

```python
from q_guardian.events.bus import EventBus

bus = EventBus()

# Subscribe
subscription_id = await bus.subscribe("threat.detected", handler, priority=0)

# Publish
event = await bus.publish(event)

# Unsubscribe
removed = await bus.unsubscribe(subscription_id)

# Info
count = bus.subscriber_count("threat.detected")

# Cleanup
await bus.clear()
```

### Event Base Class

```python
from q_guardian.events.base import Event


class MyEvent(Event):
    def __init__(self, data: dict, source: str = "custom"):
        self.id = str(uuid4())
        self.timestamp = datetime.now()
        self.source = source
        self.data = data
        self._propagation_stopped = False

    @property
    def event_type(self) -> str:
        return "custom.event"

    def stop_propagation(self) -> None:
        self._propagation_stopped = True

    @property
    def propagation_stopped(self) -> bool:
        return self._propagation_stopped
```

### Standard Events

```python
from q_guardian.events.standard import (
    # Framework
    FrameworkStarted,
    FrameworkStopped,
    FrameworkError,
    PluginLoaded,
    PluginUnloaded,
    # Security
    ThreatDetected,
    PromptReceived,
    PromptScanned,
    PolicyViolation,
    AnomalyDetected,
    # Prompt Analysis
    BeforePrompt,
    AfterPrompt,
    PromptBlocked,
    PromptAllowed,
    # Quantum
    QuantumCircuitCreated,
    QuantumMeasurementMade,
    QuantumStateCollapsed,
    # Dashboard
    MetricsUpdated,
    AlertTriggered,
)
```

---

## Configuration API

### FrameworkConfig

```python
from q_guardian.framework.config import FrameworkConfig

config = FrameworkConfig(
    plugins=PluginConfig(enabled=True, priority=0),
    runtime=RuntimeConfig(
        max_concurrent_agents=100,
        request_timeout_seconds=30,
        enable_caching=True,
    ),
    policy=PolicyConfig(
        enforcement_mode="enforce",
        default_policy="allow",
    ),
    quantum=QuantumConfig(
        enabled=False,
        backend="simulator",
    ),
    dashboard=DashboardConfig(
        enabled=False,
        refresh_interval_seconds=30,
    ),
    prompt_scanner=PromptScannerConfig(
        enabled=True,
        sensitivity="medium",
    ),
    plugin_configs={
        "my-plugin": {"key": "value"},
    },
)

# Load from file
await config.load_from_file("config.json")

# Get plugin-specific config
plugin_config = config.get_plugin_config("my-plugin")

# Create from Module 1 settings
config = FrameworkConfig.from_settings(settings)
```

### AppSettings

```python
from q_guardian.config.settings import AppSettings, get_settings

settings = get_settings()

# AppSettings
settings.app.name  # "Q-Guardian"
settings.app.version  # "1.1.0"
settings.app.environment  # Environment.DEVELOPMENT
settings.app.debug  # True
settings.app.host  # "0.0.0.0"
settings.app.port  # 8000
settings.app.is_development  # True/False
settings.app.is_production  # True/False

# DatabaseSettings
settings.database.url  # "mongodb://localhost:27017"
settings.database.database  # "q_guardian"

# SecuritySettings
settings.security.secret_key
settings.security.jwt_algorithm

# CORSSettings
settings.cors.origins  # ["http://localhost:3000"]

# LoggingSettings
settings.logging.level  # "INFO"
settings.logging.format  # "json"
```

### PromptSecurityConfig

```python
from q_guardian.security.config import PromptSecurityConfig

config = PromptSecurityConfig(
    enabled=True,
    sensitivity="medium",
    max_prompt_length=100000,
    min_prompt_length=1,
    max_lines=1000,
    block_on_critical=True,
    block_on_high_count=3,
    review_on_high_count=1,
    warn_on_medium_count=2,
    log_findings=True,
    suspicious_keywords=["ignore previous", "bypass"],
)
```

### MLConfig

```python
from q_guardian.ml.config import MLConfig

config = MLConfig(
    enabled=True,
    anomaly_threshold=0.5,
    classification_threshold=0.5,
    model_storage_path="models/ml",
    default_cv_folds=5,
    random_state=42,
)
```

### QuantumConfig

```python
from q_guardian.quantum.config import QuantumConfig

config = QuantumConfig(
    enabled=True,
    backend="simulator",
    backend_device="statevector_simulator",
    num_qubits=5,
    shots=1024,
    encoding_type="angle",
    feature_map_depth=2,
    quantum_models=["qsvm", "vqc"],
    enable_quantum_ensemble=True,
    fusion_strategy="stacking",
    quantum_weight=0.3,
    classical_weight=0.5,
    rule_weight=0.2,
    optimization_level=1,
    enable_error_mitigation=True,
    max_circuit_depth=100,
    ibm_token=None,
    use_hardware=False,
)
```

---

## Public Classes Reference

### Runtime Models

```python
from q_guardian import Agent, AgentSession, AgentRequest, AgentResponse
from q_guardian import ToolInvocation, MemoryAccess
from q_guardian import SecurityContext, ThreatContext, RiskContext
from q_guardian import RuntimeContext
from q_guardian import MemoryTracker, RequestManager, SessionManager, ToolExecutionTracker
```

### Runtime Enums

```python
from q_guardian import (
    AgentStatus,  # INACTIVE, ACTIVE
    SessionStatus,  # OPEN, CLOSED, EXPIRED
    MemoryType,  # SHORT_TERM, LONG_TERM, EPISODIC
    MemoryOperation,  # READ, WRITE, DELETE, SEARCH
    ThreatSeverity,  # LOW, MEDIUM, HIGH, CRITICAL
    ThreatType,  # PROMPT_INJECTION, JAILBREAK, DATA_EXFILTRATION, ...
    ToolType,  # FUNCTION, API, DATABASE, FILE_SYSTEM, ...
)
```

### Security Classes

```python
from q_guardian import (
    PromptNormalizer,
    PromptValidator,
    PromptFeatureExtractor,
    RuleEngine,
    SecurityDecisionEngine,
    PromptScannerPlugin,
    PromptAnalysis,
    PromptFeatures,
    PromptFinding,
    PromptRule,
)
```

### Security Enums

```python
from q_guardian import (
    PromptCategory,  # PROMPT_INJECTION, JAILBREAK, MANIPULATION, ...
    PromptDecision,  # ALLOW, REVIEW, BLOCK
    PromptSeverity,  # LOW, MEDIUM, HIGH, CRITICAL
)
```

### ML Classes

```python
from q_guardian import (
    BaseThreatModel,
    ModelRegistry,
    IsolationForestDetector,
    RandomForestThreatClassifier,
    XGBoostThreatClassifier,
    EnsembleDetector,
    ModelManager,
    ModelStorage,
    MLFeatureProvider,
    InferenceEngine,
    ModelTrainer,
    CrossValidator,
    BenchmarkMetrics,
    ResearchMetrics,
    ThreatAnalysisPlugin,
)
```

### ML Data Models

```python
from q_guardian import (
    ModelMetadata,
    InferenceResult,
    TrainingResult,
    FeatureVector,
    EvaluationMetrics,
)
```

### ML Enums

```python
from q_guardian import (
    ModelType,  # ANOMALY_DETECTOR, CLASSIFIER, ENSEMBLE
    ModelBackend,  # SKLEARN, XGBOOST, CUSTOM
    TrainingStatus,  # NOT_TRAINED, TRAINING, TRAINED, FAILED
    ModelStatus,  # LOADED, UNLOADED, ERROR
)
```

### Quantum Classes

```python
from q_guardian import (
    QuantumBackend,
    BackendManager,
    LocalSimulatorBackend,
    QuantumFeatureMap,
    AngleEncodingMap,
    ZZFeatureMap,
    PauliFeatureMap,
    QuantumKernel,
    QuantumKernelEstimator,
    CircuitExecutor,
    BaseQuantumModel,
    QuantumTrainer,
    QuantumEvaluator,
    QuantumAnalysisPlugin,
)
```

### Quantum Data Models

```python
from q_guardian import (
    CircuitResult,
    QuantumModelMetadata,
    QuantumTrainingResult,
    QuantumInferenceResult,
)
```

### Quantum Enums

```python
from q_guardian import (
    QuantumBackendType,  # SIMULATOR, QISKIT, PENNYLANE, CUDAQ
    EncodingType,  # ANGLE, AMPLITUDE, ZZ, PAULI
    QuantumModelType,  # QSVM, VQC, KERNEL, ENSEMBLE
)
```

### Core Classes

```python
from q_guardian import (
    Event,
    EventBus,
    Plugin,
    PluginMetadata,
    PluginStatus,
    PluginRegistry,
    HookManager,
    Adapter,
    FrameworkConfig,
    FrameworkContext,
    FrameworkState,
    Guardian,
)
```
