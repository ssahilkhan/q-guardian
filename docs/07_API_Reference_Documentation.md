# 07. API Reference — Q-Gaudrail

> **Document index:** this is document 07 of the Q-Gaudrail technical documentation set.
> This document reflects the code as it exists today. The pre-existing `docs/api-reference.md` documents a broader/planned REST surface; this document is authoritative for what is implemented.

## 1. HTTP API

### 1.1 Base URL & conventions

- Base URL: `http://localhost:8000`
- v1 prefix: `/api/v1`
- Docs: `/docs` (Swagger UI), `/redoc`, `/openapi.json`
- Correlation header: `X-Correlation-ID` — preserved if the client provides one, otherwise generated as `uuid4().hex[:12]` and echoed back on the response (`middleware/correlation.py`).

### 1.2 `GET /` — Root

Returns basic application info. Status `200`.

```json
{
  "application": "Q-Guardian",
  "version": "1.1.0",
  "docs": "/docs",
  "redoc": "/redoc",
  "health": "/api/v1/health"
}
```

### 1.3 `GET /api/v1/health` — Health check (liveness + readiness)

Also available at `/api/v1/health/`. Response model: `HealthResponseSchema`.

| Field | Type | Description |
|---|---|---|
| `status` | string | `"healthy"` if DB healthy, else `"degraded"` |
| `application` | string | App name (`Q-Guardian`) |
| `version` | string | `1.1.0` |
| `environment` | string | e.g. `development` |
| `timestamp` | datetime | UTC check time |
| `database` | dict | `{status: "healthy"/"unhealthy", database: "mongodb", message}` |

DB health is computed by `database/health.py::check_database_health()` which pings Mongo via `MongoDBClient.ping()`.

### 1.4 `GET /api/v1/system/version` — Version & system info

Response model: `ResponseSchema[VersionResponseSchema]`.

```json
{
  "success": true,
  "message": "Version information retrieved successfully",
  "data": {
    "application": "Q-Guardian",
    "version": "1.1.0",
    "environment": "development",
    "python_version": "3.12.x",
    "timestamp": "..."
  },
  "timestamp": "...",
  "correlation_id": null
}
```

### 1.5 `GET /api/v1/system/status` — Operational status

Response model: `ResponseSchema[dict[str, str]]`; returns `{"status": "operational"}`.

### 1.6 Response envelope schemas (`schemas/base.py`)

- `ResponseSchema[T]`: `success`, `message`, `data`, `timestamp`, `correlation_id`.
- `PaginatedResponseSchema[T]`: `success`, `message`, `data[]`, `total`, `page`, `page_size`, `total_pages`, `timestamp`.
- `HealthResponseSchema`: `status`, `application`, `version`, `environment`, `timestamp`, `database`.
- `ErrorResponseSchema`: `success=false`, `error{...}`, `timestamp`, `correlation_id`.
- `VersionResponseSchema`: `application`, `version`, `environment`, `python_version`, `timestamp`.

### 1.6a Console API — analysis & console routers

The web console (`/ui`, see `docs/21_Web_Console_UI.md`) adds two v1 routers.
All run through the shared `AnalysisService` facade over the existing
`ThreatAnalysisPlugin`; no detection logic is reimplemented.

**Analysis** (`/api/v1/analysis`, `endpoints/analysis.py`):

| Endpoint | Request | Response | Notes |
|---|---|---|---|
| `POST /analysis/scan` | `ScanRequestSchema {prompt}` (1–100 000 chars) | `ResponseSchema[AnalysisItemSchema]` | Runs the full pipeline; result appended to in-memory history (bounded, 200). |
| `GET /analysis` | query `limit` (1–200) | `PaginatedResponseSchema[AnalysisItemSchema]` | Most recent first. |
| `GET /analysis/{analysis_id}` | — | `ResponseSchema[AnalysisItemSchema]` | `404` if unknown. |

`AnalysisItemSchema` (in `schemas/console.py`) summarizes `analysis_id`,
`decision`, `risk_score`, `is_valid`, `finding_count`, `high_severity_count`,
`processing_time_ms`, `timestamp`, plus the full `payload` (the pipeline's
`PromptAnalysis` dump: findings, features, normalized prompt, recommendation…).

**Console** (`/api/v1/console`, `endpoints/console.py`) — read-only:

| Endpoint | Data |
|---|---|
| `GET /console/rules` | Registered detection rules (`list[dict]`). |
| `GET /console/models` | ML model registry status + quantum backend availability (`ml`, `quantum`). |
| `GET /console/components` | Pipeline stage inventory with live status. |
| `GET /console/configuration` | Sanitized configuration. **Never** returns `secret_key`, tokens, passwords, credentialed URLs, or `*_path` / `*_dir` keys. |
| `GET /console/summary` | Landing-page aggregates (components, rules, ml, quantum, history). |
| `GET /console/research` | Read-only research artifact snapshot via `q_guardian/api/services/research.py`: `datasets`, `model_artifacts` (metadata only), `evaluation`, `benchmarks`, `loadtests`. Bounded reads of known on-disk files; binary models never deserialized. |

### 1.7 Middleware behavior

Request chain (outer→inner): **CorrelationID → ResponseTiming → ExceptionLogging → SecurityHeaders → CORS → TrustedHost (dev only)**. See `06_Architecture_Documentation.md` §5.

### 1.8 Not yet implemented (scaffolded)

`api/v1/router.py` contains commented-out scaffolding for future routers: prompt-injection, jailbreak, threats. These endpoints are **not** registered.

## 2. Python SDK — `q_guardian.Guardian`

Main facade (see `sdk/guardian.py`). Usage:

```python
from q_guardian import Guardian

guardian = Guardian()  # or Guardian(config=FrameworkConfig(...))
await guardian.start()
# ... use the framework ...
await guardian.shutdown()
```

### 2.1 Construction

| Member | Signature | Description |
|---|---|---|
| `Guardian.__init__` | `(config: FrameworkConfig \| None = None)` | Composes state machine, event bus, plugin registry, hook manager, adapters dict, runtime managers |

### 2.2 Lifecycle

| Method | Signature | Description |
|---|---|---|
| `start` | `async` | INITIALIZING → context → STARTING → discover/register plugins → initialize_all → start_all → RUNNING → publish `FrameworkStarted` |
| `shutdown` | `async` | If RUNNING/ERROR: STOPPING → publish `FrameworkStopped` → stop_all → clear bus/hooks → STOPPED |

### 2.3 Properties

`state`, `events` (EventBus), `plugins` (PluginRegistry), `config`, `runtime` (RuntimeContext \| None), `current_agent`, `current_session`, `session_manager`, `request_manager`, `tool_tracker`, `memory_tracker`; `get_context()` → FrameworkContext \| None.

### 2.4 Plugin management

`register_plugin(plugin)`, `unregister_plugin(name)`, `enable_plugin(name)`, `disable_plugin(name)`, `list_plugins()` → list[PluginMetadata], `get_plugin(name)` (raises `KeyError`).

### 2.5 Events

`publish(event) -> Event`, `subscribe(event_type, handler, priority=0) -> int`, `unsubscribe(subscription_id) -> bool`.

### 2.6 Hooks

`register_hook(hook_name, handler)`, `execute_hook(hook_name, **kwargs) -> dict`.

### 2.7 Adapters

`register_adapter(adapter)` (keyed by `adapter.name`), `get_adapter(name)` (raises `KeyError`).

### 2.8 Convenience / plugin dispatch

| Method | Signature | Behavior |
|---|---|---|
| `scan_prompt` | `async (prompt, **kwargs) -> dict` | `before_prompt` hook → `BeforePrompt` event → plugins implementing `prompt_scanner` → `after_prompt` hook → `AfterPrompt` event; returns aggregated results |
| `monitor` | `async (event_data) -> dict` | dispatch to `runtime_monitor` plugins |
| `calculate_risk` | `async (data) -> dict` | dispatch to `risk_engine` plugins |
| `enforce_policy` | `async (data) -> dict` | dispatch to `policy_engine` plugins |

### 2.9 Runtime management

| Method | Signature | Description |
|---|---|---|
| `set_agent` | `(agent: Agent)` | activates agent (deactivates previous), updates runtime context |
| `create_session` | `async (agent_id="", conversation_id="", user_id="", metadata=None) -> AgentSession` | creates session (agent_id falls back to current agent), updates context, publishes `SessionStarted` |
| `close_session` | `async () -> bool` | closes current session, publishes `SessionEnded` |
| `get_runtime_context` | `() -> RuntimeContext \| None` | current runtime context |

## 3. Adapter API — `q_guardian.adapters`

Abstract `Adapter` base (`adapters/base.py`) with concrete implementations:
`generic`, `autogen`, `crewai`, `google_adk`, `langgraph`, `openai_agents`, `semantic_kernel`.

Contract: each adapter exposes `name` and framework-specific integration methods; used with `Guardian.register_adapter()` / `get_adapter()`.

## 4. Plugin API — `q_guardian.plugins`

- `Plugin` base: `name`, `version`, `initialize(context)`, `start()`, `stop()`, `health_check()`; interface detection via methods (e.g. `scan_prompt` → `prompt_scanner`, `monitor` → `runtime_monitor`, `calculate_risk` → `risk_engine`, `enforce_policy` → `policy_engine`).
- `PluginRegistry`: `register_plugin`, `unregister_plugin`, `enable_plugin`, `disable_plugin`, `get_plugin`, `list_plugins`, `get_plugins_by_interface`, `has_plugin`, `initialize_all`, `start_all`, `stop_all`, static `discover_plugins()`.

## 5. Event System API — `q_guardian.events`

- `Event` base: `id`, `timestamp`, `source`, `data`, `event_type` (class-level).
- `EventBus`: `subscribe(event_type, handler, priority=0) -> int`, `unsubscribe(id) -> bool`, `publish(event) -> Event`, `publish_sync`, `clear()`, wildcard `"*"` and category patterns (`"threat.*"`).
- Standard events (`events/standard.py`): `FrameworkStarted`, `FrameworkStopped`, `BeforePrompt`, `AfterPrompt`.
- Domain events exist for runtime, security, ml, quantum, risk, policy, response, observability (see `08_Data_Model_Documentation.md`).

## 6. Configuration API

`q_guardian.config.settings`:
- `Environment` enum: `DEVELOPMENT`, `TESTING`, `PRODUCTION`.
- `AppSettings` (env prefix `APP_`), `DatabaseSettings` (prefix `MONGODB_`), `SecuritySettings`, `CORSSettings` (prefix `CORS_`), `LoggingSettings`.
- `get_settings()` → cached `_SettingsComposite` exposing `.app`, `.database`, `.security`, `.cors`, `.logging`.
- Validation: `SecuritySettings.secret_key` raises if still default **and** `ENVIRONMENT=production`.
- `DatabaseSettings.client_kwargs` → `{serverSelectionTimeoutMS, minPoolSize, maxPoolSize}` for Motor.

## 7. Database API — `q_guardian.database`

- `MongoDBClient` (singleton via `get_db_client()`): `connect()`, `disconnect()`, `ping() -> bool`, `.client`, `.database`, `get_collection(name)`.
- `get_database()` — FastAPI dependency yielding the Motor database.

## 8. Logging API — `q_guardian.logging`

- `setup_logging(log_level, log_dir, log_format)` — structlog configuration (JSON or console).
- Logging middleware adds context; `CorrelationIDMiddleware` binds `correlation_id` via structlog contextvars.

## 9. Error Handling

- `GuardianError` hierarchy (`exceptions/base.py`) with `message`, `code`, `details`, `to_dict()`/`from_dict()`.
- `register_exception_handlers(app)` (`exceptions/handlers.py`) wires exception handlers onto the FastAPI app.
- Module-specific exception types: `response/exceptions.py` (13, incl. `ResponseTimeoutError`), `risk/exceptions.py`, `policy/exceptions.py`, `quantum/exceptions.py`, `ml/exceptions.py` (via module layout), `observability/exceptions.py`.

## 10. Cross-References

- `06_Architecture_Documentation.md` — middleware chain, facade internals.
- `08_Data_Model_Documentation.md` — models backing the SDK/API.
- `docs/api-reference.md` (pre-existing) — planned/broader API surface.
