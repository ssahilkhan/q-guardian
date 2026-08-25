# 13 - Plugin System, Events, Hooks & Guardian SDK

> Module: `src\q_guardian\` — the extensibility backbone of Q-Gaudrail
> Scope: `plugins\`, `events\`, `hooks\`, `exceptions\`, and the `Guardian` SDK facade
> (`sdk\guardian.py`). This document explains how third-party capability (rules, ML,
> quantum, policy, observability) plugs into the framework and how components
> communicate without knowing about each other.

---

## 1. The Big Picture

Q-Gaudrail's runtime is assembled from three loosely coupled mechanisms:

```
                     Guardian (sdk\guardian.py)  —  facade
                             │
        ┌────────────────────┼───────────────────────┐
        ▼                    ▼                       ▼
   PluginRegistry       EventBus                HookManager
   (lifecycle)         (async pub/sub)         (before/after)
        │                    │                       │
   plugins: security,    typed Events          named hooks
   threat-analysis,      (Event base)          (dict-merge
   quantum-analysis,                            context)
   risk, policy, ...
```

- **Plugins** provide capability and own a lifecycle
  (`initialize → start → stop`).
- **Events** broadcast state changes to subscribers asynchronously.
- **Hooks** run handlers around named points and merge returned dicts into a shared
  context.
- **`Guardian`** wires all three together and is the recommended entry point for
  application code.

---

## 2. The Plugin System — `src\q_guardian\plugins\`

### 2.1 `plugins\base.py`

- **`PluginStatus(str, Enum)`** — `REGISTERED`, `INITIALIZING`, `RUNNING`, `STOPPED`,
  `ERROR`, `DISABLED`.
- **`PluginMetadata(BaseModel)`** — `name` (required), `version` (required),
  `author`, `description`, `dependencies: list[str]`, `status`, `interfaces: list[str]`.
- **`Plugin(ABC)`** — the plugin contract:
  - Abstract properties: `name`, `version`.
  - Concrete properties: `author = ""`, `description = ""`, `dependencies = []`,
    `interfaces = []`.
  - Abstract lifecycle methods (all `async`): `initialize(context)`, `start()`,
    `stop()`.
  - Concrete helpers: `health()` → `{"status": "healthy", "plugin": name}`;
    `configuration()` → `{}`; `metadata()` → builds `PluginMetadata` from the
    properties.

### 2.2 `plugins\registry.py`

**`PluginRegistry`** — central lifecycle + discovery hub:

| Method | Behavior |
|---|---|
| `register_plugin(plugin)` | duplicate name → `ValidationException`; stores plugin + metadata |
| `unregister_plugin(name)` | removes both |
| `get_plugin(name)` | missing → `KeyError` |
| `has_plugin(name)` / `get_plugins_by_interface(interface)` / `list_plugins(status=None)` | querying |
| `enable_plugin` / `disable_plugin` | set status `REGISTERED` / `DISABLED` |
| `initialize_all(context)` | skips `DISABLED`; sets `INITIALIZING` → `initialize` → `REGISTERED`, `ERROR` on failure (continues past failures) |
| `start_all()` | skips `DISABLED`/`ERROR`; `start` → `RUNNING` |
| `stop_all()` | reversed order; `stop` → `STOPPED` |
| `health_check()` | `{name: plugin.health()}` |
| `discover_plugins(group="q_guardian.plugins")` (static) | pip entry-point discovery via `importlib.metadata.entry_points()` |

### 2.3 `plugins\__init__.py`

Exports `Plugin`, `PluginMetadata`, `PluginRegistry`, `PluginStatus`.

---

## 3. The Event System — `src\q_guardian\events\`

### 3.1 `events\base.py`

- **`EventHandler = Callable[..., Awaitable[None]]`** — async handler signature.
- **`Event(BaseModel, ABC)`** — base for all events
  (`ConfigDict(populate_by_name=True, frozen=False)`):
  - Fields: `id` (default `generate_uuid()`), `event_type` (required),
    `timestamp` (default `datetime.now(UTC)`), `source = "system"`, `data: dict = {}`,
    `metadata: dict = {}`, `propagation_stopped: bool = False`.
  - `stop_propagation()` — halts further handler dispatch for this event.

### 3.2 `events\bus.py`

**`EventBus`** — async publish/subscribe:

- `subscribe(event_type, handler, priority=0) -> int` — handlers sorted by priority
  (lower = earlier); returns subscription id.
- `unsubscribe(subscription_id) -> bool`.
- `publish(event) -> Event` — dispatches to specific-type handlers + wildcard
  `"*"` handlers; stops early when `propagation_stopped`; per-handler exceptions are
  logged (`event_handler_error`) and never block other handlers.
- `broadcast(event_type, data=None, source="system") -> Event` — builds a `_GenericEvent`
  and publishes.
- `subscriber_count(event_type=None)` — per-type or global.
- `clear()` — resets all subscriptions.
- `WILDCARD = "*"`.

### 3.3 `events\standard.py`

Fifteen predefined standard events (all subclass `Event`, hard-coded `event_type` with
`init=False`):

| Event | event_type | Event | event_type |
|---|---|---|---|
| `FrameworkStarted` | `framework.started` | `IncidentCreated` | `incident.created` |
| `FrameworkStopped` | `framework.stopped` | `DashboardUpdated` | `dashboard.updated` |
| `PluginLoaded` | `plugin.loaded` | `BeforePrompt` | `prompt.before` |
| `PluginUnloaded` | `plugin.unloaded` | `AfterPrompt` | `prompt.after` |
| `PromptReceived` | `prompt.received` | `BeforeToolExecution` | `tool.before` |
| `ThreatDetected` | `threat.detected` | `AfterToolExecution` | `tool.after` |
| `RiskCalculated` | `risk.calculated` | `RuntimeEvent` | `runtime.event` |
| `PolicyViolation` | `policy.violation` | | |

### 3.4 `events\__init__.py`

Exports `Event`, `EventHandler`, `EventBus`.

---

## 4. The Hook System — `src\q_guardian\hooks\`

**`HookManager`** — before/after lifecycle hooks with context mutation:

- `register_hook(hook_name, handler)`, `unregister_hook(hook_name, handler) -> bool`.
- `execute_hook(hook_name, **kwargs) -> dict` — starts with `dict(kwargs)`, runs each
  handler (awaited if coroutine, else called); any handler returning a dict merges it
  into the shared context; exceptions are logged and swallowed; returns the merged
  context.
- `list_hooks() -> dict[str, int]`, `clear()`.

`HookHandler = Callable[..., Any]`.

---

## 5. Exceptions — `src\q_guardian\exceptions\`

### 5.1 `exceptions\base.py`

Hierarchy rooted at **`ApplicationException(Exception)`** — carries `message`, `code`,
`status_code`, `details`; `to_dict()` → `{"error": {"code", "message", "details"}}`.

| Class | code | status | Notes |
|---|---|---|---|
| `ValidationException` | `VALIDATION_ERROR` | 422 | |
| `DatabaseException` | `DATABASE_ERROR` | 503 | |
| `SecurityException` | `SECURITY_ERROR` | 403 | |
| `ExternalServiceException` | `EXTERNAL_SERVICE_ERROR` | 502 | `service_name` merged into details |
| `NotFoundException` | `NOT_FOUND` | 404 | message `"<resource> not found"` |
| `AuthenticationException` | `AUTHENTICATION_ERROR` | 401 | |
| `RateLimitException` | `RATE_LIMIT_ERROR` | 429 | |

### 5.2 `exceptions\handlers.py`

FastAPI handlers: `application_exception_handler`, `validation_exception_handler`
(wraps `RequestValidationError`), `general_exception_handler`; registered via
`register_exception_handlers(app)`.

---

## 6. The Guardian SDK — `src\q_guardian\sdk\guardian.py`

**`Guardian(config: FrameworkConfig | None = None)`** is the single facade an
application uses. It composes the state machine, event bus, plugin registry, hook
manager, adapters, and runtime managers.

### 6.1 Lifecycle

- `start()` — `INITIALIZING` → build `FrameworkContext` → `STARTING` →
  discover+register plugins (if `config.plugins.enabled`) →
  `initialize_all` → `start_all` → `RUNNING` → publish `FrameworkStarted`.
- `shutdown()` — `STOPPING` → publish `FrameworkStopped` → `stop_all` →
  clear event bus + hooks → `STOPPED`.

### 6.2 Facade methods

| Group | Methods |
|---|---|
| State | `state`, `get_context()` |
| Plugins | `register_plugin`, `unregister_plugin`, `enable_plugin`, `disable_plugin`, `list_plugins`, `get_plugin` |
| Events | `publish`, `subscribe`, `unsubscribe` |
| Hooks | `register_hook`, `execute_hook` |
| Adapters | `register_adapter`, `get_adapter` |
| Plugin dispatch | `scan_prompt(prompt, **kwargs)`, `monitor(data)`, `calculate_risk(data)`, `enforce_policy(data)` |
| Sessions | `create_session(agent_id="", conversation_id="", user_id="", metadata=None)`, `close_session()`, `set_agent(agent)` |
| Runtime | `runtime`, `current_agent`, `current_session`, `session_manager`, `request_manager`, `tool_tracker`, `memory_tracker`, `get_runtime_context()` |

`scan_prompt` runs the `before_prompt` hook, publishes `BeforePrompt`, dispatches to
every plugin advertising interface `"prompt_scanner"` with a `scan_prompt` method
(per-plugin try/except), runs the `after_prompt` hook, publishes `AfterPrompt`, and
returns the results.

---

## 7. Built-in Plugins & Their Interfaces

The framework ships five plugins, each exposing a distinct interface so `Guardian`
dispatch and `PluginRegistry.get_plugins_by_interface` can find them:

| Plugin | `name` | interface(s) | source |
|---|---|---|---|
| `PromptScannerPlugin` | `prompt-scanner` | `prompt_scanner` | `security\plugin.py` |
| `ThreatAnalysisPlugin` | `threat-analysis` | `prompt_scanner` | `ml\plugin.py` |
| `QuantumAnalysisPlugin` | `quantum-analysis` | `quantum_analyzer` | `quantum\plugin.py` |
| Risk / policy plugin | `risk-engine` | `risk_engine` | `risk\plugin.py` |
| Observability plugin | `observability` | `runtime_monitor` | `observability\plugin.py` |

See docs 10 (security), 12 (ML + quantum), 15 (policy/risk), and 17 (observability)
for each plugin's internals.

---

## 8. Writing a Plugin (quick pattern)

```python
from q_guardian.plugins.base import Plugin, PluginStatus
from q_guardian.framework.context import FrameworkContext


class MyPlugin(Plugin):
    name = "my-plugin"
    version = "1.0.0"
    author = "you"
    description = "Example plugin"
    interfaces = ["prompt_scanner"]

    async def initialize(self, context: FrameworkContext) -> None:
        self.context = context

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def scan_prompt(self, prompt: str, **kwargs) -> dict:
        return {"my_plugin": {"decision": "allow"}}
```

Register with `guardian.register_plugin(MyPlugin())`, or make the class discoverable
by installing an entry point in the `q_guardian.plugins` group.
