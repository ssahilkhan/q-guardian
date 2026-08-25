# Event System Guide

## Overview

The Q-Guardian event system provides async pub/sub messaging for loose coupling between components. Events are the primary way plugins, hooks, and adapters communicate.

## Event Bus

### Creating an Event Bus

```python
from q_guardian.events import EventBus

bus = EventBus()
```

### Subscribing to Events

```python
async def handler(event):
    print(f"Received: {event}")


# Subscribe to specific event type
await bus.subscribe("threat.detected", handler)

# Subscribe to all events
await bus.subscribe("*", handler)

# Subscribe to event category
await bus.subscribe("threat.*", handler)  # all threat events
```

### Publishing Events

```python
from q_guardian.events.standard import ThreatDetected

event = ThreatDetected(threat_type="prompt_injection", severity="high", source="scanner-plugin")

await bus.publish(event)
```

### Unsubscribing

```python
await bus.unsubscribe("threat.detected", handler)
```

### Getting Subscriber Count

```python
count = bus.subscriber_count("threat.detected")
```

### Clearing All Subscribers

```python
await bus.clear()
```

## Standard Events

### Framework Events

```python
from q_guardian.events.standard import (
    FrameworkStarted,
    FrameworkStopped,
    FrameworkError,
    PluginLoaded,
    PluginUnloaded,
)

# Framework lifecycle
event = FrameworkStarted(version="1.0.0", source="guardian")
event = FrameworkStopped(reason="shutdown", source="guardian")
event = FrameworkError(error="Connection failed", source="database")
```

### Security Events

```python
from q_guardian.events.standard import (
    ThreatDetected,
    PromptReceived,
    PromptScanned,
    PolicyViolation,
    AnomalyDetected,
)

# Threat detection
event = ThreatDetected(
    threat_type="prompt_injection",
    severity="high",
    source="scanner",
    details={"pattern": "ignore previous"},
)

# Prompt scanning
event = PromptReceived(prompt="Hello world", source="api")
event = PromptScanned(prompt="Hello world", result={"safe": True}, source="scanner")
```

### Quantum Events

```python
from q_guardian.events.standard import (
    QuantumCircuitCreated,
    QuantumMeasurementMade,
    QuantumStateCollapsed,
)

# Quantum operations
event = QuantumCircuitCreated(circuit_id="abc-123", qubits=4, source="quantum-scanner")

event = QuantumMeasurementMade(circuit_id="abc-123", result="0110", source="quantum-scanner")
```

### Dashboard Events

```python
from q_guardian.events.standard import MetricsUpdated, AlertTriggered

# Metrics
event = MetricsUpdated(metrics={"scans": 100, "threats": 5}, source="metrics-collector")

# Alerts
event = AlertTriggered(
    alert_type="high_threat-rate",
    severity="critical",
    message="Threat rate exceeded threshold",
    source="monitor",
)
```

## Event Propagation

### Stopping Propagation

```python
async def handler(event):
    event.stop_propagation()  # Prevents other handlers from receiving event
    print("Handled exclusively")


await bus.subscribe("threat.detected", handler)
```

### Priority Ordering

Handlers are executed in the order they were subscribed. Use multiple subscriptions with specific ordering if needed.

## Error Handling

Handler errors are isolated - one handler failing doesn't affect others:

```python
async def bad_handler(event):
    raise ValueError("Something went wrong")


async def good_handler(event):
    print("This still runs!")


await bus.subscribe("threat.detected", bad_handler)
await bus.subscribe("threat.detected", good_handler)

# Both handlers are called, error from bad_handler is logged
```

## Custom Events

Create custom events by extending the Event base class:

```python
from q_guardian.events import Event
from datetime import datetime
from uuid import uuid4


class CustomEvent(Event):
    def __init__(self, data: str, source: str = "custom"):
        self.id = str(uuid4())
        self.timestamp = datetime.now()
        self.source = source
        self.data = {"custom_data": data}
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

## Best Practices

1. **Use descriptive event types** - `threat.detected` not `event1`
2. **Include context in events** - source, timestamp, relevant data
3. **Keep handlers small** - Do one thing per handler
4. **Use wildcards carefully** - `*` receives everything
5. **Handle errors in handlers** - Don't let exceptions propagate
6. **Avoid circular events** - A→B→A can cause infinite loops
