# 10 - Security Overview

> Module: `src\q_guardian\security\` + HTTP middleware + configuration — the
> defense-in-depth surface of Q-Gaudrail v1.1.0.
>
> Q-Gaudrail protects AI agents at two levels: **HTTP transport** (headers, CORS,
> correlation IDs, exception hygiene) and **application-level prompt security**
> (normalization, validation, feature extraction, rule detection, decision making).
> A third level — authentication (JWT + API keys) and authorization — is
> implemented and enforced on every protected v1 endpoint (see §5).

---

## 1. Security Layers Map

```
LEVEL 0 — TRANSPORT (Starlette/FastAPI)
   api/app.py registers (outer -> inner):
     1. CorrelationIDMiddleware      -> X-Correlation-ID
     2. ResponseTimingMiddleware     -> X-Response-Time
     3. ExceptionLoggingMiddleware   -> logs tracebacks, re-raises
     4. SecurityHeadersMiddleware    -> 7 hardened headers
     5. CORSMiddleware               -> config.cors
     6. TrustedHostMiddleware        -> dev only

LEVEL 1 — PROMPT SECURITY ENGINE (src/q_guardian/security/)
   PromptScannerPlugin (name="prompt-scanner", v1.0.0)
     Normalize -> Validate -> Extract Features -> Rule Engine -> Decision Engine
     emits 7 events, updates SecurityContext, callable via Guardian.scan_prompt()

LEVEL 2 — DETECTION EXTENSIONS (future + partial)
   PromptDetector / PromptClassifier / FeatureProvider / ThreatClassifier ABCs
   implemented by ml/* and quantum/* modules (documented in 12)

LEVEL 3 — POLICY + RISK + RESPONSE (see docs 13, 14)
   BLOCK/WARN/REVIEW/ALLOW feed into RiskAssessment -> PolicyDecision -> Response

LEVEL 4 — AUTHN/Z + RATE LIMITING (implemented, §5)
   security/auth.py: JWTService, AuthenticationService, AuthorizationService,
   APIKeyService, RateLimitService  (all functional, enforced on protected
   /api/v1 endpoints via the router-level get_current_principal dependency)
```

---

## 2. HTTP Transport Security

### 2.1 `SecurityHeadersMiddleware` — `src\q_guardian\security\headers.py`

A `BaseHTTPMiddleware` that stamps every response with 7 headers
(`SECURITY_HEADERS` class constant, exact values):

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `X-Permitted-Cross-Domain-Policies` | `none` |
| `Cache-Control` | `no-store, no-cache, must-revalidate` |
| `Pragma` | `no-cache` |

### 2.2 CORS — `src\q_guardian\security\cors.py`

`get_cors_middleware(app)` registers Starlette `CORSMiddleware` from
`settings.cors` (`CORSSettings`, env prefix `CORS_`):

| Setting | Default |
|---------|---------|
| `origins` | `["http://localhost:3000", "http://localhost:8080"]` |
| `allow_credentials` | `true` |
| `allow_methods` | `["*"]` |
| `allow_headers` | `["*"]` |

### 2.3 Correlation & Timing — `src\q_guardian\middleware\`

| Middleware | Behavior |
|------------|----------|
| `CorrelationIDMiddleware` | Accepts a client-provided `X-Correlation-ID` or generates `uuid.uuid4().hex[:12]`; stores on `request.state.correlation_id`, binds to structlog contextvars, echoes the header back on the response. |
| `ResponseTimingMiddleware` | Measures `time.perf_counter()` duration; sets `X-Response-Time: {ms}ms`; debug-logs `response_timing`. |
| `ExceptionLoggingMiddleware` | Catches exceptions, logs `unhandled_exception` with `traceback.format_exc()`, then re-raises so exception handlers respond properly. |

> Note: `logging/middleware.py`'s `RequestLoggingMiddleware` (per-request start/end
> logs + response-time header) is exported but the app factory uses the three
> `middleware/` classes instead.

### 2.4 Error Response Hygiene

`src\q_guardian\exceptions\handlers.py` registers
`application_exception_handler` and `validation_exception_handler`, producing the
structured `ErrorResponseSchema` envelope (`success=False`, `error` dict,
`timestamp`, `correlation_id`). Exception taxonomy lives in
`src\q_guardian\exceptions\base.py`:

| Exception | `code` | `status_code` |
|-----------|--------|---------------|
| `ApplicationException` | base | 500 |
| `DatabaseException` | `DATABASE_ERROR` | 503 |
| `ExternalServiceException` | external | — |
| `SecurityException` | security | — |
| `ValidationException` | validation | — |

---

## 3. Prompt Security Engine — `src\q_guardian\security\`

### 3.1 Pipeline Components — `src\q_guardian\security\pipeline.py`

The pipeline is modular: every stage is usable standalone.

**`PromptNormalizer`** — normalization for consistent analysis:

1. Unicode NFKC normalization (`unicodedata.normalize("NFKC", prompt)`)
2. Line-ending normalization (`\r\n` → `\n`, `\r` → `\n`)
3. Remove hidden/invisible characters via `_remove_hidden_chars` (drops Unicode
   categories `Cf`=format and `Cc`=control; preserves `\n` and `\t`)
4. Strip leading/trailing whitespace
5. Collapse whitespace runs to a single space, preserving newlines
   (`re.sub(r"[^\S\n]+", " ", text)`)
6. Collapse 3+ blank lines to exactly 2 (`re.sub(r"\n{3,}", "\n\n", text)`)

**`PromptValidator`** — input limits (defaults `max_length=100_000`,
`min_length=1`, `max_lines=10_000`):

- Empty/too-short → INVALID (immediate return)
- Over length → INVALID
- Over line count → INVALID
- Replacement character `\ufffd` (malformed encoding) → INVALID
- Null byte `\x00` → INVALID
- Otherwise → `(VALID, [])`

**`PromptFeatureExtractor`** — produces `PromptFeatures`:

- `token_estimate = max(1, char_count // 4)` (≈4 chars/token BPE approximation)
- `special_chars` = non-alphanumeric, non-whitespace count
- `code_block_count = prompt.count("```") // 2`
- `url_count` via `r"https?://\S+"`
- Markdown detection (headers, `**bold**`, `__bold__`, list items, numbered lists, inline code)
- `repeated_patterns`: words (length ≥ 3) appearing ≥ 3 times
- `entropy`: Shannon entropy `-Σ p·log2(p)`, rounded to 4 decimals
- `suspicious_keywords` (default list below), `has_unicode_escaped`
  (`\uXXXX`), `has_html_tags` (`<[^>]+>`), `uppercase_ratio` (over alpha chars),
  `digit_ratio`

**`RuleEngine`** — configurable rule scanning. For each enabled rule, keyword
match first (case-insensitive substring), regex fallback
(`re.search(pattern, prompt, re.IGNORECASE)`, matched text truncated to 100 chars);
each match yields a `PromptFinding` with the rule's `confidence`.

### 3.2 Default Detection Content

**`_DEFAULT_SUSPICIOUS_KEYWORDS`** (exact list):

```
ignore previous, ignore all, disregard, forget everything, new instructions,
system prompt, you are now, act as, pretend to be, jailbreak, dan mode,
do anything now, bypass, override, admin mode, developer mode, debug mode,
root access, sudo, unrestricted
```

**`DEFAULT_RULES`** — 10 rules (quoted exactly):

| ID | Name | Category | Severity | Trigger |
|----|------|----------|----------|---------|
| `pi-001` | Ignore Previous Instructions | PROMPT_INJECTION | HIGH (0.9) | "ignore previous", "ignore all previous", "disregard previous" |
| `pi-002` | Instruction Override | PROMPT_INJECTION | HIGH (0.85) | "new instructions", "new system prompt", "forget everything" |
| `jb-001` | Role Manipulation | ROLE_MANIPULATION | MEDIUM (0.7) | "you are now", "act as", "pretend to be", "roleplay as" |
| `jb-002` | Jailbreak Phrases | JAILBREAK | HIGH (0.85) | "dan mode", "do anything now", "jailbreak", "unrestricted mode" |
| `jb-003` | Developer/Debug Mode | JAILBREAK | MEDIUM (0.75) | "developer mode", "debug mode", "admin mode", "sudo mode" |
| `sp-001` | System Prompt Reference | SYSTEM_PROMPT_LEAK | MEDIUM (0.7) | "system prompt", "your instructions", "your prompt", "initial prompt" |
| `sp-002` | Prompt Extraction Attempt | SYSTEM_PROMPT_LEAK | HIGH (0.85) | "repeat your instructions", "show me your prompt", "what is your system prompt", "print your instructions" |
| `enc-001` | Excessive Encoding | EXCESSIVE_ENCODING | MEDIUM (0.7) | regex `\uXXXX` and `&#x...;` |
| `fmt-001` | Suspicious Formatting | SUSPICIOUS_FORMATTING | LOW (0.5) | regex `\n{5,}`, `[\t ]{20,}`, `[^\x00-\x7F]{50,}` |
| `pi-003` | Bypass Attempt | PROMPT_INJECTION | HIGH (0.8) | "bypass", "override system", "break your rules", "ignore your rules" |

### 3.3 Decision Engine — `src\q_guardian\security\decision.py`

`SecurityDecisionEngine(block_on_critical=True, block_on_high_count=2,
review_on_high_count=1, warn_on_medium_count=1)`.

`decide(analysis)` — exact cascade:

```
no findings          -> ALLOW,  risk_score=0.0, "No security concerns detected."
CRITICAL > 0         -> BLOCK   "BLOCK: {n} critical severity finding(s) detected."
HIGH >= 2            -> BLOCK   "BLOCK: {n} high severity finding(s) exceed threshold."
HIGH >= 1            -> REVIEW  "REVIEW: {n} high severity finding(s) require review."
MEDIUM >= 1          -> WARN    "WARN: {n} medium severity finding(s) detected."
else                 -> ALLOW   "ALLOW: Findings are low severity; prompt is likely safe."
```

`_compute_risk_score(findings)` — severity-weighted, confidence-scaled:

```
weights = {INFO: 0.1, LOW: 0.2, MEDIUM: 0.5, HIGH: 0.8, CRITICAL: 1.0}
total   = Σ (weight(severity) * finding.confidence)
raw     = total / len(findings)
score   = min(1.0, raw * 1.2)      # sigmoid-like scaling
```

### 3.4 Plugin — `src\q_guardian\security\plugin.py`

`PromptScannerPlugin` (`name="prompt-scanner"`, `version="1.0.0"`,
`author="Q-Guardian"`, `interfaces=["prompt_scanner"]`). `scan_prompt(prompt)`
runs the full pipeline (normalize → validate → extract → rules → decide), stamps
`processing_time_ms`, increments `scan_count`/`block_count`, publishes events, and
returns `analysis.model_dump()`.

Events published (source `"plugin:prompt-scanner"`):
`PromptNormalized` → `PromptValidated` → `PromptFeaturesExtracted` →
`PromptRuleMatched` (one per finding) → `PromptAnalysisCompleted` →
`PromptBlocked` or `PromptAllowed`. Event types:
`security.prompt.normalized`, `security.prompt.validated`,
`security.prompt.features`, `security.prompt.rule_matched`,
`security.prompt.analysis_completed`, `security.prompt.blocked`,
`security.prompt.allowed`.

### 3.5 Configuration — `src\q_guardian\security\config.py`

`PromptSecurityConfig` (see `docs/08_Data_Model_Documentation.md` §3.3) is the single
tunable surface: length limits, enabled/disabled/custom rules, severity thresholds,
logging flags, suspicious keyword override, and future ML/Quantum enablement flags.

---

## 4. Extensibility Contract — `src\q_guardian\security\extensibility.py`

ABCs that external detection modules implement:

| ABC | Contract |
|-----|----------|
| `PromptDetector` | `name` property; `async detect(prompt, features) -> DetectionResult`; built-in `health()`. |
| `PromptClassifier` | `name` property; `async classify(prompt, features) -> dict[str, float]` (category→probability). |
| `FeatureProvider` | `name` property; `async extract_features(prompt, base_features) -> dict`. |
| `ThreatClassifier` | `name` property; `async classify_quantum(prompt, features) -> DetectionResult`. |
| `DetectionResult` | Pydantic model: `detector_name`, `findings: list[PromptFinding]`, `risk_score`, `confidence`, `metadata`. |

Implementation status:

- **ML (module 5)**: `ml/models/*` implement `PromptDetector`/`PromptClassifier`;
  `ml/feature_pipeline.py` implements `FeatureProvider`.
- **Quantum (module 6)**: `quantum/models/base.py` and `quantum/models/qsvm.py`
  implement `ThreatClassifier`/`PromptDetector`.
- The documented integration point: `PromptScannerPlugin` will call `detect()` and
  merge `DetectionResult.findings` into the analysis *before*
  `SecurityDecisionEngine` runs.

---

## 5. Auth / API Security — `src\q_guardian\security\auth.py`

Authentication and authorization are fully implemented and enforced at the
router level: every endpoint under `/api/v1` except `GET /api/v1/health`
requires a principal, resolved by the `get_current_principal` dependency
(`security/http_auth.py`) from either:

1. `Authorization: Bearer <jwt>` — an access token from `JWTService`, checked
   against the persistent token blocklist (`security/token_blocklist.py`) so
   logged-out/revoked tokens stay rejected; or
2. the `X-API-Key` header (configurable via `api_key_header`) validated by
   `APIKeyService`.

Unauthenticated or invalid requests produce the structured 401 envelope via
the global exception handlers; `AuthenticationError` carries a stable
machine-readable `reason` (`missing_credentials`, `invalid_token`,
`token_revoked`, `invalid_api_key`, …).

| Component | Capability | Public API |
|-----------|------------|------------|
| `hash_password` / `verify_password` | bcrypt hashing (72-byte input limit) | module-level helpers |
| `JWTService` | HS256 access + refresh tokens, distinguished by a `type` claim so one kind never replays as the other | `create_access_token(claims)`, `create_refresh_token(claims)`, `verify_token(token, expected_type=…)` |
| `AuthenticationService` | username/password login, durable registration, token refresh + revocation | `authenticate`, `register_user`, `refresh`, `revoke_tokens`, `users_configured` |
| `AuthorizationService` | role → permission mapping | `assign_role`, `get_user_roles` |
| `APIKeyService` | key lifecycle | `generate_api_key`, `authenticate_api_key`, `revoke_api_key`, `list_api_keys` |
| `RateLimitService` | in-memory sliding-window throttle | `check_rate_limit(identifier, limit, window)`, `retry_after`, `reset` |

**Provisioning:**

- **Users**: `AUTH_USERS` env var (JSON `{username: {password_hash, roles}}`
  with bcrypt hashes) plus the persistent MongoDB `user_repository`; accounts
  created through the console register flow always get the standard
  `analyst` role.
- **API keys**: `API_KEYS` env var (comma-separated raw `qg_…` keys or
  `sha256:<hexdigest>` entries); keys are stored as SHA-256 digests — raw key
  material is never persisted.

**Enforcement points:**

- Router-level `dependencies=[Depends(get_current_principal)]` on
  `api_v1_router` (`api/v1/router.py`) protects analysis, console, system,
  datasets, training, scans, analytics and reports; `public_router` (health)
  stays unauthenticated so orchestrators can probe readiness.
- `api/v1/endpoints/auth.py` (`/api/v1/auth`): `login`, `refresh`,
  `register`, `logout`. Bootstrap routes are public by design; `logout`
  re-authenticates at the endpoint so a caller can only revoke its own
  tokens. Login and registration are throttled to 5 attempts per IP+username
  per 15 minutes (`_check_login_rate_limit`).
- The console ships a login view and stores issued tokens client-side
  (`ui/static/js/auth.js`, `ui/static/js/views/login.js`); `ui/static/js/api.js`
  attaches the `Authorization` header to every API call.

Related config lives in `SecuritySettings` (`src\q_guardian\config\settings.py`,
env prefix empty):

| Setting | Default |
|---------|---------|
| `secret_key` | `"change-me-to-a-random-secret-key"` |
| `jwt_algorithm` | `"HS256"` |
| `jwt_expiration_minutes` | `30` |
| `jwt_refresh_expiration_days` | `7` |
| `api_key_header` | `"X-API-Key"` |

**Secret handling**: `validate_secret_key` field validator refuses to boot in
`ENVIRONMENT=production` while `SECRET_KEY` is still the default placeholder
(`ValueError("SECRET_KEY must be changed in production!")`). `.env.example` ships
the placeholder — rotate it before any real deployment (see `docs/11_Deployment_Guide.md`).

---

## 6. Runtime Security State

As plugins analyze traffic, they update the shared `SecurityContext`
(`runtime/models.py`): `trust_score` (default 1.0), `risk_score` (default 0.0),
`confidence`, `active_policies`, `alerts`, `violations`, `blocked`. Mutation is
clamped to [0,1] and idempotent (`add_alert`/`add_violation` deduplicate). The
pipeline closes the loop: BLOCK decision → `SecurityContext.block()` →
downstream `risk.RiskAssessment` → `PolicyDecision` → `response` action.

Threats that surface are captured as `ThreatContext` (type, severity, confidence,
indicators, evidence) — the hand-off object for incident response and the dashboard.

---

## 7. Threat Categories Covered

`PromptCategory` values map 1:1 to the framework's canonical threat taxonomy
(`runtime/enums.py` `ThreatType` mirrors the same names):

```
prompt_injection, jailbreak, role_manipulation, system_prompt_leak,
data_exfiltration, excessive_encoding, suspicious_formatting,
oversized_prompt, malformed_input, unknown
```

---

## 8. Known Gaps & Roadmap

- **Per-endpoint rate limiting**: `RateLimitSettings` / `middleware/rate_limit.py`
  exist but the middleware is disabled by default (`RATE_LIMIT_ENABLED=false`);
  only the auth login/register routes have enforced throttling (5 per 15 min).
- **ML/Quantum in decision path**: engines exist (`ml/*`, `quantum/*`) but the
  security decision cascade is rule-only by default (`PromptSecurityConfig.ml_enabled`
  and `.quantum_enabled` default `False`).
- **HTTP endpoints for scan results**: router scaffolding for prompt-injection /
  jailbreak / threats endpoints exists in `api/v1/router.py` but is **not registered**.
- **Secret rotation**: no built-in rotation; rely on environment configuration.
- **Correlation depth**: HTTP `X-Correlation-ID` propagates into observability traces
  (`Trace.correlation_id`) but not yet into every module's storage record.
