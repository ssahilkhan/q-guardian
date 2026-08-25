# Plugin Development Guide

## Table of Contents

1. [Plugin Lifecycle](#plugin-lifecycle)
2. [Plugin Interface Requirements](#plugin-interface-requirements)
3. [Using Events and Hooks](#using-events-and-hooks)
4. [Plugin Configuration](#plugin-configuration)
5. [Plugin Testing](#plugin-testing)
6. [Publishing Plugins](#publishing-plugins)
7. [Example Plugin Walkthrough](#example-plugin-walkthrough)

---

## Plugin Lifecycle

Every plugin follows a well-defined lifecycle managed by the framework:

```
1. Registration
   guardian.register_plugin(plugin)
   -> PluginStatus.REGISTERED

2. Initialization
   plugin.initialize(context)
   -> PluginStatus.INITIALIZING -> PluginStatus.REGISTERED
   Setup resources, register event handlers, register hooks.

3. Starting
   plugin.start()
   -> PluginStatus.RUNNING
   Begin accepting work.

4. Running
   Plugin processes requests, publishes events.

5. Stopping
   plugin.stop()
   -> PluginStatus.STOPPED
   Release resources, close connections.
```

### Lifecycle State Diagram

```
REGISTERED --initialize()--> INITIALIZING --success--> REGISTERED
                                    |
                                    +--error--> ERROR

REGISTERED --start()--> RUNNING --stop()--> STOPPED

Any state --disable()--> DISABLED
DISABLED --enable()--> REGISTERED
```

### Error Handling During Lifecycle

If a plugin fails during initialization or start:
- The plugin is marked as `ERROR`
- Remaining plugins continue their lifecycle
- The framework logs the error with full traceback

Plugins should handle their own errors gracefully and only raise for critical failures.

---

## Plugin Interface Requirements

### Required Properties

```python
from q_guardian.plugins.base import Plugin


class MyPlugin(Plugin):
    @property
    def name(self) -> str:
        """Unique identifier for this plugin. Must not conflict with other plugins."""
        return "my-unique-plugin"

    @property
    def version(self) -> str:
        """Semantic version string."""
        return "1.0.0"
```

### Required Methods

```python
async def initialize(self, context: FrameworkContext) -> None:
    """Called once after registration.

    The FrameworkContext provides access to:
    - context.event_bus: Publish and subscribe to events
    - context.hook_manager: Register lifecycle hooks
    - context.plugin_registry: Access other plugins
    - context.config: Framework configuration
    - context.logger: Structured logger
    """
    self._context = context


async def start(self) -> None:
    """Called after all plugins are initialized.

    Begin accepting work, start background tasks, etc.
    """
    pass


async def stop(self) -> None:
    """Called during framework shutdown.

    Release resources, close connections, cancel tasks.
    """
    pass
```

### Optional Properties

```python
@property
def author(self) -> str:
    """Plugin author name."""
    return "Your Name"


@property
def description(self) -> str:
    """Brief description of plugin functionality."""
    return "Does something useful"


@property
def dependencies(self) -> list[str]:
    """List of plugin names this plugin depends on."""
    return ["prompt-scanner"]


@property
def interfaces(self) -> list[str]:
    """Interface identifiers this plugin implements.

    Used by Guardian to route method calls.
    Common interfaces: prompt_scanner, threat_detector,
    runtime_monitor, risk_engine, policy_engine
    """
    return ["my_interface"]
```

### Optional Methods

```python
def health(self) -> dict[str, Any]:
    """Return health status information."""
    return {"status": "healthy", "plugin": self.name}


def configuration(self) -> dict[str, Any]:
    """Describe configuration options."""
    return {"sensitivity": {"type": "str", "default": "medium"}}
```

---

## Using Events and Hooks

### Publishing Events

```python
from q_guardian.events.base import Event


class ScanComplete(Event):
    def __init__(self, result: dict, source: str = "my-plugin"):
        self.id = str(uuid4())
        self.timestamp = datetime.now()
        self.source = source
        self.data = result
        self._propagation_stopped = False

    @property
    def event_type(self) -> str:
        return "my_plugin.scan_complete"

    def stop_propagation(self):
        self._propagation_stopped = True

    @property
    def propagation_stopped(self):
        return self._propagation_stopped


class MyPlugin(Plugin):
    async def initialize(self, context: FrameworkContext) -> None:
        self._event_bus = context.event_bus

    async def do_work(self):
        result = {"status": "done"}
        event = ScanComplete(result=result, source=self.name)
        await self._event_bus.publish(event)
```

### Subscribing to Events

```python
class MyPlugin(Plugin):
    async def initialize(self, context: FrameworkContext) -> None:
        self._event_bus = context.event_bus
        await self._event_bus.subscribe("threat.detected", self._on_threat)
        await self._event_bus.subscribe("threat.*", self._on_any_threat)
        await self._event_bus.subscribe("*", self._on_any_event)

    async def _on_threat(self, event):
        print(f"Specific threat: {event.data}")

    async def _on_any_threat(self, event):
        print(f"Any threat event: {event.event_type}")

    async def _on_any_event(self, event):
        print(f"Event received: {event.event_type}")
```

### Registering Hooks

```python
class MyPlugin(Plugin):
    async def initialize(self, context: FrameworkContext) -> None:
        self._hook_manager = context.hook_manager
        await self._hook_manager.register_hook("before_prompt", self._validate)
        await self._hook_manager.register_hook("after_prompt", self._post_process)

    async def _validate(self, prompt: str = "", **kwargs):
        """Pre-scan validation hook."""
        if len(prompt) > 100000:
            return {"blocked": True, "reason": "Too long"}
        return {"blocked": False}

    async def _post_process(self, prompt: str = "", results: dict = None, **kwargs):
        """Post-scan processing hook."""
        if results:
            for name, result in results.items():
                print(f"Plugin {name} returned: {result}")
        return {"processed": True}
```

### Unsubscribing

```python
async def stop(self) -> None:
    await self._event_bus.unsubscribe(self._subscription_id)
    await self._hook_manager.unregister_hook("before_prompt", self._validate)
```

---

## Plugin Configuration

### Using Framework Config

```python
from q_guardian.framework.config import FrameworkConfig, PluginConfig


class MyPluginConfig(PluginConfig):
    sensitivity: str = "medium"
    max_items: int = 100
    enable_caching: bool = True


class MyPlugin(Plugin):
    def __init__(self, config: MyPluginConfig | None = None):
        self._config = config or MyPluginConfig()

    async def initialize(self, context: FrameworkContext) -> None:
        # Access per-plugin config overrides
        overrides = context.config.get_plugin_config(self.name)
        if overrides:
            self._config = MyPluginConfig(**overrides)
```

### Configuration via FrameworkConfig

```python
config = FrameworkConfig(
    plugin_configs={
        "my-plugin": {
            "sensitivity": "high",
            "max_items": 200,
            "enable_caching": False,
        }
    }
)

guardian = Guardian(config=config)
guardian.register_plugin(MyPlugin(config=MyPluginConfig(sensitivity="high")))
await guardian.start()
```

### Environment-Based Configuration

```python
import os


class MyPlugin(Plugin):
    async def initialize(self, context: FrameworkContext) -> None:
        self._api_key = os.environ.get("MY_PLUGIN_API_KEY", "")
        self._debug = os.environ.get("MY_PLUGIN_DEBUG", "false").lower() == "true"
```

---

## Plugin Testing

### Basic Plugin Test

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from q_guardian.framework.context import FrameworkContext
from q_guardian.events.bus import EventBus
from q_guardian.hooks.manager import HookManager
from my_package import MyPlugin


@pytest.fixture
def plugin():
    return MyPlugin()


@pytest.fixture
def context():
    ctx = MagicMock(spec=FrameworkContext)
    ctx.event_bus = EventBus()
    ctx.hook_manager = HookManager()
    ctx.config = FrameworkConfig()
    ctx.logger = MagicMock()
    return ctx


@pytest.mark.asyncio
async def test_plugin_initialization(plugin, context):
    await plugin.initialize(context)
    assert plugin._context is not None


@pytest.mark.asyncio
async def test_plugin_start(plugin, context):
    await plugin.initialize(context)
    await plugin.start()
    assert plugin.health()["status"] == "healthy"


@pytest.mark.asyncio
async def test_plugin_stop(plugin, context):
    await plugin.initialize(context)
    await plugin.start()
    await plugin.stop()


@pytest.mark.asyncio
async def test_plugin_event_publishing(plugin, context):
    await plugin.initialize(context)

    received = []

    async def handler(event):
        received.append(event)

    await context.event_bus.subscribe("my_plugin.scan_complete", handler)
    await plugin.do_work()

    assert len(received) == 1
```

### Integration Testing with Guardian

```python
import pytest
from q_guardian import Guardian, FrameworkConfig
from my_package import MyPlugin


@pytest.mark.asyncio
async def test_plugin_with_guardian():
    guardian = Guardian()
    guardian.register_plugin(MyPlugin())
    await guardian.start()

    plugins = guardian.list_plugins()
    plugin_names = [p.name for p in plugins]
    assert "my-plugin" in plugin_names

    result = await guardian.scan_prompt("test prompt")
    assert result is not None

    await guardian.shutdown()
```

---

## Publishing Plugins

### Package Structure

```
my-q-guardian-plugin/
    pyproject.toml
    README.md
    src/
        my_package/
            __init__.py
            plugin.py
            models.py
```

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=75.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "my-q-guardian-plugin"
version = "1.0.0"
description = "A custom Q-Guardian plugin"
requires-python = ">=3.12"
dependencies = [
    "q-guardian>=1.0.0",
]

[project.entry-points."q_guardian.plugins"]
my_plugin = "my_package:MyPlugin"
```

### Installing Published Plugins

```bash
pip install my-q-guardian-plugin
```

Plugins registered via entry points are auto-discovered when `FrameworkConfig.plugins.enabled` is `true`.

---

## Example Plugin Walkthrough

### Goal

Create a custom content filter plugin that blocks prompts containing profanity or sensitive data patterns.

### Step 1: Define Models

```python
# src/content_filter/models.py
from pydantic import BaseModel
from enum import Enum


class FilterDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"


class FilterResult(BaseModel):
    decision: FilterDecision
    matched_patterns: list[str]
    confidence: float
```

### Step 2: Implement the Plugin

```python
# src/content_filter/plugin.py
import re
from typing import Any
from q_guardian.plugins.base import Plugin
from q_guardian.framework.context import FrameworkContext


class ContentFilterPlugin(Plugin):
    def __init__(self, patterns: list[str] | None = None):
        self._patterns = patterns or [
            r"\b\d{3}-\d{2}-\d{4}\b",  # SSN pattern
            r"\b\d{16}\b",  # Credit card
            r"(?i)social\s+security",
        ]
        self._compiled = [re.compile(p) for p in self._patterns]
        self._context: FrameworkContext | None = None

    @property
    def name(self) -> str:
        return "content-filter"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def author(self) -> str:
        return "Custom Developer"

    @property
    def description(self) -> str:
        return "Filters prompts for sensitive data patterns"

    @property
    def interfaces(self) -> list[str]:
        return ["prompt_scanner"]

    async def initialize(self, context: FrameworkContext) -> None:
        self._context = context
        await context.event_bus.subscribe("threat.detected", self._on_threat)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def scan_prompt(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        matched = []
        for i, pattern in enumerate(self._compiled):
            if pattern.search(prompt):
                matched.append(self._patterns[i])

        decision = "block" if matched else "allow"
        confidence = min(len(matched) * 0.3, 1.0)

        return {
            "plugin": self.name,
            "decision": decision,
            "matched_patterns": matched,
            "confidence": confidence,
        }

    async def _on_threat(self, event) -> None:
        if event.data.get("severity") in ("high", "critical"):
            print(f"High severity threat: {event.data}")

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "plugin": self.name,
            "pattern_count": len(self._compiled),
        }
```

### Step 3: Write Tests

```python
# tests/test_content_filter.py
import pytest
from content_filter.plugin import ContentFilterPlugin


@pytest.fixture
def plugin():
    return ContentFilterPlugin()


@pytest.mark.asyncio
async def test_allow_safe_prompt(plugin):
    result = await plugin.scan_prompt("What is the weather?")
    assert result["decision"] == "allow"
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_block_ssn_pattern(plugin):
    result = await plugin.scan_prompt("My SSN is 123-45-6789")
    assert result["decision"] == "block"
    assert len(result["matched_patterns"]) == 1


@pytest.mark.asyncio
async def test_block_credit_card(plugin):
    result = await plugin.scan_prompt("Card number: 4111111111111111")
    assert result["decision"] == "block"
```

### Step 4: Publish

```toml
# pyproject.toml
[project.entry-points."q_guardian.plugins"]
content_filter = "content_filter:ContentFilterPlugin"
```

```bash
pip install -e .
```

The plugin is now auto-discovered and loaded by Q-Guardian.
