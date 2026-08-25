# Q-Guardian Security Review Report

**Date:** 2026-07-19
**Scope:** Full Q-Guardian codebase (`src/q_guardian/`, configuration, deployment)
**Reviewer:** Automated Security Analysis
**Version Under Review:** 0.9.0

---

## Executive Summary

Q-Guardian is a hybrid quantum-classical framework for runtime security of autonomous AI agents. The codebase demonstrates strong architectural foundations with Pydantic validation, structured logging via structlog, a well-designed plugin system, and proper separation of concerns. However, several security issues were identified ranging from critical to low severity.

**Overall Security Posture:** Moderate — solid design patterns with notable gaps in production hardening.

| Severity | Count | Summary |
|----------|-------|---------|
| **Critical** | 2 | joblib deserialization vulnerability; default secret key accepted outside production |
| **High** | 3 | MongoDB credentials logged in plaintext; CORS wildcard methods/headers in dev defaults; no authentication middleware implemented |
| **Medium** | 5 | joblib.load without integrity verification; plugin system loads untrusted code via entry points; MongoDB port exposed on host; source code volume-mounted; debug=true in docker-compose |
| **Low** | 6 | Default secret key placeholder; 0.0.0.0 binding; dependency version ranges (not pinned); X-Response-Time header leaks internal timing; exception traceback in logs; no rate limiting enabled by default |

---

## 1. Dependency Analysis

### 1.1 Core Dependencies (pyproject.toml)

| Dependency | Version Spec | Concern |
|------------|-------------|---------|
| `fastapi>=0.115.0` | Range spec | **No upper bound** — a breaking change in a future release could introduce vulnerabilities or break the application. Should use `>=0.115.0,<1.0.0` |
| `pydantic>=2.10.0` | Range spec | Same concern — should be bounded |
| `python-jose[cryptography]>=3.3.0` | Range spec | `python-jose` is **unmaintained** (last release 2021). Consider migrating to `PyJWT` which is actively maintained and has better security track record |
| `passlib[bcrypt]>=1.7.0` | Range spec | `passlib` is **unmaintained** (last release 2020). Consider using `bcrypt` directly |
| `orjson>=3.10.0` | Range spec | Acceptable but should be bounded |
| `httpx>=0.28.0` | Range spec | Acceptable but should be bounded |
| `motor>=3.7.0` | Range spec | Acceptable but should be bounded |
| `structlog>=24.0.0` | Range spec | Acceptable but should be bounded |

### 1.2 Optional Dependencies

| Dependency | Concern |
|------------|---------|
| `qiskit>=1.0.0` | Large attack surface; ensure pinned to known-good version in production |
| `scikit-learn>=1.3.0` | Relatively stable; pin in production |
| `joblib` (transitive via scikit-learn) | **Critical** — see Section 5.1 |

### 1.3 requirements.txt vs pyproject.toml

`requirements.txt` uses exact pins (`==`) while `pyproject.toml` uses ranges (`>=`). This is inconsistent. Production deployments should use the pinned file, but the `requirements.txt` contains a formatting error on line 28:

```
# --- Utilities orjson==3.10.13
```

This line is missing a newline — the `orjson` dependency is appended to a comment. This means **orjson is not installed** via `requirements.txt`, which would cause a runtime import failure.

**Recommendations:**
1. Pin all dependencies in both files with upper bounds (e.g., `>=X.Y.Z,<X+1.0.0`)
2. Migrate from `python-jose` to `PyJWT`
3. Migrate from `passlib` to `bcrypt` directly
4. Fix the `requirements.txt` formatting error on line 28
5. Add `pip-audit` or `safety` to CI pipeline for vulnerability scanning
6. Generate `requirements.lock` for reproducible builds

---

## 2. Input Validation

### 2.1 Prompt Scanning Pipeline

The prompt security pipeline (`security/pipeline.py`) implements solid validation:

- **PromptNormalizer:** NFKC normalization, hidden character stripping, line ending normalization — well implemented
- **PromptValidator:** Checks length, line count, encoding corruption, null bytes — good
- **PromptFeatureExtractor:** Entropy calculation, keyword matching, pattern detection — no injection risk
- **RuleEngine:** Uses `re.search` with patterns from `PromptRule` objects — **safe** (no user-controlled regex compilation from raw input)

**Positive:** The `RuleEngine` only executes against a predefined set of `PromptRule` objects. User input is never used to construct regex patterns directly — only matched against them. This prevents regex injection attacks.

**Concern:** The `max_prompt_length` default is 100,000 characters. While this is validated, processing very large prompts through the full pipeline could cause performance issues (denial of service via resource exhaustion).

### 2.2 Policy Condition Parser

The condition parser (`policy/core/condition_parser.py`) uses a hand-written recursive-descent parser. This is **safe by design** — it tokenizes and parses into a structured AST (`Condition`/`CompoundCondition`) rather than executing arbitrary code.

**Concern:** The `MATCHES` and `NOT_MATCHES` operators use `re.search()` with user-provided patterns (`policy/data.py:72-76`). If policy condition patterns are sourced from untrusted input, this could enable **ReDoS (Regular Expression Denial of Service)** attacks via crafted pathological regex patterns.

```python
# policy/data.py:72-73 — user-supplied regex pattern
if op == ComparisonOperator.MATCHES:
    return bool(re.search(str(expected), str(actual)))
```

### 2.3 API Endpoint Input

FastAPI + Pydantic provide automatic request validation. Exception handlers (`exceptions/handlers.py`) return structured error responses. The `RequestValidationError` handler properly formats validation errors.

**Concern:** The `general_exception_handler` returns `type(exc).__name__` in error details, which is minimal information leakage — acceptable but worth noting.

### 2.4 Correlation ID

The correlation middleware (`middleware/correlation.py:42-44`) accepts client-provided correlation IDs without validation:

```python
correlation_id = request.headers.get(CORRELATION_ID_HEADER)
if not correlation_id:
    correlation_id = uuid.uuid4().hex[:12]
```

A malicious client could inject very long strings or special characters as correlation IDs, which would be logged and included in response headers. No length or format validation is applied.

**Recommendations:**
1. Validate correlation ID format (e.g., max 128 chars, alphanumeric only)
2. Add timeout limits for prompt processing (e.g., 30s max)
3. Sanitize or bound ReDoS risk in policy regex patterns — add regex timeout or complexity limits
4. Validate/sanitize correlation IDs to prevent log injection

---

## 3. Secrets Management

### 3.1 .env.example

The `.env.example` file properly includes comments warning against committing `.env`. However:

**Critical:** The default `SECRET_KEY=change-me-to-a-random-secret-key` is a well-known placeholder. The validation in `SecuritySettings` (`config/settings.py:116-121`) only enforces changing it in production:

```python
if value == "change-me-to-a-random-secret-key":
    if os.getenv("ENVIRONMENT") == "production":
        raise ValueError("SECRET_KEY must be changed in production!")
```

This means:
- In development/testing, the default key is used — acceptable for local dev
- If someone forgets to set `ENVIRONMENT=production` in production, the default key is used
- The check relies on the `ENVIRONMENT` env var being set correctly

**High:** MongoDB connection URL is logged at INFO level (`database/client.py:43`):

```python
logger.info("mongodb_connecting", url=self._settings.database.url, ...)
```

If the MongoDB URL contains credentials (e.g., `mongodb://user:password@host:27017`), they would appear in logs.

### 3.2 Credential Storage

- `response/data.py:368`: `IntegrationConfig.api_key: str = ""` — API keys stored as plain strings in Pydantic models. No encryption at rest.
- `observability/integrations/datadog.py:22`: `api_key` and `app_key` stored as plain instance attributes
- `observability/integrations/grafana.py:22`: `api_key` stored as plain instance attribute
- `quantum/backends/qiskit_backend.py:155`: IBM Quantum `token` stored as plain instance attribute

**Recommendations:**
1. Add production environment detection hardening — fail startup if `SECRET_KEY` is default AND `ENVIRONMENT` is not explicitly set to `development`
2. Sanitize or mask MongoDB URLs in log output
3. Use a secrets vault (e.g., HashiCorp Vault, AWS Secrets Manager) for production credential storage
4. Add `__repr__` overrides on models containing secrets to prevent accidental logging
5. Consider encrypting sensitive fields in `IntegrationConfig`

---

## 4. Authentication & Authorization

### 4.1 Implementation Status

All authentication and authorization services are **placeholders** (`security/auth.py`):

- `JWTService`: Raises `NotImplementedError`
- `AuthenticationService`: Raises `NotImplementedError`
- `AuthorizationService`: Raises `NotImplementedError`
- `APIKeyService`: Raises `NotImplementedError`
- `RateLimitService`: Raises `NotImplementedError`

**High:** The API is currently **completely unauthenticated**. Any client can call any endpoint. This is acceptable for development but must be implemented before production deployment.

### 4.2 CORS Configuration

The CORS settings (`config/settings.py:136-142` and `.env.example:35-38`) default to:

```python
allow_methods: list[str] = ["*"]  # ALL methods
allow_headers: list[str] = ["*"]  # ALL headers
allow_credentials: bool = True
```

**High:** Wildcard `["*"]` methods and headers combined with `allow_credentials=True` is insecure. While this is development-only configuration, it could easily leak to production if not properly overridden.

**Note:** FastAPI's `CORSMiddleware` will correctly handle the combination, but `allow_methods=["*"]` and `allow_headers=["*"]` with credentials is overly permissive.

### 4.3 Security Headers

The `SecurityHeadersMiddleware` (`security/headers.py`) adds well-chosen headers:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `X-Permitted-Cross-Domain-Policies: none`
- `Cache-Control: no-store, no-cache, must-revalidate`

**Missing:** `Content-Security-Policy` header is not set. While primarily relevant for browser-rendered content, it's good defense-in-depth.

**Concern:** `Strict-Transport-Security` (HSTS) is not set. Should be added when TLS is deployed.

**Recommendations:**
1. Implement authentication middleware before production
2. Restrict CORS to specific origins, methods, and headers in production
3. Add `Content-Security-Policy` and `Strict-Transport-Security` headers
4. Implement rate limiting before production (currently disabled by default)
5. Add API key validation to at least protect write endpoints

---

## 5. Plugin System Security

### 5.1 Plugin Loading Mechanism

The plugin registry (`plugins/registry.py`) supports two plugin loading methods:

1. **Direct registration:** `registry.register_plugin(MyPlugin())` — safe, controlled by application code
2. **Entry point discovery:** `PluginRegistry.discover_plugins()` (`registry.py:258-298`) — loads plugins via Python entry points

```python
plugin_class = ep.load()  # Loads arbitrary Python code
if isinstance(plugin_class, type) and issubclass(plugin_class, Plugin):
    discovered.append(plugin_class())
```

**Medium:** Entry point discovery loads and instantiates arbitrary Python code. While it validates the class inherits from `Plugin`, the `__init__`, `initialize`, `start`, and `stop` methods can execute arbitrary code. If an attacker can install a Python package on the system, they can achieve code execution through this mechanism.

**Mitigating factor:** This requires package installation access, which already implies a high level of system compromise.

### 5.2 ML Model Deserialization (Critical)

The `ModelStorage` class (`ml/storage.py`) uses `joblib.dump()` and `joblib.load()`:

```python
# ml/storage.py:46-52
import joblib

joblib.dump(model, artifact_path)

# ml/storage.py:81-92
import joblib

model = joblib.load(artifact_path)
```

**Critical:** `joblib.load()` uses Python pickle under the hood, which can execute arbitrary code during deserialization. If an attacker can write to the model storage directory, they can achieve remote code execution by replacing a `.joblib` file with a malicious pickle payload.

**Current mitigating factors:**
- Models are stored on the local filesystem
- No remote model loading is implemented
- The `ModelStorage` class creates the directory locally

**Required mitigations:**
1. Validate model file integrity (hash/checksum verification) before loading
2. Consider switching to a safer serialization format (ONNX, safetensors)
3. Add file permission checks on the model directory
4. Implement model signing/verification

### 5.3 Plugin Lifecycle

The plugin lifecycle management is well-structured:
- Plugins have clear `REGISTERED -> INITIALIZING -> RUNNING -> STOPPED` states
- Failed plugins are isolated (marked as ERROR)
- Stop order is reverse registration order (good)

**Positive:** No plugins execute code from untrusted sources. The `PromptScannerPlugin` uses only predefined rules and local configuration.

---

## 6. Serialization Security

### 6.1 JSON Handling (orjson)

The `json_utils.py` module uses `orjson` for JSON serialization:

```python
def json_loads(data: bytes | str) -> Any:
    return orjson.loads(data)
```

**Positive:** `orjson` is a safe, high-performance JSON library. It does not execute code during deserialization. No concerns here.

### 6.2 YAML Handling

The framework config loader (`framework/config.py:154-164`) uses `yaml.safe_load()`:

```python
data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
```

**Positive:** `yaml.safe_load()` prevents YAML deserialization attacks (unlike `yaml.load()` without `Loader=SafeLoader`). This is correctly implemented.

### 6.3 joblib Deserialization

Covered in Section 5.2 — this is the primary serialization concern.

### 6.4 No Pickle Usage

Grep found no direct `pickle` usage in the codebase. The only deserialization risk is through `joblib` (which uses pickle internally).

**Recommendations:**
1. Add checksum/hash verification for ML model files before `joblib.load()`
2. Consider migrating to `safetensors` format when ML models are productionized
3. Document the serialization security considerations

---

## 7. Configuration Security

### 7.1 Default Values

| Setting | Default | Concern |
|---------|---------|---------|
| `debug: bool` | `True` | Should default to `False` |
| `host: str` | `0.0.0.0` | Binds to all interfaces — should be `127.0.0.1` by default |
| `secret_key` | `"change-me-to-a-random-secret-key"` | Known placeholder |
| `jwt_algorithm` | `HS256` | Acceptable, but RS256 recommended for production |
| `rate_limit_enabled` | `false` | Should be `true` by default |
| `CORS_ALLOW_METHODS` | `["*"]` | Overly permissive |
| `CORS_ALLOW_HEADERS` | `["*"]` | Overly permissive |
| `max_prompt_length` | `100,000` | Reasonable but consider lower default |
| `CORS_ALLOW_CREDENTIALS` | `true` | Combined with wildcard methods/headers is problematic |

### 7.2 Environment Profiles

The `Environment` enum supports `DEVELOPMENT`, `TESTING`, and `PRODUCTION`. The secret key validator correctly checks `ENVIRONMENT == "production"`, but:

**Concern:** The `get_settings()` function uses `lru_cache(maxsize=1)`, meaning settings are loaded once and cached. If the environment changes (e.g., env var is updated after startup), it won't be picked up. This is standard behavior but worth noting for container deployments.

### 7.3 Docker Compose Configuration

```yaml
environment:
  - ENVIRONMENT=development
  - DEBUG=true
```

**Medium:** `docker-compose.yml` hardcodes `development` environment and `debug=true`. If used in production without override, this would bypass the secret key validation.

**Recommendations:**
1. Default `debug` to `False`
2. Default `host` to `127.0.0.1` (use docker networking for container communication)
3. Enable rate limiting by default
4. Restrict CORS defaults for production
5. Use environment-specific docker-compose files (e.g., `docker-compose.prod.yml`)
6. Add a startup check that fails if production environment detects development settings

---

## 8. Network Security

### 8.1 HTTP Client Usage

The codebase uses `httpx` as the HTTP client. No instances of `verify=False` or SSL bypass were found — **positive**.

### 8.2 MongoDB Connection

```python
# database/client.py
self._client = AsyncIOMotorClient(
    self._settings.database.url,
    **self._settings.database.client_kwargs,
)
```

**Concern:** No TLS/SSL configuration for MongoDB connections. The default URL `mongodb://localhost:27017` uses unencrypted connections. Production MongoDB deployments should use TLS.

### 8.3 External Service Integration

The `WebhookNotifier` (`response/notifications/webhook.py`) accepts URLs at runtime. No URL validation or SSRF protection is implemented:

```python
def __init__(self, url: str = "", headers: dict[str, str] | None = None) -> None:
    self._url = url
```

If webhook URLs come from user input, this could enable SSRF attacks.

### 8.4 Health Check Endpoint

The Docker health check (`docker/Dockerfile:25`) makes an HTTP request:

```dockerfile
HEALTHCHECK CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health').raise_for_status()
```

**Low:** This is standard practice and not a security concern, but the health check should validate response status.

**Recommendations:**
1. Configure MongoDB TLS for production
2. Add URL validation/allowlisting for webhook endpoints
3. Validate that httpx client uses SSL verification by default

---

## 9. Container Security

### 9.1 Dockerfile Analysis

```dockerfile
FROM python:3.12-slim           # Good — slim base
RUN useradd --create-home --shell /bin/bash appuser  # Good — non-root
USER appuser                     # Good — runs as non-root
```

**Positive:**
- Uses slim base image (smaller attack surface)
- Creates and runs as non-root user
- Uses `--no-cache-dir` for pip (no cached wheels in image)
- Uses `--no-install-recommends` for apt (minimal packages)
- Health check is configured

**Concerns:**

| Issue | Severity | Detail |
|-------|----------|--------|
| No `.dockerignore` check | Low | Verify `.dockerignore` exists and excludes `.env`, `.git`, `__pycache__` |
| No read-only filesystem | Low | Container filesystem is writable; consider `--read-only` with tmpfs for `/tmp` |
| No resource limits | Medium | No `mem_limit`, `cpus` in docker-compose |
| No seccomp/AppArmor profile | Low | Default profiles are used |
| Source code volume-mounted | Medium | `volumes: - ../src:/app/src` mounts source — development only, but could expose host filesystem |

### 9.2 Docker Compose Analysis

**Medium concerns:**
- MongoDB port `27017` is exposed on the host (`ports: - "27017:27017"`) — should only be exposed in development
- No MongoDB authentication configured (no `--auth`, no `MONGO_INITDB_ROOT_USERNAME/PASSWORD`)
- No network segmentation beyond basic bridge
- No resource limits (`mem_limit`, `cpus`)

**Recommendations:**
1. Add `.dockerignore` if not present
2. Add resource limits to docker-compose services
3. Don't expose MongoDB port in production
4. Enable MongoDB authentication
5. Create separate `docker-compose.prod.yml` with hardened settings
6. Add `read_only: true` to API container in production
7. Use Docker secrets for sensitive configuration instead of environment variables

---

## 10. Logging Security

### 10.1 Information Leakage

**Medium:** The exception middleware (`middleware/exception.py:50`) logs full tracebacks:

```python
logger.error("unhandled_exception", traceback=traceback.format_exc())
```

While this is standard for debugging, full tracebacks can reveal:
- Internal file paths
- Library versions
- Code structure

The `general_exception_handler` (`exceptions/handlers.py:70-79`) returns only `type(exc).__name__` in error responses — this is properly minimal.

### 10.2 Sensitive Data in Logs

**High:** MongoDB URL logged at INFO level (`database/client.py:43`) may contain credentials.

The `exc_info=True` pattern is used throughout the codebase (21 instances), which is appropriate for server-side logging.

### 10.3 Structured Logging

**Positive:** The codebase uses `structlog` consistently, which provides structured, machine-parseable logs. This aids in security monitoring and incident response.

**Recommendations:**
1. Sanitize sensitive fields (URLs with credentials, API keys) before logging
2. Consider using `structlog` processors for automatic secret redaction
3. Ensure log files have appropriate permissions (not world-readable)

---

## 11. Code Quality & Safety

### 11.1 Dangerous Function Usage

| Function | Found | Assessment |
|----------|-------|------------|
| `eval()` / `exec()` | **None** | Clean — no dynamic code execution |
| `pickle` | **None** | Clean — no direct pickle usage |
| `subprocess` | **None** | Clean — no subprocess calls |
| `__import__` | **1 instance** | `policy/composition/__init__.py:51` — unusual `__import__("datetime")` usage; not a security issue but poor style |

### 11.2 Type Safety

**Positive:** The codebase uses `mypy` with strict mode enabled (`pyproject.toml:105-112`). This catches many classes of bugs at development time.

### 11.3 Regex Safety

The policy condition parser's `MATCHES` operator accepts user-provided regex patterns. As noted in Section 2.2, this is a ReDoS vector.

---

## 12. Recommendations — Prioritized

### Critical (Fix Before Production)

1. **ML Model Integrity Verification** — Add checksum/hash verification before `joblib.load()` in `ml/storage.py`. Consider migrating to `safetensors` format.
2. **Secret Key Hardening** — Fail startup in production if `SECRET_KEY` is the default value AND `ENVIRONMENT` is not explicitly set to `development`. Add minimum entropy requirements for the secret key.

### High (Fix Before Production)

3. **Authentication Implementation** — Implement JWT/API key authentication middleware before exposing the API to untrusted clients.
4. **MongoDB Credential Logging** — Sanitize the MongoDB URL before logging in `database/client.py:43`.
5. **CORS Production Defaults** — Ensure production configuration restricts CORS origins, methods, and headers. Add environment-based validation.
6. **Rate Limiting** — Enable rate limiting by default, or require explicit opt-out in production configuration.

### Medium (Address Soon)

7. **Dependency Pinning** — Pin all dependencies with upper bounds in `pyproject.toml`. Fix the `requirements.txt` formatting error.
8. **Joblib Migration Path** — Plan migration from `joblib` to a safer serialization format (ONNX/safetensors) for ML model persistence.
9. **Plugin Discovery Security** — Add validation/signing for entry-point-discovered plugins. Consider allowing only explicitly trusted plugin packages.
10. **ReDoS Protection** — Add regex complexity limits or timeouts for policy `MATCHES` operator.
11. **Docker Hardening** — Add resource limits, don't expose MongoDB port in production, enable MongoDB authentication.
12. **Correlation ID Validation** — Validate format and length of client-provided correlation IDs.

### Low (Address When Possible)

13. **Missing Security Headers** — Add `Content-Security-Policy` and `Strict-Transport-Security` headers.
14. **Dependency Migration** — Migrate from `python-jose` to `PyJWT` and from `passlib` to `bcrypt` directly.
15. **Secret Field Protection** — Add `__repr__` overrides on models containing API keys/secrets.
16. **Webhook URL Validation** — Add URL allowlist/validation for webhook endpoints.
17. **MongoDB TLS** — Configure TLS for MongoDB connections in production.
18. **Timing Header** — Consider whether `X-Response-Time` should be exposed in production responses (information leakage for timing attacks).
19. **Log File Permissions** — Ensure log files are created with restrictive permissions (0600).

---

## 13. Positive Findings

The codebase demonstrates several security-positive patterns:

1. **No dynamic code execution** — No `eval()`, `exec()`, or `pickle` usage
2. **Safe YAML loading** — `yaml.safe_load()` used correctly
3. **Structured input validation** — Pydantic models throughout
4. **Proper exception handling** — No stack traces leaked to clients
5. **Security headers middleware** — Comprehensive header set
6. **Non-root Docker execution** — Proper container hardening
7. **Structured logging** — `structlog` used consistently for audit trails
8. **Separation of concerns** — Clear module boundaries reduce attack surface
9. **Plugin lifecycle management** — Proper state machine for plugin states
10. **Decision engine** — Well-structured risk scoring with configurable thresholds
11. **Safe regex usage** — Rule engine only matches against predefined patterns, never compiles user input
12. **Type-safe codebase** — Strict mypy configuration catches many bug classes

---

*This review covers the codebase as of the current state. Security is a continuous process — regular reviews should be conducted as the codebase evolves, especially before major releases or production deployments.*
