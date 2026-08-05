# Migration Guide

## Table of Contents

1. [Version Compatibility Matrix](#version-compatibility-matrix)
2. [Breaking Changes Between Versions](#breaking-changes-between-versions)
3. [Migration from 0.8.x to 1.0.0](#migration-from-08x-to-0100)
4. [Deprecated APIs](#deprecated-apis)

---

## Version Compatibility Matrix

### Python Versions

| Q-Guardian Version | Python 3.11 | Python 3.12 | Python 3.13 |
|---------------------|-------------|-------------|-------------|
| 0.1.x - 0.5.x | Supported | Supported | Not tested |
| 0.6.x - 0.8.x | Supported | Supported | Not tested |
| 0.9.x | Not supported | Supported | Supported |
| 0.10.x | Not supported | Required (3.12+) | Supported |

### Dependency Versions

| Dependency | 0.8.x | 0.9.x | 0.10.x |
|------------|-------|-------|--------|
| FastAPI | >=0.100.0 | >=0.110.0 | >=0.115.0 |
| Pydantic | >=2.0.0 | >=2.5.0 | >=2.10.0 |
| pydantic-settings | >=2.0.0 | >=2.1.0 | >=2.7.0 |
| structlog | >=23.0.0 | >=23.2.0 | >=24.0.0 |
| scikit-learn (optional) | >=1.3.0 | >=1.3.0 | >=1.3.0 |
| qiskit (optional) | N/A | >=0.45.0 | >=1.0.0 |

### Feature Availability

| Feature | 0.8.x | 0.9.x | 0.10.x |
|---------|-------|-------|--------|
| Plugin system | Basic | Full | Full |
| Event bus | Basic | Full | Full |
| Runtime abstraction | Partial | Full | Full |
| Prompt security | Rules only | Rules only | Rules + ML |
| Classical ML | Limited | Full | Full |
| Quantum analysis | Not available | Basic | Full |
| Hybrid fusion | Not available | Not available | Full |
| Observability | Not available | Basic | Full |

---

## Breaking Changes Between Versions

### 0.5.x to 0.6.x

**Module 6 Introduction**

- Quantum package added under `q_guardian.quantum`
- `QuantumConfig` replaces earlier placeholder config
- New dependency: `qiskit>=1.0.0` (optional)

**Migration:**

```python
# Before (0.5.x)
from q_guardian import Guardian
guardian = Guardian()

# After (0.6.x) -- no changes needed, quantum is opt-in
from q_guardian import Guardian
from q_guardian.quantum import QuantumConfig

config = FrameworkConfig(
    quantum=QuantumConfig(enabled=True)
)
guardian = Guardian(config=config)
```

### 0.6.x to 0.7.x

**Adaptive Trust Management**

- `SecurityContext` gains new methods: `update_trust()`, `update_risk()`
- New `TrustManager` available via `guardian.trust_manager`
- No breaking API changes

### 0.7.x to 0.8.x

**Advanced Policy Engine**

- `PolicyConfig` gains `enforcement_mode` field
- `guardian.enforce_policy()` method added
- `PolicyViolation` event added

**Migration:**

```python
# Before (0.7.x)
config = FrameworkConfig()

# After (0.8.x)
config = FrameworkConfig(
    policy=PolicyConfig(enforcement_mode="enforce")
)
```

### 0.8.x to 0.9.x

**Autonomous Incident Response**

- `Plugin.health()` return type changed from `bool` to `dict[str, Any]`
- `Plugin.configuration()` added as optional method
- `RuntimeContext` gains `to_snapshot()` method
- `ObservabilityPlugin` introduced
- Python 3.11 support dropped

**Migration:**

```python
# Before (0.8.x)
class MyPlugin(Plugin):
    def health(self) -> bool:
        return True

# After (0.9.x)
class MyPlugin(Plugin):
    def health(self) -> dict[str, Any]:
        return {"status": "healthy", "plugin": self.name}
```

### 0.9.x to 0.10.x

**Major Release**

- `FrameworkConfig` restructured with nested config classes
- `PluginConfig` replaces flat `enabled` flag
- `RuntimeConfig` replaces individual runtime settings
- `PromptSecurityConfig` now available for scanner-specific config
- `MLConfig` extended with `model_storage_path` and `random_state`
- `QuantumConfig` extended with full backend and fusion settings
- `HybridFusionEngine` and fusion strategies introduced
- `from_settings()` classmethod added to `FrameworkConfig`

---

## Migration from 0.8.x to 1.0.0

### Step 1: Update Python Version

Ensure Python 3.12+ is installed:

```bash
python --version  # Must be 3.12+
```

### Step 2: Update Dependencies

```bash
pip install --upgrade q-guardian
```

Or with optional features:

```bash
pip install --upgrade "q-guardian[ml]"
pip install --upgrade "q-guardian[ml,quantum]"
```

### Step 3: Update Configuration

**Before (0.8.x):**

```python
from q_guardian import Guardian, FrameworkConfig

config = FrameworkConfig()
guardian = Guardian(config=config)
```

**After (1.0.0):**

```python
from q_guardian import Guardian, FrameworkConfig
from q_guardian.framework.config import RuntimeConfig, PolicyConfig

config = FrameworkConfig(
    runtime=RuntimeConfig(
        max_concurrent_agents=100,
        enable_caching=True,
    ),
    policy=PolicyConfig(
        enforcement_mode="enforce",
    ),
)
guardian = Guardian(config=config)
```

### Step 4: Update Plugin Health Methods

**Before (0.8.x):**

```python
class MyPlugin(Plugin):
    def health(self) -> bool:
        return True
```

**After (1.0.0):**

```python
class MyPlugin(Plugin):
    def health(self) -> dict[str, Any]:
        return {"status": "healthy", "plugin": self.name}
```

### Step 5: Update Environment Variables

If using `.env` files, ensure variable names match the new settings classes:

```bash
# Old (may still work due to backward compatibility)
MONGODB_URL=mongodb://localhost:27017
SECRET_KEY=secret

# Recommended (explicit)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=q_guardian
SECRET_KEY=your-secret-key
```

### Step 6: Update Event Subscriptions

Event type names are unchanged, but verify any custom event subscriptions still work.

### Step 7: Update ML Configuration

If using ML features:

```python
# Before (0.8.x)
from q_guardian.ml import ThreatAnalysisPlugin

plugin = ThreatAnalysisPlugin()

# After (1.0.0)
from q_guardian.ml import ThreatAnalysisPlugin, MLConfig

config = MLConfig(
    enabled=True,
    anomaly_threshold=0.5,
    model_storage_path="models/ml",
)
plugin = ThreatAnalysisPlugin(config=config)
```

### Step 8: Add Quantum Support (Optional)

```python
from q_guardian.quantum import QuantumConfig, QuantumAnalysisPlugin

quantum_config = QuantumConfig(
    enabled=True,
    backend="simulator",
    num_qubits=5,
)

quantum_plugin = QuantumAnalysisPlugin(config=quantum_config)
guardian.register_plugin(quantum_plugin)
```

### Step 9: Verify

```bash
# Run tests
pytest tests/ -v

# Check types
mypy src/q_guardian/

# Check linting
ruff check src/ tests/
```

---

## Deprecated APIs

### 0.9.x Deprecations

| Deprecated | Replacement | Removed In |
|------------|-------------|------------|
| `Plugin.health() -> bool` | `Plugin.health() -> dict[str, Any]` | 1.0.0 |
| `FrameworkConfig(runtime_enabled=True)` | `FrameworkConfig(runtime=RuntimeConfig(...))` | 1.0.0 |

### 0.8.x Deprecations

| Deprecated | Replacement | Removed In |
|------------|-------------|------------|
| `ThreatAnalysisPlugin(config=None)` with flat settings | `ThreatAnalysisPlugin(config=MLConfig(...))` | 1.0.0 |
| Direct `ModelManager.register()` | `ModelManager.register_model()` | 0.9.0 |

### Upcoming Deprecations (Planned for 0.11.0)

| Deprecated | Replacement |
|------------|-------------|
| `guardian.events` property | `guardian.event_bus` (alias) |
| Flat `FrameworkConfig(**kwargs)` | Nested config classes |
| `PromptScannerPlugin` standalone | `ThreatAnalysisPlugin` (unified) |

### How to Check for Deprecations

Enable deprecation warnings:

```python
import warnings
warnings.filterwarnings("default", category=DeprecationWarning)
```

Or run with the `-Wd` flag:

```bash
python -Wd your_script.py
```
