# Configuration Guide

## Table of Contents

1. [Configuration Overview](#configuration-overview)
2. [Environment Variables](#environment-variables)
3. [Settings Classes](#settings-classes)
4. [Framework Configuration](#framework-configuration)
5. [Security Settings](#security-settings)
6. [ML Configuration](#ml-configuration)
7. [Quantum Configuration](#quantum-configuration)
8. [Observability Configuration](#observability-configuration)
9. [Configuration Examples](#configuration-examples)

---

## Configuration Overview

Q-Guardian uses a layered configuration system:

1. **Environment variables** -- loaded from `.env` files via pydantic-settings
2. **Settings classes** -- typed, validated configuration objects
3. **FrameworkConfig** -- aggregate framework-level configuration
4. **Plugin configs** -- per-plugin configuration overrides

Priority order: programmatic > environment variables > defaults.

### Loading Order

```python
# 1. Environment variables and .env file are loaded automatically
# 2. Settings classes are instantiated from environment
# 3. FrameworkConfig can be created from settings or directly
# 4. Guardian receives FrameworkConfig

from q_guardian.config.settings import get_settings
from q_guardian.framework.config import FrameworkConfig
from q_guardian import Guardian

# Option A: Use default settings
guardian = Guardian()

# Option B: Create from settings
settings = get_settings()
config = FrameworkConfig.from_settings(settings)
guardian = Guardian(config=config)

# Option C: Direct configuration
config = FrameworkConfig(
    runtime={"max_concurrent_agents": 200},
    quantum={"enabled": True},
)
guardian = Guardian(config=config)
```

---

## Environment Variables

### .env File

Create a `.env` file in the project root:

```bash
# Application
APP_NAME=Q-Guardian
APP_ENVIRONMENT=production
APP_DEBUG=false
APP_HOST=0.0.0.0
APP_PORT=8000
APP_LOG_LEVEL=INFO
APP_LOG_DIR=logs

# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=q_guardian
MONGODB_MIN_POOL_SIZE=1
MONGODB_MAX_POOL_SIZE=10
MONGODB_TIMEOUT_MS=5000

# Security
SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30
JWT_REFRESH_EXPIRATION_DAYS=7

# CORS
CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=["*"]
CORS_ALLOW_HEADERS=["*"]

# Logging
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=30
LOG_FORMAT=json
```

### Environment Profiles

Set `APP_ENVIRONMENT` to control behavior:

| Value | Debug Default | Log Level | CORS |
|-------|---------------|-----------|------|
| development | true | DEBUG | Permissive |
| testing | true | INFO | Permissive |
| production | false | WARNING | Restrictive |

---

## Settings Classes

### AppSettings

Prefix: `APP_`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | Q-Guardian | Application name |
| `version` | str | 1.1.0 | Application version |
| `environment` | Environment | development | Runtime environment |
| `debug` | bool | true | Debug mode |
| `host` | str | 0.0.0.0 | Server host |
| `port` | int | 8000 | Server port |
| `log_level` | str | INFO | Logging level |
| `log_dir` | str | logs | Log directory |

### DatabaseSettings

Prefix: `MONGODB_`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | str | mongodb://localhost:27017 | Connection URL |
| `database` | str | q_guardian | Database name |
| `min_pool_size` | int | 1 | Min connection pool |
| `max_pool_size` | int | 10 | Max connection pool |
| `timeout_ms` | int | 5000 | Connection timeout (ms) |

### SecuritySettings

No prefix (reads from root env).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `secret_key` | str | change-me... | Application secret |
| `jwt_algorithm` | str | HS256 | JWT algorithm |
| `jwt_expiration_minutes` | int | 30 | JWT lifetime |
| `jwt_refresh_expiration_days` | int | 7 | Refresh token lifetime |
| `api_key_header` | str | X-API-Key | API key header name |

### CORSSettings

Prefix: `CORS_`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `origins` | list[str] | localhost:3000,8080 | Allowed origins |
| `allow_credentials` | bool | true | Allow credentials |
| `allow_methods` | list[str] | * | Allowed methods |
| `allow_headers` | list[str] | * | Allowed headers |

### LoggingSettings

No prefix (reads from root env).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `level` | str | INFO | Log level |
| `dir` | str | logs | Log directory |
| `max_bytes` | int | 10485760 | Max file size (10MB) |
| `backup_count` | int | 30 | Backup file count |
| `format` | str | json | Log format (json/console) |

---

## Framework Configuration

### PluginConfig

```python
from q_guardian.framework.config import PluginConfig

config = PluginConfig(
    enabled=True,      # Enable/disable plugin system
    priority=0,        # Default priority for all plugins
)
```

### RuntimeConfig

```python
from q_guardian.framework.config import RuntimeConfig

config = RuntimeConfig(
    max_concurrent_agents=100,      # Max concurrent agent sessions
    request_timeout_seconds=30,     # Request timeout
    enable_caching=True,            # Enable response caching
)
```

### PolicyConfig

```python
from q_guardian.framework.config import PolicyConfig

config = PolicyConfig(
    enforcement_mode="enforce",  # enforce | audit | disabled
    default_policy="allow",      # Default action for unknown policies
)
```

### PromptScannerConfig

```python
from q_guardian.framework.config import PromptScannerConfig

config = PromptScannerConfig(
    enabled=True,
    sensitivity="medium",  # low | medium | high
)
```

### DashboardConfig

```python
from q_guardian.framework.config import DashboardConfig

config = DashboardConfig(
    enabled=False,
    refresh_interval_seconds=30,
)
```

---

## Security Settings

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
    suspicious_keywords=[
        "ignore previous",
        "disregard instructions",
        "you are now",
        "bypass safety",
        "maintenance mode",
        "override",
        "system prompt",
        "jailbreak",
    ],
)
```

### Decision Thresholds

| Threshold | Default | Description |
|-----------|---------|-------------|
| `block_on_critical` | true | Block immediately on critical severity |
| `block_on_high_count` | 3 | Block when high-severity findings exceed count |
| `review_on_high_count` | 1 | Flag for review on first high-severity finding |
| `warn_on_medium_count` | 2 | Warn when medium-severity findings exceed count |

---

## ML Configuration

### MLConfig

```python
from q_guardian.ml.config import MLConfig

config = MLConfig(
    enabled=True,
    anomaly_threshold=0.5,          # Threshold for anomaly detector
    classification_threshold=0.5,   # Threshold for classifier
    model_storage_path="models/ml", # Path to save/load models
    default_cv_folds=5,             # Cross-validation folds
    random_state=42,                # Reproducibility seed
)
```

### Model-Specific Settings

```python
from q_guardian.ml import (
    IsolationForestDetector,
    RandomForestThreatClassifier,
    EnsembleDetector,
)

# Isolation Forest
detector = IsolationForestDetector(
    contamination=0.1,   # Expected fraction of anomalies
    n_estimators=100,    # Number of trees
)

# Random Forest
classifier = RandomForestThreatClassifier(
    n_estimators=100,    # Number of trees
    max_depth=None,      # Maximum tree depth
)

# Ensemble
ensemble = EnsembleDetector(
    detectors=[detector, classifier],
    weights={"isolation-forest": 1.0, "random-forest": 2.0},
)
```

---

## Quantum Configuration

### QuantumConfig

```python
from q_guardian.quantum.config import QuantumConfig

config = QuantumConfig(
    enabled=True,

    # Backend
    backend="simulator",           # simulator | qiskit | pennylane | cudaq
    backend_device="statevector_simulator",
    num_qubits=5,
    shots=1024,

    # Feature Encoding
    encoding_type="angle",         # angle | amplitude | zz | pauli
    feature_map_depth=2,

    # Models
    quantum_models=["qsvm", "vqc"],
    enable_quantum_ensemble=True,

    # Fusion
    fusion_strategy="stacking",    # weighted | stacking | bayesian | adaptive
    quantum_weight=0.3,
    classical_weight=0.5,
    rule_weight=0.2,

    # Execution
    optimization_level=1,
    enable_error_mitigation=True,
    max_circuit_depth=100,

    # Hardware
    ibm_token=None,
    ibm_instance=None,
    use_hardware=False,
)
```

### Backend Selection

| Backend | Package Required | Best For |
|---------|-----------------|----------|
| simulator | None (built-in) | Development, testing |
| qiskit | qiskit, qiskit-aer | Research, IBM hardware |
| pennylane | pennylane | Hardware-agnostic |
| cudaq | cuda-quantum | GPU-accelerated simulation |

### Fusion Strategies

| Strategy | Complexity | Description |
|----------|-----------|-------------|
| weighted | Low | Simple weighted average of predictions |
| stacking | Medium | Meta-learner learns optimal combination (default) |
| bayesian | High | Probabilistic fusion with priors |
| adaptive | High | Learns weights dynamically from data |

---

## Observability Configuration

### ObservabilityPlugin Config

```python
from q_guardian.observability import ObservabilityPlugin

config = {
    "metrics": {
        "enabled": True,
        "interval_seconds": 15,
        "exporters": ["prometheus", "datadog"],
    },
    "tracing": {
        "enabled": True,
        "sample_rate": 0.1,          # 10% of traces
        "exporters": ["jaeger"],
    },
    "health": {
        "enabled": True,
        "check_interval_seconds": 30,
    },
    "analytics": {
        "enabled": True,
    },
    "alerts": {
        "enabled": True,
        "rules": [
            {
                "name": "high_threat_rate",
                "metric": "qguardian_threats_detected_total",
                "condition": "rate > 10 per minute",
                "severity": "critical",
            },
        ],
    },
}

plugin = ObservabilityPlugin(config=config)
```

---

## Configuration Examples

### Minimal Development Config

```python
from q_guardian import Guardian, FrameworkConfig

config = FrameworkConfig()
guardian = Guardian(config=config)
```

### Production Config

```python
from q_guardian import Guardian, FrameworkConfig
from q_guardian.framework.config import (
    RuntimeConfig, PolicyConfig, PluginConfig,
)

config = FrameworkConfig(
    plugins=PluginConfig(enabled=True),
    runtime=RuntimeConfig(
        max_concurrent_agents=200,
        request_timeout_seconds=10,
        enable_caching=True,
    ),
    policy=PolicyConfig(
        enforcement_mode="enforce",
        default_policy="allow",
    ),
    quantum={"enabled": False},
)

guardian = Guardian(config=config)
```

### ML-Enabled Config

```python
from q_guardian import Guardian, FrameworkConfig
from q_guardian.ml import (
    ThreatAnalysisPlugin, MLConfig,
    IsolationForestDetector, RandomForestThreatClassifier,
)

ml_config = MLConfig(enabled=True, anomaly_threshold=0.4)

plugin = ThreatAnalysisPlugin(config=ml_config)
plugin.register_ml_detector(IsolationForestDetector(contamination=0.1))
plugin.register_ml_classifier(RandomForestThreatClassifier(n_estimators=200))

config = FrameworkConfig(
    runtime={"max_concurrent_agents": 100},
)

guardian = Guardian(config=config)
guardian.register_plugin(plugin)
```

### Quantum-Enabled Config

```python
from q_guardian import Guardian, FrameworkConfig
from q_guardian.quantum import QuantumConfig, QuantumAnalysisPlugin

quantum_config = QuantumConfig(
    enabled=True,
    backend="simulator",
    num_qubits=5,
    fusion_strategy="stacking",
)

quantum_plugin = QuantumAnalysisPlugin(config=quantum_config)

config = FrameworkConfig(
    quantum={"enabled": True, "backend": "simulator"},
)

guardian = Guardian(config=config)
guardian.register_plugin(quantum_plugin)
```

### Full Enterprise Config (from .env)

```python
from q_guardian.config.settings import get_settings
from q_guardian.framework.config import FrameworkConfig
from q_guardian import Guardian

settings = get_settings()
config = FrameworkConfig.from_settings(settings)
guardian = Guardian(config=config)
```

### Loading from JSON File

```json
{
  "plugins": {"enabled": true},
  "runtime": {
    "max_concurrent_agents": 150,
    "request_timeout_seconds": 20
  },
  "policy": {
    "enforcement_mode": "enforce"
  },
  "quantum": {
    "enabled": false
  },
  "prompt_scanner": {
    "enabled": true,
    "sensitivity": "high"
  }
}
```

```python
config = FrameworkConfig()
await config.load_from_file("config.json")
guardian = Guardian(config=config)
```
