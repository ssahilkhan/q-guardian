# Runtime Abstraction Layer

## Overview

The Runtime Abstraction Layer defines the core domain models that represent an AI agent's execution lifecycle. Every future module (Prompt Security, Runtime Monitoring, Threat Detection, Policy Engine, Quantum Engine, Dashboard) MUST use these runtime objects.

This layer contains **NO** threat detection logic, **NO** ML, **NO** quantum algorithms — only reusable runtime abstractions.

## Architecture

```
src/q_guardian/runtime/
├── __init__.py       # Public API re-exports
├── enums.py          # Status and type enumerations
├── models.py         # Core domain models
├── context.py        # RuntimeContext for plugin integration
├── managers.py       # SessionManager, RequestManager, trackers
└── events.py         # Runtime lifecycle events
```

## Runtime Models

### Agent

Represents an AI agent. Contains identity, capabilities, and lifecycle state.

```python
from q_guardian import Agent

agent = Agent(
    name="security-bot",
    framework="langgraph",
    capabilities=["scan", "monitor"],
)
agent.activate()
```

### AgentSession

Groups a sequence of requests/responses within a bounded timeframe.

```python
from q_guardian import AgentSession

session = AgentSession(agent_id=agent.id, user_id="user-1")
session.open()
session.increment_requests()
session.close()
duration = session.duration()
```

### AgentRequest / AgentResponse

Model incoming requests and outgoing responses with timing and token usage.

```python
from q_guardian import AgentRequest, AgentResponse, TokenUsage

request = AgentRequest(prompt="Analyze this code", source="api")
response = AgentResponse(
    output="Safe to execute",
    execution_time=0.5,
    token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
)
```

### ToolInvocation

Tracks tool execution lifecycle including arguments, results, and timing.

```python
from q_guardian import ToolInvocation

invocation = ToolInvocation(
    tool_name="execute_sql",
    arguments={"query": "SELECT * FROM users"},
    result={"rows": 42},
    success=True,
)
```

### MemoryAccess

Tracks memory operations for audit and security analysis.

```python
from q_guardian import MemoryAccess
from q_guardian.runtime.enums import MemoryType, MemoryOperation

access = MemoryAccess(
    memory_type=MemoryType.LONG_TERM,
    operation=MemoryOperation.WRITE,
    key="user_preferences",
    value={"theme": "dark"},
)
```

### SecurityContext

Aggregates security state during execution. Updated by security plugins.

```python
from q_guardian import SecurityContext

security = SecurityContext()
security.update_risk(0.3)
security.update_trust(0.8)
security.add_alert("Anomalous behavior detected")
```

### ThreatContext / RiskContext

Structured containers for threat detection and risk calculation results.

## RuntimeContext

The central object passed to all plugins during execution. Plugins MUST NOT directly manipulate session objects — everything passes through RuntimeContext.

```python
from q_guardian import RuntimeContext

# RuntimeContext provides shortcuts
ctx.agent_id  # current agent ID
ctx.session_id  # current session ID
ctx.prompt  # current prompt text
ctx.is_blocked  # whether execution is blocked
ctx.tool_count  # number of tool invocations
ctx.threat_count  # number of detected threats

# Track operations
ctx.add_tool_invocation(invocation)
ctx.add_memory_access(access)
ctx.add_threat(threat)

# Create snapshot for monitoring
snapshot = ctx.to_snapshot()
```

## Session Lifecycle

```
create_session() → Session (OPEN)
    ↓
  request / response cycle
    ↓
close_session() → Session (CLOSED)
    ↓
  (timeout) → remove_expired_sessions() → REMOVED
```

## Agent Lifecycle

```
Agent (INACTIVE)
    ↓
set_agent() → Agent (ACTIVE)
    ↓
  (another agent set) → previous Agent (INACTIVE)
```

## Request Flow

```
1. Request received → AgentRequest
2. Track via RequestManager.track_request()
3. Process (scan, monitor, etc.)
4. Complete: RequestManager.complete_request() → AgentResponse
   OR Fail: RequestManager.fail_request()
```

## Tool Execution Flow

```
1. start_invocation() → ToolInvocation (active)
2. Execute tool
3. finish_invocation() → ToolInvocation (completed, in history)
4. get_statistics() for metrics
```

## Memory Tracking Flow

```
1. record_read() / record_write() / record_delete() / record_search()
2. get_history() for audit trail
3. get_statistics() for usage metrics
```

## Relationship: RuntimeContext vs FrameworkContext

| FrameworkContext | RuntimeContext |
|-----------------|---------------|
| Available before agents | Available during agent execution |
| Contains event_bus, plugin_registry | Contains agent, session, request |
| Shared across all plugins | Per-execution |
| No agent-specific state | Full agent execution state |

RuntimeContext wraps FrameworkContext and provides access to it via `framework_context`.

## Guardian SDK Integration

```python
from q_guardian import Guardian, Agent

guardian = Guardian()
await guardian.start()

# Set current agent
agent = Agent(name="my-bot", id="bot-1", framework="langgraph")
guardian.set_agent(agent)

# Create session
session = await guardian.create_session(user_id="user-1")

# Access runtime context
rt = guardian.runtime
print(rt.agent_id)  # "bot-1"
print(rt.session_id)  # session.session_id

# Use trackers
guardian.tool_tracker.start_invocation("search", {"q": "query"})
guardian.memory_tracker.record_read(MemoryType.SHORT_TERM, key="context")

# Close session and shutdown
await guardian.close_session()
await guardian.shutdown()
```

## Future Module Usage

| Module | Uses These Models |
|--------|------------------|
| Prompt Security | AgentRequest.prompt, RuntimeContext |
| Runtime Monitoring | ToolInvocation, MemoryAccess, RuntimeContext |
| Threat Detection | ThreatContext, SecurityContext |
| Policy Engine | SecurityContext, Agent.capabilities |
| Quantum Engine | RuntimeContext, RiskContext |
| Dashboard | All models for metrics display |
