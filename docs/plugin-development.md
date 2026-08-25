# Plugin Development Guide

## Overview

Plugins are the primary extension mechanism for Q-Guardian. They allow you to add custom security checks, integrations, and functionality to the framework.

## Creating a Plugin

### Basic Plugin

```python
from q_guardian import Plugin, PluginMetadata


class SecurityPlugin(Plugin):
    @property
    def name(self) -> str:
        return "security-scanner"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def initialize(self, context) -> None:
        """Setup resources and configuration."""
        self.config = context.config
        self.event_bus = context.event_bus

    async def start(self) -> None:
        """Start processing (optional)."""
        pass

    async def stop(self) -> None:
        """Cleanup resources (optional)."""
        pass

    async def health_check(self) -> bool:
        """Return True if plugin is healthy (optional)."""
        return True
```

### Plugin Lifecycle

1. **initialize()** - Called when plugin is registered. Setup config, connections.
2. **start()** - Called when framework starts. Begin processing.
3. **stop()** - Called when framework shuts down. Cleanup resources.
4. **health_check()** - Optional. Return health status.

## Registering Plugins

### Via SDK

```python
from q_guardian import Guardian

guardian = Guardian()
plugin = SecurityPlugin()

# Register (calls initialize)
guardian.register_plugin(plugin)

# Start framework (calls start on all plugins)
await guardian.start()

# Shutdown (calls stop on all plugins)
await guardian.shutdown()
```

### Via Plugin Registry

```python
from q_guardian.plugins import PluginRegistry

registry = PluginRegistry()
registry.register(plugin)
await registry.initialize_all(context)
await registry.start_all()
await registry.stop_all()
```

## Using Events

### Publishing Events

```python
from q_guardian.events.standard import ThreatDetected


class ThreatPlugin(Plugin):
    async def scan(self, prompt: str):
        if self.detect_threat(prompt):
            event = ThreatDetected(
                threat_type="prompt_injection", severity="high", source=self.name
            )
            await self.event_bus.publish(event)
```

### Subscribing to Events

```python
class ResponsePlugin(Plugin):
    async def initialize(self, context) -> None:
        await context.event_bus.subscribe("threat.detected", self.handle_threat)

    async def handle_threat(self, event):
        print(f"Threat detected: {event.threat_type}")
```

## Using Hooks

### Registering Hooks

```python
class ValidationPlugin(Plugin):
    async def initialize(self, context) -> None:
        context.hook_manager.register("before_scan", self.validate_prompt)

    async def validate_prompt(self, context):
        prompt = context.get("prompt", "")
        if len(prompt) > 10000:
            raise ValueError("Prompt too long")
        return context
```

### Executing Hooks

```python
class ScanPlugin(Plugin):
    async def scan(self, prompt: str):
        context = {"prompt": prompt}
        context = await self.hook_manager.execute("before_scan", context)
        if context.get("blocked"):
            return {"status": "blocked"}
        # Continue scanning...
```

## Plugin Metadata

Provide metadata for plugin discovery:

```python
from q_guardian.plugins import PluginMetadata


class MyPlugin(Plugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
            author="Developer",
            tags=["security", "custom"],
            dependencies=["requests>=2.0"],
        )
```

## Best Practices

1. **Keep plugins focused** - One plugin, one responsibility
2. **Use events for loose coupling** - Don't call other plugins directly
3. **Handle errors gracefully** - Don't crash the framework
4. **Implement health_check()** - Help monitor plugin status
5. **Clean up in stop()** - Release connections, close files
6. **Use async/await** - Don't block the event loop
