# 09 - Database Schema Documentation

> Module: `src\q_guardian\database\` — Persistence for Q-Gaudrail v1.1.0
> Storage engines: MongoDB (async, via Motor) as the primary store; JSON-file
> backends for module-local state (risk, observability, response, ML, quantum, policy).
> At the time of writing, **no MongoDB collections are defined** — the database layer
> provides the connection manager, health check, and repository contract only.

---

## 1. Storage Architecture Overview

```
                        +--------------------------+
                        |   config/settings.py     |
                        |   DatabaseSettings       |  env_prefix="MONGODB_"
                        +--------------------------+
                                   |  get_settings()  (lru_cache singleton)
                                   v
   +----------------------------------------------------------+
   |  database/client.py : MongoDBClient                      |
   |    - AsyncIOMotorClient (connection pooling)             |
   |    - .connect() / .disconnect() / .ping() / .client      |
   |    - .database / .get_collection(name)                   |
   +----------------------------------------------------------+
        | get_db_client() (lazy singleton)                    |
        | get_database()   (FastAPI dependency)               |
        v                                                     |
   +----------------------------------------------------------+
   |  database/health.py : check_database_health()            |
   |    -> {"status": "healthy"|"unhealthy", "database": ...} |
   +----------------------------------------------------------+
        | consumed by api/v1/endpoints/health.py              |
        v
   +----------------------------------------------------------+
   |  Document contract (models/base.py)                      |
   |    BaseDocument : id (alias "_id"), model_dump_mongo()   |
   +----------------------------------------------------------+
        |
        v
   +----------------------------------------------------------+
   |  Repository contract (repositories/base.py)              |
   |    BaseRepository[T]: find/create/update/delete/count    |
   |    (abstract — MongoDB and future stores implement it)   |
   +----------------------------------------------------------+

   Module-local JSON stores (no MongoDB):
     risk/storage.py         -> risk_storage/  (assessments, audit, explanations)
     observability/storage.py-> observability_storage/ (metrics, traces, alerts, ...)
     response/storage.py     -> response_storage/ (responses, quarantines, ...)
     ml/storage.py           -> models/ml/      (joblib artifacts)
     quantum/storage.py      -> quantum models  (model_metadata.json, model_state.json)
```

Two clear tiers emerge:

- **Tier 1 — MongoDB (async)**: connection + health + future document collections.
- **Tier 2 — JSON file stores**: the fully-implemented persistence used by module
  subsystems today. Each module defines its own directory layout.

---

## 2. Connection Configuration

### 2.1 Environment variables — `.env.example`

| Variable | Default | Meaning |
|----------|---------|---------|
| `MONGODB_URL` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DATABASE` | `q_guardian` | Database name |
| `MONGODB_MIN_POOL_SIZE` | `1` | Minimum connection pool size |
| `MONGODB_MAX_POOL_SIZE` | `10` | Maximum connection pool size |
| `MONGODB_TIMEOUT_MS` | `5000` | Server selection timeout (ms) |

### 2.2 `DatabaseSettings` — `src\q_guardian\config\settings.py`

Pydantic `BaseSettings` with `env_prefix="MONGODB_"`, reading `.env`
(`SettingsConfigDict(env_prefix="MONGODB_", env_file=".env", env_file_encoding="utf-8",
case_sensitive=False, extra="ignore")`).

| Field | Default |
|-------|---------|
| `url` | `"mongodb://localhost:27017"` |
| `database` | `"q_guardian"` |
| `min_pool_size` | `1` |
| `max_pool_size` | `10` |
| `timeout_ms` | `5000` |

Property `client_kwargs -> dict[str, Any]` maps to Motor's connection pool knobs:

```
{"serverSelectionTimeoutMS": self.timeout_ms,
 "minPoolSize":              self.min_pool_size,
 "maxPoolSize":              self.max_pool_size}
```

### 2.3 Fallback constants — `src\q_guardian\core\constants.py`

If settings are not wired, the module defines defaults:

- `MONGODB_MIN_POOL_SIZE: Final[int] = 1`
- `MONGODB_MAX_POOL_SIZE: Final[int] = 10`
- `MONGODB_TIMEOUT_MS: Final[int] = 5000`

> Note: `constants.py` documents that `HEALTH_ENDPOINT`, `VERSION_ENDPOINT`,
> `ROOT_ENDPOINT`, `REQUEST_ID_HEADER`, and the `MONGODB_*` constants are not
> referenced elsewhere in `src\q_guardian` (defined for external/future use).

---

## 3. `MongoDBClient` — `src\q_guardian\database\client.py`

The async client manager built on `motor.motor_asyncio`.

### 3.1 Lifecycle

| Method | Behavior |
|--------|----------|
| `__init__()` | Holds `_client=None`, `_database=None`, `_settings=get_settings()`. |
| `async connect()` | No-op (info log) if already connected; otherwise creates `AsyncIOMotorClient(url, **client_kwargs)`, sets `_database = client[database]`, runs `await self._client.admin.command("ping")`, logs `mongodb_connected`. |
| `async disconnect()` | `close()` the client; resets `_client`/`_database` to `None`. |
| `async ping() -> bool` | `await self.client.admin.command("ping")` wrapped in try/except → `True`/`False`. |
| `get_collection(name)` | `return self.database[name]`. |

### 3.2 Accessors with guards

| Accessor | Guard |
|----------|-------|
| `client -> AsyncIOMotorClient[Any]` | Raises `RuntimeError("MongoDB client is not connected. Call connect() first.")` if `None`. |
| `database -> AsyncIOMotorDatabase[Any]` | Same `RuntimeError` guard. |

### 3.3 Module-level accessors

| Accessor | Purpose |
|----------|---------|
| `get_db_client() -> MongoDBClient` | Lazy singleton (`_client_instance`); creates once and reuses. |
| `get_database()` (async generator) | FastAPI dependency: `client = get_db_client()`, `yield client.database`. **Does not call `connect()`** — the caller must connect first. |

Consumers: `database/__init__.py`, `database/health.py`, `api/app.py`
(app factory calls `get_db_client()` for lifecycle wiring).

---

## 4. Health Check — `src\q_guardian\database\health.py`

`check_database_health() -> dict[str, Any]` (async):

1. `client = get_db_client()`
2. `is_connected = await client.ping()`
3. If connected → `{"status": "healthy", "database": "mongodb", "message": "Connection successful"}`
4. Else → `{"status": "unhealthy", "database": "mongodb", "message": "Ping failed"}`
5. On exception → log `database_health_check_failed`, return `{"status": "unhealthy", "database": "mongodb", "message": str(e)}`

Consumed by `api/v1/endpoints/health.py`, which packs the result into
`HealthResponseSchema.database` (`dict[str, Any] | None`). The HTTP layer maps
`healthy` → `status="healthy"` and `unhealthy`/degraded states into a
`degraded`-style response (see `docs/07_API_Reference_Documentation.md`).

---

## 5. Error Contract

`DatabaseException` in `src\q_guardian\exceptions\base.py`:

| Attribute | Value |
|-----------|-------|
| `code` | `"DATABASE_ERROR"` |
| `status_code` | `503` (Service Unavailable) |
| default message | `"Database operation failed"` |

Registered by `src\q_guardian\exceptions\handlers.py`
(`register_exception_handlers`) so the FastAPI app returns a structured error.

---

## 6. Document Model — `src\q_guardian\models\base.py`

The base classes any MongoDB document will inherit from:

| Class | Purpose |
|-------|---------|
| `TimestampMixin(BaseModel)` | `created_at` and `updated_at`, both `default_factory(get_utc_now)`. |
| `BaseModelConfig(BaseModel)` | `model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True, use_enum_values=True, frozen=False)`. |
| `BaseDocument(BaseModelConfig, TimestampMixin)` | Mongo document root. `id: str = Field(default_factory=generate_uuid, alias="_id")`. |
| `AbstractEntity(ABC)` | Abstract `to_dict()` and `get_id()` contract. |

Serialization method on `BaseDocument`:

```
model_dump_mongo() -> dict[str, Any]:   # returns self.model_dump(by_alias=True)
```

This means documents store their primary key under `_id` (Mongo convention) while
Python code uses `.id`.

---

## 7. Repository Contract — `src\q_guardian\repositories\base.py`

`BaseRepository(ABC, Generic[T])` — abstract CRUD contract all data-access layers
implement (MongoDB and future stores). All methods async:

| Method | Signature |
|--------|-----------|
| `find_by_id` | `(id: str) -> T \| None` |
| `find_many` | `(filters: dict \| None = None, skip: int = 0, limit: int = 100, sort: list[tuple[str, int]] \| None = None) -> list[T]` |
| `create` | `(entity: T) -> T` |
| `update` | `(id: str, data: dict[str, Any]) -> T \| None` |
| `delete` | `(id: str) -> bool` |
| `count` | `(filters: dict \| None = None) -> int` |
| `exists` | `(id: str) -> bool` |

There is currently **no MongoDB implementation** of this contract; the interface is
the intended seam for future collection-backed repositories.

---

## 8. Current Collection Status

**Defined MongoDB collections: none.**

A grep of `src\q_guardian\database\` shows only `client.py`, `health.py`, and
`__init__.py`. `get_collection(name)` exists on `MongoDBClient` and returns
`self.database[name]`, so collection creation is fully supported — no collections
are yet wired into any subsystem. All working persistence today is JSON-file based
(see next section).

---

## 9. JSON File Stores (Module-local Persistence)

These are the *actual* persistence layers in use. All follow the same pattern:
a root directory, per-category subdirectories, one JSON file per record named
`{record_id}.json`, pretty-printed UTF-8, `default=str`.

### 9.1 Risk — `src\q_guardian\risk\storage.py`

- Default root: `risk_storage/`
- Subdirectories: `assessments/`, `audit/`, `explanations/`
- Methods: `save_assessment`, `load_assessment` (raises `RiskError("Assessment not found: …")`),
  `save_audit_record`, `save_explanation`, `list_assessments`, `list_audit_records`,
  `delete_assessment`, `get_storage_stats` (counts + total bytes).

### 9.2 Observability — `src\q_guardian\observability\storage.py`

- Default root: `observability_storage/`
- Subdirectories: `metrics/`, `traces/`, `alerts/`, `alert_events/`, `health/`, `analytics/`
- Methods: `save_metric`, `save_trace`, `save_alert`, `save_alert_event`,
  `save_health_report` (`health/{report_id or "latest"}.json`),
  `save_analytics_report` (same pattern), plus `load_metric/trace/alert` (raise
  `StorageError("… not found: {id}")`), list and delete helpers, `get_storage_stats`.

### 9.3 Response — `src\q_guardian\response\storage.py`

- Default root: `response_storage/`
- Subdirectories: `responses/`, `quarantines/`, `playbooks/`, `evidence/`,
  `recovery/`, `rollbacks/`
- Methods: `save_response`, `load_response`, `save_quarantine`, `load_quarantine`,
  `save_playbook_execution`, `save_rollback`, `save_recovery`, list helpers,
  `delete(category, item_id)` (category map: `"response"`, `"quarantine"`,
  `"playbook"`, `"evidence"`, `"recovery"`, `"rollback"`).
- `_serialize()` staticmethod: `model_dump(mode="json")` when available, else
  `__dict__` minus `_`-prefixed keys, else `{"value": str(obj)}`.

### 9.4 ML — `src\q_guardian\ml\storage.py`

- Default root: `models/ml/` (created at construction with `mkdir(parents=True, exist_ok=True)`)
- Format: **joblib** (`.joblib`), not JSON
- Naming: `<base>/<model_name>/<model_name>_v<version>.joblib`
- Methods: `save(model, metadata) -> artifact_path` (sets `metadata.status=READY`),
  `load(metadata)` (raises `ValueError` on empty path, `FileNotFoundError` on missing file),
  `delete(metadata)`, `exists(metadata)`, `list_artifacts()` (`rglob("*.joblib")`).

### 9.5 Quantum — `src\q_guardian\quantum\storage.py`

- Constants: `METADATA_FILENAME = "model_metadata.json"`,
  `STATE_FILENAME = "model_state.json"`, `VERSIONS_DIR = "versions"`
- Follows the ML `ModelStorage` pattern; JSON metadata + state per model, versioned
  with rollback, bulk listing, deletion, and storage statistics.

### 9.6 Policy — `src\q_guardian\policy\storage\`

The Advanced Policy Engine can persist policy definitions to file when
`persist_to_file` is enabled in `PolicyEngineConfig` (see
`src\q_guardian\policy\config.py` and `policy\storage\__init__.py`).

---

## 10. Docker / Deployment

`docker-compose.yml` declares the MongoDB service used by the containerized API:

- Image: `mongo:7`, container `q-guardian-mongo`, port `27017:27017`
- Volume: `mongo-data:/data/db`
- Healthcheck: `["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]`
  (interval 10s, timeout 5s, retries 5, start_period 10s)
- The `api` service waits on `mongo` with `depends_on: condition: service_healthy`
  and connects via `MONGODB_URL=mongodb://mongo:27017`.

---

## 11. Schema Evolution Notes

- There is no migration framework and no versioned collection schema; schema is
  implicit in the Pydantic models listed in `docs/08_Data_Model_Documentation.md`.
- JSON stores are backward-tolerant only by loading into `dict` (files are never
  re-validated into models on load except where a loader exists).
- Future MongoDB adoption should implement `BaseRepository[T]` per collection and
  reuse `BaseDocument.model_dump_mongo()` for writes.
