# Q-Guardian Framework Architecture

## Overview

Q-Guardian is a hybrid quantum-classical framework for runtime security of autonomous AI agents. It provides a modular, extensible architecture with plugin support, event-driven communication, and hooks for customization.

## Core Components

### 1. Framework State Machine

The `FrameworkStateMachine` manages the lifecycle of the framework:

```
INITIALIZING → RUNNING → STOPPED
    ↓            ↓
   ERROR ←──────┘
```

**States:**
- `INITIALIZING` - Framework is starting up
- `RUNNING` - Framework is operational
- `STOPPED` - Framework has been shut down
- `ERROR` - Framework encountered an error

### 2. Event Bus

The `EventBus` provides async pub/sub messaging:

```python
from q_guardian import EventBus, Event

bus = EventBus()

# Subscribe to events
await bus.subscribe("threat.detected", handler)

# Publish events
event = ThreatDetected(threat_type="prompt_injection", severity="high")
await bus.publish(event)

# Wildcard subscriptions
await bus.subscribe("threat.*", handler)  # receives all threat events
await bus.subscribe("*", handler)  # receives all events
```

### 3. Plugin System

Plugins are the primary extension mechanism:

```python
from q_guardian import Plugin, PluginMetadata


class MyPlugin(Plugin):
    @property
    def name(self) -> str:
        return "my-plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def initialize(self, context) -> None:
        # Setup resources
        pass

    async def start(self) -> None:
        # Start processing
        pass

    async def stop(self) -> None:
        # Cleanup resources
        pass
```

### 4. Hook Manager

Hooks allow pre/post processing of operations:

```python
from q_guardian import HookManager

hooks = HookManager()


# Register async hook
async def validate_prompt(context):
    prompt = context.get("prompt", "")
    if "ignore previous" in prompt.lower():
        context["blocked"] = True
    return context


hooks.register("before_scan", validate_prompt)

# Execute hooks
context = {"prompt": "Hello world"}
result = await hooks.execute("before_scan", context)
```

### 5. Adapters

Adapters integrate with AI frameworks:

```python
from q_guardian.adapters import LangGraphAdapter, CrewAIAdapter

# Register adapters
guardian.register_adapter(LangGraphAdapter())
guardian.register_adapter(CrewAIAdapter())

# Use adapter
adapter = guardian.get_adapter("langgraph")
```

## Framework Lifecycle

```python
from q_guardian import Guardian

# Initialize
guardian = Guardian()

# Start (initializes plugins, transitions to RUNNING)
await guardian.start()

# Use framework
await guardian.scan_prompt("Hello world")
adapter = guardian.get_adapter("langgraph")

# Shutdown
await guardian.shutdown()
```

## Configuration

The `FrameworkConfig` provides structured configuration:

```python
from q_guardian import FrameworkConfig

config = FrameworkConfig(
    runtime=RuntimeConfig(max_concurrent_scans=100, scan_timeout_seconds=30),
    policy=PolicyConfig(block_on_threat=True, min_severity="medium"),
)
```

## Directory Structure

```
src/q_guardian/
├── core/              # Core state management
├── events/            # Event bus and standard events
├── hooks/             # Hook manager
├── plugins/           # Plugin base classes and registry
├── adapters/          # AI framework adapters
├── framework/         # Configuration and context
├── sdk/               # Public SDK (Guardian facade)
└── __init__.py        # Public API re-exports
```
