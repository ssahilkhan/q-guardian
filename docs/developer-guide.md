# Q-Guardian Developer Guide

## Table of Contents

1. [Development Environment Setup](#development-environment-setup)
2. [Running Tests](#running-tests)
3. [Code Style and Conventions](#code-style-and-conventions)
4. [Architecture Overview](#architecture-overview)
5. [Adding New Modules](#adding-new-modules)
6. [Testing Patterns](#testing-patterns)
7. [Submitting Changes](#submitting-changes)

---

## Development Environment Setup

### Prerequisites

- Python 3.12+
- Git
- pip or Poetry
- MongoDB (for integration tests)

### Clone and Install

```bash
git clone https://github.com/ssahilkhan/q-guardian.git
cd q-guardian
pip install -e ".[dev]"
```

This installs all development dependencies:

- `pytest` and `pytest-asyncio` for testing
- `ruff` for linting
- `mypy` for type checking
- `pre-commit` for git hooks
- `mongomock` for test database mocking

### Pre-commit Hooks

```bash
pre-commit install
```

This runs ruff and mypy checks on every commit.

### IDE Configuration

For VS Code, create `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.linting.mypyEnabled": true,
    "python.linting.enabled": true,
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true
    },
    "python.analysis.typeCheckingMode": "strict"
}
```

### Environment Variables for Development

```bash
APP_ENVIRONMENT=development
APP_DEBUG=true
APP_LOG_LEVEL=DEBUG
APP_LOG_FORMAT=console
MONGODB_URL=mongodb://localhost:27017
```

---

## Running Tests

### Full Test Suite

```bash
pytest tests/ -v
```

### Fast Subset (Excluding Slow Quantum Tests)

```bash
pytest tests/ --ignore=tests/unit/test_quantum_qsvm.py \
              --ignore=tests/unit/test_quantum_kernel_trainer.py \
              --ignore=tests/unit/test_quantum_inference_engine.py -v
```

### Run with Coverage

```bash
pytest tests/ -v --cov=q_guardian --cov-report=html
```

### Run Specific Module Tests

```bash
# Runtime models
pytest tests/unit/test_runtime_models.py -v

# Event system
pytest tests/unit/test_event_bus.py -v

# Fusion strategies
pytest tests/unit/test_fusion_strategies.py -v

# ML models
pytest tests/unit/test_ml_models.py -v
```

### Run by Marker

```bash
# Unit tests only
pytest -m unit -v

# Integration tests only
pytest -m integration -v

# Exclude slow tests
pytest -m "not slow" -v
```

### Test Counts by Module

| Test Suite | Tests |
|-----------|-------|
| Modules 1-5 (Enterprise, Framework, Runtime, Security, ML) | 501 |
| Module 6 Phase 1 (Quantum Infrastructure) | 168 |
| Module 6 Phase 2 (Quantum Learning) | 170 |
| Module 6 Phase 3 (Hybrid Fusion) | 129 |
| **Total** | **968** |

---

## Code Style and Conventions

### Formatting and Linting

Q-Guardian uses ruff for both formatting and linting. Configuration is in `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]
```

Run ruff manually:

```bash
# Check for issues
ruff check src/ tests/

# Auto-fix issues
ruff check --fix src/ tests/

# Format code
ruff format src/ tests/
```

### Type Checking

mypy is configured for strict mode:

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
no_implicit_optional = true
plugins = ["pydantic.mypy"]
```

Run mypy:

```bash
mypy src/q_guardian/
```

### Naming Conventions

- **Classes:** PascalCase (`FrameworkConfig`, `PromptScannerPlugin`)
- **Functions/Methods:** snake_case (`scan_prompt`, `register_plugin`)
- **Constants:** UPPER_SNAKE_CASE (`API_V1_PREFIX`)
- **Private attributes:** Leading underscore (`_config`, `_event_bus`)
- **Files:** snake_case (`framework_state.py`, `model_manager.py`)

### Import Order

Imports are organized by ruff isort in this order:

1. Standard library
2. Third-party packages
3. First-party packages (`q_guardian`)
4. Local imports within the same module

### Docstrings

Use Google-style docstrings for all public methods:

```python
async def scan_prompt(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
    """Scan a prompt through registered prompt scanners.

    Args:
        prompt: The prompt text to scan.
        **kwargs: Additional context for scanning.

    Returns:
        Aggregated scan results from all scanners.

    Raises:
        ValueError: If the prompt is empty.
    """
```

### Async/Await

All I/O operations and plugin lifecycle methods are async. Never use `asyncio.run()` inside library code. Only test files and entry points use `asyncio.run()`.

### Pydantic Models

Use Pydantic v2 for all data models:

```python
from pydantic import BaseModel, Field


class PromptSecurityConfig(BaseModel):
    enabled: bool = Field(default=True, description="Enable prompt scanning")
    sensitivity: str = Field(default="medium", description="Sensitivity level")
```

---

## Architecture Overview

### Layered Design

Q-Guardian follows Clean Architecture with strict dependency rules:

```
Layer 1: Enterprise Foundation (FastAPI, middleware, database)
    |
Layer 2: Framework Core (EventBus, Plugin, HookManager)
    |
Layer 3: Runtime Abstraction (Agent, Session, Tool, Memory)
    |
Layer 4: Prompt Security Engine (Normalizer, Validator, Rules)
    |
Layer 5: Classical ML Security (IsolationForest, RandomForest, XGBoost)
    |
Layer 6: Quantum Intelligence (Backends, FeatureMaps, QSVM, Fusion)
```

Outer layers may depend on inner layers. Inner layers must never depend on outer layers.

### Key Directories

```
src/q_guardian/
    api/            # FastAPI routes and application factory
    core/           # State machine and constants
    events/         # EventBus and standard events
    hooks/          # HookManager
    plugins/        # Plugin ABC and PluginRegistry
    adapters/       # AI framework adapters
    runtime/        # Agent, Session, Context, Managers
    framework/      # FrameworkConfig and FrameworkContext
    sdk/            # Guardian facade (public API)
    security/       # Prompt security pipeline
    ml/             # Classical ML models and pipeline
    quantum/        # Quantum backends, models, and fusion
    config/         # pydantic-settings configuration
    database/       # MongoDB async client
    logging/        # Structured logging setup
    middleware/      # HTTP middleware
    exceptions/     # Exception hierarchy
    observability/  # Metrics, tracing, analytics, alerts
    utils/          # Utility functions
```

### Module Boundaries

Each module has its own `__init__.py` that re-exports public APIs. Import from the module level, not from internal files:

```python
# Correct
from q_guardian.ml import IsolationForestDetector
from q_guardian.quantum import QuantumConfig

# Avoid
from q_guardian.ml.models.anomaly import IsolationForestDetector
```

---

## Adding New Modules

### Step 1: Create the Module Directory

```
src/q_guardian/new_module/
    __init__.py
    models.py
    enums.py
    config.py
    plugin.py
    exceptions.py
```

### Step 2: Define Public API

```python
# src/q_guardian/new_module/__init__.py
from q_guardian.new_module.models import NewModel
from q_guardian.new_module.config import NewModuleConfig

__all__ = ["NewModel", "NewModuleConfig"]
```

### Step 3: Create a Plugin

```python
# src/q_guardian/new_module/plugin.py
from q_guardian.plugins.base import Plugin
from q_guardian.framework.context import FrameworkContext


class NewModulePlugin(Plugin):
    @property
    def name(self) -> str:
        return "new-module"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def interfaces(self) -> list[str]:
        return ["new_module_interface"]

    async def initialize(self, context: FrameworkContext) -> None:
        self._context = context

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass
```

### Step 4: Add to Public Exports

```python
# src/q_guardian/__init__.py
from q_guardian.new_module import NewModel, NewModuleConfig
```

### Step 5: Write Tests

```
tests/unit/test_new_module_models.py
tests/unit/test_new_module_plugin.py
tests/integration/test_new_module_integration.py
```

---

## Testing Patterns

### Unit Test Structure

```python
import pytest
from q_guardian.security import PromptNormalizer


class TestPromptNormalizer:
    def setup_method(self):
        self.normalizer = PromptNormalizer()

    def test_normalize_basic(self):
        result = self.normalizer.normalize("Hello World")
        assert result == "hello world"

    def test_normalize_whitespace(self):
        result = self.normalizer.normalize("  Hello   World  ")
        assert result == "hello world"
```

### Async Tests

```python
import pytest
from q_guardian import Guardian, Agent


@pytest.mark.asyncio
async def test_guardian_workflow():
    guardian = Guardian()
    await guardian.start()

    agent = Agent(name="test", id="test-1", framework="langgraph")
    guardian.set_agent(agent)

    session = await guardian.create_session()
    assert session is not None

    await guardian.close_session()
    await guardian.shutdown()
```

### Using Fixtures

```python
import pytest
from q_guardian import Guardian, FrameworkConfig


@pytest.fixture
async def guardian():
    config = FrameworkConfig()
    g = Guardian(config=config)
    await g.start()
    yield g
    await g.shutdown()


@pytest.mark.asyncio
async def test_with_guardian(guardian):
    result = await guardian.scan_prompt("Hello")
    assert result is not None
```

### Mocking

```python
from unittest.mock import AsyncMock, MagicMock
from q_guardian.plugins.base import Plugin


def create_mock_plugin(name="mock-plugin"):
    plugin = MagicMock(spec=Plugin)
    plugin.name = name
    plugin.version = "1.0.0"
    plugin.interfaces = ["prompt_scanner"]
    plugin.initialize = AsyncMock()
    plugin.start = AsyncMock()
    plugin.stop = AsyncMock()
    plugin.health.return_value = {"status": "healthy"}
    return plugin
```

---

## Submitting Changes

### Branch Naming

- `feature/add-new-scanner` -- New features
- `fix/resolve-plugin-init-error` -- Bug fixes
- `docs/update-user-guide` -- Documentation
- `refactor/clean-up-event-bus` -- Refactoring

### Commit Messages

Follow conventional commits:

```
feat(security): add new injection detection pattern
fix(ml): resolve model loading timeout
docs: update plugin development guide
refactor(runtime): simplify session manager
```

### Pull Request Process

1. Create a branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass: `pytest tests/ -v`
4. Ensure linting passes: `ruff check src/ tests/`
5. Ensure type checking passes: `mypy src/q_guardian/`
6. Update documentation if adding public APIs
7. Submit pull request with descriptive title and summary

### Review Checklist

- [ ] All tests pass
- [ ] No linting errors
- [ ] Type annotations are correct
- [ ] Public APIs are documented
- [ ] Changes follow existing patterns
- [ ] No secrets or credentials in code
- [ ] New modules added to `__init__.py` exports
