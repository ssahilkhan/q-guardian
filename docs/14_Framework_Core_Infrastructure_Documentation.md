# 14 - Framework, Core & Infrastructure

> Module: `src\q_guardian\` — the supporting layers that make the security/ML/quantum
> modules runnable: `framework\`, `core\`, `config\`, `database\`, `dependencies\`,
> `logging\`, `middleware\`, `models\`, `repositories\`, `schemas\`, `services\`,
> `utils\`, `adapters\`, and the FastAPI service (`api\`).

---

## 1. Framework Configuration & Context — `src\q_guardian\framework\`

### 1.1 `framework\config.py`

Seven Pydantic configs + aggregate:

| Config | Key defaults |
|---|---|
| `PluginConfig` | `enabled=True`, `priority=0` (`extra="allow"`) |
| `RuntimeConfig` | `max_concurrent_agents=100`, `request_timeout_seconds=30`, `enable_caching=True` |
| `PolicyConfig` | `enforcement_mode="enforce"` (enforce/audit/disabled), `default_policy="allow"` |
| `QuantumConfig` | `enabled=False`, `backend="simulator"` |
| `DashboardConfig` | `enabled=False`, `refresh_interval_seconds=30` |
| `PromptScannerConfig` | `enabled=True`, `sensitivity="medium"` |
| `FrameworkConfig` | aggregates all six + `plugin_configs: dict[str, dict]` |

`FrameworkConfig` methods: `from_settings(settings)` (maps `debug` → caching,
`logging.level` → runtime log level), `get_plugin_config(plugin_name)`,
`load_from_file(path)` (async; JSON/YAML, YAML requires PyYAML).

### 1.2 `framework\context.py`

**`FrameworkContext(BaseModel)`** — the shared handle handed to every plugin and
adapter (`ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)`):
- Required: `logger`, `config`, `event_bus`, `plugin_registry`, `hook_manager`.
- Optional: `database`, `session_id` (default `generate_uuid()`),
  `current_request`, `current_agent`, `extra`.
- `create_child_context(**overrides)` — deep-copies `extra` and produces a new child
  context.

---

## 2. Core — `src\q_guardian\core\`

### 2.1 `core\constants.py`

`APP_TITLE="Q-Guardian"`, `APP_DESCRIPTION`, `APP_VERSION="0.10.0"`,
`API_V1_PREFIX="/api/v1"`, `HEALTH_ENDPOINT="/health"`, `VERSION_ENDPOINT="/version"`,
`ROOT_ENDPOINT="/"`, `CORRELATION_ID_HEADER="X-Correlation-ID"`,
`REQUEST_ID_HEADER="X-Request-ID"`, `MONGODB_MIN/MAX_POOL_SIZE`, `MONGODB_TIMEOUT_MS`.

### 2.2 `core\framework_state.py`

- **`FrameworkState(str, Enum)`** — `INITIALIZING`, `STARTING`, `RUNNING`,
  `STOPPING`, `STOPPED`, `ERROR`.
- **`FrameworkStateMachine`** — enforces valid transitions:

```
INITIALIZING → {STARTING, ERROR, STOPPED}
STARTING     → {RUNNING, ERROR, STOPPING}
RUNNING      → {STOPPING, ERROR}
STOPPING     → {STOPPED, ERROR}
STOPPED      → {}
ERROR        → {STOPPING, INITIALIZING}
```

Invalid transitions raise `StateTransitionError(ApplicationException)` with code
`INVALID_STATE_TRANSITION`. Helpers: `is_running`, `is_stopped`, `is_error`,
`can_start`, `can_stop`.

---

## 3. Application Configuration — `src\q_guardian\config\settings.py`

pydantic-settings, env-driven, categories keyed by env prefix:

| Class | env_prefix | Key fields |
|---|---|---|
| `Environment(str, Enum)` | — | `development`, `testing`, `production` |
| `AppSettings` | `APP_` | `name`, `version="0.10.0"`, `environment`, `debug=True`, `host`, `port=8000`, `log_level`, `log_dir` |
| `DatabaseSettings` | `MONGODB_` | `url`, `database`, `min_pool_size=1`, `max_pool_size=10`, `timeout_ms=5000` |
| `SecuritySettings` | — | `secret_key` (production guard via `validate_secret_key`), `jwt_algorithm="HS256"`, `jwt_expiration_minutes=30`, `api_key_header` |
| `CORSSettings` | `CORS_` | `origins`, `allow_credentials`, `allow_methods`, `allow_headers` |
| `LoggingSettings` | — | `level`, `dir`, `max_bytes`, `backup_count`, `format` |

`_SettingsComposite` aggregates all five; `get_settings()` (lru-cached singleton)
returns it.

---

## 4. Database — `src\q_guardian\database\`

- **`MongoDBClient`** (Motor async driver):
  - `connect()` — builds `AsyncIOMotorClient`, pings `admin.command("ping")`,
    selects database.
  - `disconnect()`, `client` / `database` properties (raise `RuntimeError` if not
    connected), `get_collection(name)`, `ping() -> bool`.
- **Singletons / dependencies**: `get_db_client()` (lazy singleton),
  `get_database()` (async FastAPI dependency).
- **`check_database_health()`** → `{"status": "healthy"|"unhealthy", "database":
  "mongodb", "message": ...}`.

---

## 5. Dependency Injection — `src\q_guardian\dependencies\container.py`

**`DependencyContainer`** — name-keyed service registry: `register(name, service)`,
`resolve(name)` (raises `KeyError`), `has(name)`, `clear()`. `get_container()`
singleton.

---

## 6. Logging — `src\q_guardian\logging\`

- **`setup_logging(log_level="INFO", log_dir="logs", log_format="json")`** —
  configures structlog: shared processors (contextvars, level, stack info, exc info,
  ISO timestamps), `JSONRenderer()` or `ConsoleRenderer(colors=True)`,
  `PrintLoggerFactory`, filter-by-level bound logger; adds a
  `TimedRotatingFileHandler` (`q_guardian.log`, midnight rotation, 30 backups) and a
  stdout `StreamHandler`; silences `uvicorn.access`, `motor`, `pymongo` at WARNING.
- **`RequestLoggingMiddleware`** — logs `request_started` / `request_completed` with
  correlation id + timing; sets `X-Response-Time`.

---

## 7. HTTP Middleware — `src\q_guardian\middleware\`

| Middleware | Purpose |
|---|---|
| `CorrelationIDMiddleware` | ensures every request carries a correlation id (client-provided or fresh `uuid4().hex[:12]`); binds contextvars; sets response header |
| `ExceptionLoggingMiddleware` | logs unhandled exceptions with traceback, then re-raises |
| `ResponseTimingMiddleware` | adds `X-Response-Time` header, debug-log `response_timing` |

---

## 8. Data-Access Scaffolding — models / repositories / schemas / services

These packages define **interfaces and base classes**; they are currently empty of
concrete domain implementations (no in-tree consumers beyond `api` schemas).

- **`models\base.py`**: `TimestampMixin` (`created_at`, `updated_at` via
  `get_utc_now`); `BaseModelConfig` (`populate_by_name`, `str_strip_whitespace`,
  `use_enum_values`); `BaseDocument` (`id` aliased `_id`, `model_dump_mongo()`
  dumping by alias); `AbstractEntity(ABC)` (`to_dict()`, `get_id()`).
- **`repositories\base.py`**: `BaseRepository(ABC, Generic[T])` — `find_by_id`,
  `find_many(filters, skip=0, limit=100, sort)`, `create`, `update`, `delete`,
  `count`, `exists` (all async).
- **`services\base.py`**: `BaseService(ABC, Generic[T])` — `get_by_id`, `get_all`,
  `create`, `update`, `delete` (all async).
- **`schemas\base.py`**: `BaseSchema`; `ResponseSchema[T]` (envelope: `success`,
  `message`, `data`, `timestamp`, `correlation_id`); `PaginatedResponseSchema[T]`
  (`total`, `page`, `page_size`, `total_pages`); `HealthResponseSchema`;
  `ErrorResponseSchema`; `VersionResponseSchema` (`python_version`).

---

## 9. Utilities — `src\q_guardian\utils\`

| Module | Contents |
|---|---|
| `datetime_utils.py` | `get_utc_now()`, `utc_timestamp()`, `get_current_timestamp()`, `to_iso_format(dt)` |
| `uuid_utils.py` | `generate_uuid()` (str v4), `generate_correlation_id()` (12-char hex) |
| `json_utils.py` | orjson `json_dumps` / `json_loads`; `OrjsonResponse` (FastAPI response_class with `OPT_SERIALIZE_NUMPY | OPT_NON_STR_KEYS`) |
| `env_utils.py` | `get_environment()`, `is_development/is_testing/is_production()`, `get_env_variable(key, default)` |
| `helpers.py` | `mask_sensitive(value, visible_chars=4)`, `chunk_list`, `flatten_list`, `none_if_empty` |

`utils\__init__.py` re-exports the datetime/uuid/json helpers (not env/helpers).

---

## 10. Adapters — `src\q_guardian\adapters\`

**`Adapter(ABC)`** — bridges Q-Gaudrail to external agent frameworks:
- Abstract: `name`, `version`, `framework_name`; async `initialize(context)`,
  `connect_agent(agent_config)`, `process_prompt(prompt, context)`,
  `handle_response(response)`, `extract_features(data)`.
- Concrete: `health()`, `shutdown()`.

Seven stubs exist (future integration): `GenericAdapter` (`generic`), `AutoGenAdapter`
(`autogen`), `CrewAIAdapter` (`crewai`), `GoogleADKAdapter` (`google_adk`),
`LangGraphAdapter` (`langgraph`), `OpenAIAgentsAdapter` (`openai_agents`),
`SemanticKernelAdapter` (`semantic_kernel`). Each: `version="0.10.0"`, `initialize`
is a no-op, and the four data methods raise `NotImplementedError`. Only `Adapter` is
exported publicly.

---

## 11. HTTP Service — `src\q_guardian\api\`

- **`api\app.py`** — `create_app()` FastAPI factory: lifespan (logging setup, Mongo
  connect via `database\client.py`, disconnect on shutdown), mounts v1 router,
  registers middleware (`CorrelationID`, `ExceptionLogging`, `ResponseTiming`,
  `SecurityHeaders`, `TrustedHost`, `CORS`) and `register_exception_handlers`.
- **`api\v1\router.py`** — v1 APIRouter; currently `/health` and `/system`.
- **Endpoints**:
  - `GET /health` → `HealthResponseSchema` (liveness + database health).
  - `GET /system/version` → `VersionResponseSchema`.
  - `GET /system/status` → `ResponseSchema`.

---

## 12. Dependency Map

- **Foundation (no internal deps):** `utils\*`, `exceptions\base.py`,
  `core\constants.py`, `framework\config.py`, `adapters\base.py`,
  `repositories\base.py`, `services\base.py`, `models\base.py`, `schemas\base.py`.
- **Singleton providers:** `config\settings.get_settings`,
  `database\client.get_db_client` / `get_database`, `dependencies\container.get_container`.
- **Hubs:** `events\base` → `bus` → `standard`; `plugins\base` → `registry`;
  `hooks\manager`; `framework\context`.
- **Assembler:** `sdk\guardian.py` consumes adapters, framework state/config/context,
  events, hooks, plugins, utils, and runtime.
- **API wiring:** `api\app.py` consumes config, logging, middleware, exceptions,
  database, and the v1 endpoints.
