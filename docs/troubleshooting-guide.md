# Troubleshooting Guide

## Table of Contents

1. [Common Errors and Solutions](#common-errors-and-solutions)
2. [Performance Issues](#performance-issues)
3. [Configuration Problems](#configuration-problems)
4. [Integration Issues](#integration-issues)
5. [Debug Mode](#debug-mode)

---

## Common Errors and Solutions

### Import Errors

**Error:** `ModuleNotFoundError: No module named 'q_guardian'`

**Cause:** Package not installed or wrong Python environment.

**Solution:**

```bash
# Verify installation
pip show q-guardian

# If not found, install from source
pip install -e .

# Ensure correct Python version
python --version  # Must be 3.12+
```

**Error:** `ModuleNotFoundError: No module named 'qiskit'`

**Cause:** Quantum dependencies not installed.

**Solution:**

```bash
pip install q-guardian[quantum]
# or
pip install qiskit qiskit-machine-learning qiskit-aer
```

**Error:** `ModuleNotFoundError: No module named 'sklearn'`

**Cause:** ML dependencies not installed.

**Solution:**

```bash
pip install q-guardian[ml]
# or
pip install scikit-learn numpy
```

### Plugin Errors

**Error:** `ValidationException: Plugin 'xxx' is already registered`

**Cause:** Attempting to register a plugin with a name that already exists.

**Solution:**

```python
# Check if plugin is already registered
if guardian.plugins.has_plugin("my-plugin"):
    guardian.plugins.unregister_plugin("my-plugin")

guardian.register_plugin(MyPlugin())
```

**Error:** `KeyError: Plugin 'xxx' is not registered`

**Cause:** Attempting to access a plugin that was not registered.

**Solution:**

```python
# List all registered plugins
plugins = guardian.list_plugins()
for p in plugins:
    print(p.name)

# Check before accessing
if guardian.plugins.has_plugin("my-plugin"):
    plugin = guardian.get_plugin("my-plugin")
```

### State Machine Errors

**Error:** `StateTransitionError: Cannot transition from STOPPED to RUNNING`

**Cause:** Attempting to start a framework that was already shut down.

**Solution:**

```python
# Create a new Guardian instance after shutdown
guardian = Guardian()
await guardian.start()

# ... use framework ...

await guardian.shutdown()

# To restart, create a new instance
guardian = Guardian()
await guardian.start()
```

### Database Errors

**Error:** `ServerSelectionTimeoutError: ...`

**Cause:** MongoDB is not running or connection URL is incorrect.

**Solution:**

```bash
# Check MongoDB status
mongosh --eval "db.adminCommand('ping')"

# Verify connection string
echo $MONGODB_URL

# Framework works without MongoDB -- disable if not needed
# Just ignore the warning in logs
```

### Event Bus Errors

**Error:** Handler exceptions during event publishing

**Cause:** An event handler raised an exception.

**Solution:** Handler errors are isolated and logged. Check logs for the specific handler error. Ensure handlers catch their own exceptions:

```python
async def safe_handler(event):
    try:
        # Process event
        pass
    except Exception as e:
        logger.error("handler_error", error=str(e))
```

---

## Performance Issues

### Slow Scan Latency

**Symptom:** Prompt scanning takes longer than expected.

**Diagnosis:**

```python
import time

start = time.monotonic()
result = await guardian.scan_prompt("test prompt")
elapsed_ms = (time.monotonic() - start) * 1000
print(f"Scan took {elapsed_ms:.1f}ms")
```

**Solutions:**

1. Reduce ML model complexity:
```python
config = MLConfig(anomaly_threshold=0.6)  # Less sensitive = faster
```

2. Disable ML if not needed:
```python
config = MLConfig(enabled=False)
```

3. Reduce quantum shots:
```python
config = QuantumConfig(shots=256)  # Default is 1024
```

4. Enable caching:
```python
config = FrameworkConfig(runtime={"enable_caching": True})
```

### High Memory Usage

**Symptom:** Application consumes excessive memory.

**Diagnosis:**

```python
import psutil
import os

process = psutil.Process(os.getpid())
memory_mb = process.memory_info().rss / 1024 / 1024
print(f"Memory: {memory_mb:.1f} MB")
```

**Solutions:**

1. Reduce model storage:
```python
config = MLConfig(model_storage_path="/tmp/models")
```

2. Limit concurrent agents:
```python
config = FrameworkConfig(runtime={"max_concurrent_agents": 50})
```

3. Reduce MongoDB connection pool:
```bash
MONGODB_MAX_POOL_SIZE=5
```

### High CPU Usage

**Solutions:**

1. Reduce ML ensemble size:
```python
ensemble = EnsembleDetector(detectors=[single_detector])
```

2. Use lighter quantum backend:
```python
config = QuantumConfig(backend="simulator", num_qubits=3)
```

3. Reduce feature extraction complexity by customizing keywords list.

---

## Configuration Problems

**Error:** `ValidationError: 1 validation error for AppSettings`

**Cause:** Environment variable has invalid value.

**Solution:**

```bash
# Check current environment variables
env | grep APP_

# Ensure correct types
APP_PORT=8000          # Must be integer
APP_DEBUG=true         # Must be boolean (true/false)
APP_ENVIRONMENT=production  # Must be development|testing|production
```

**Error:** `ValueError: SECRET_KEY must be changed in production!`

**Cause:** Default secret key used in production environment.

**Solution:**

```bash
# Generate a secure key
SECRET_KEY=$(openssl rand -hex 32)

# Or use Python
python -c "import secrets; print(secrets.token_hex(32))"
```

**Error:** YAML configuration fails to load

**Cause:** PyYAML not installed.

**Solution:**

```bash
pip install pyyaml
```

**Error:** CORS errors in browser

**Cause:** Origin not in allowed list.

**Solution:**

```bash
# Add your frontend origin
CORS_ORIGINS=["http://localhost:3000","https://your-app.com"]
```

---

## Integration Issues

### LangGraph Integration

**Problem:** Adapter not connecting to LangGraph agent.

**Solution:**

```python
from q_guardian.adapters import LangGraphAdapter

adapter = LangGraphAdapter()
guardian.register_adapter(adapter)

# Verify adapter registration
registered = guardian.get_adapter("langgraph")
print(f"Adapter: {registered.name}")
```

### CrewAI Integration

**Problem:** Adapter not connecting to CrewAI agent.

**Solution:**

```python
from q_guardian.adapters import CrewAIAdapter

adapter = CrewAIAdapter()
guardian.register_adapter(adapter)
```

### Custom Plugin Not Loading

**Problem:** Entry-point plugin not auto-discovered.

**Solution:**

1. Verify pyproject.toml entry point:
```toml
[project.entry-points."q_guardian.plugins"]
my_plugin = "my_package:MyPlugin"
```

2. Reinstall the package:
```bash
pip install -e .
```

3. Check discovery is enabled:
```python
config = FrameworkConfig(plugins={"enabled": True})
```

### MongoDB Connection Pool Exhausted

**Symptom:** `ConnectionPool exhaustion` in logs.

**Solution:**

```bash
# Increase pool size
MONGODB_MAX_POOL_SIZE=50

# Or reduce concurrent operations
config = FrameworkConfig(runtime={"max_concurrent_agents": 50})
```

---

## Debug Mode

### Enabling Debug Logging

```bash
APP_DEBUG=true
APP_LOG_LEVEL=DEBUG
APP_LOG_FORMAT=console
```

Or programmatically:

```python
from q_guardian.config.settings import get_settings
import os

os.environ["APP_DEBUG"] = "true"
os.environ["APP_LOG_LEVEL"] = "DEBUG"
os.environ["APP_LOG_FORMAT"] = "console"
```

### Debug Output

With `APP_LOG_FORMAT=console`, logs are human-readable:

```
12:00:00 [info] prompt_scanner_initialized plugin=prompt-scanner
12:00:00 [info] prompt_scanner_started rules=42
12:00:00 [debug] prompt_received source=api
12:00:00 [info] prompt_findings finding_count=2 decision=block risk_score=0.85
```

### Inspecting Plugin State

```python
# List all plugins and their status
plugins = guardian.list_plugins()
for p in plugins:
    print(f"{p.name} v{p.version}: {p.status.value}")

# Check health of all plugins
health = await guardian.plugins.health_check()
for name, status in health.items():
    print(f"{name}: {status}")
```

### Inspecting Event Bus

```python
# Check subscriber counts
from q_guardian.events import EventBus

# View all hooks
hooks = guardian._hook_manager.list_hooks()
for name, count in hooks.items():
    print(f"Hook '{name}': {count} handlers")
```

### Inspecting Runtime Context

```python
rt = guardian.runtime
if rt:
    print(f"Agent: {rt.agent_id}")
    print(f"Session: {rt.session_id}")
    print(f"Blocked: {rt.is_blocked}")
    print(f"Tool count: {rt.tool_count}")
    print(f"Threat count: {rt.threat_count}")

    # Take snapshot
    snapshot = rt.to_snapshot()
    print(snapshot)
```

### Running Tests in Debug Mode

```bash
# Verbose output with full tracebacks
pytest tests/ -v --tb=long

# Stop on first failure
pytest tests/ -x

# Run specific test
pytest tests/unit/test_event_bus.py::TestEventBus::test_subscribe -v -s
```
