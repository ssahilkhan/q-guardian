# Web Console UI — Architecture & Implementation Plan

> Q-Guardian Console: a dependency-free web control plane that exposes the
> framework's *existing* detection pipeline, models, rules, and configuration
> through a single-page interface served by the existing FastAPI application.

---

## 1. Repository Understanding

The Q-Guardian core is a **hybrid quantum-classical security framework** for
runtime security of autonomous AI agents. The console UI reuses these existing
capabilities without duplicating any logic:

| Existing capability | Reused by the UI |
|---|---|
| `ThreatAnalysisPlugin` (`q_guardian/ml/plugin.py`) | The unified scan pipeline: Normalize → Validate → Features → Rules → optional ML → Decision. Constructible standalone; degrades to rule-only when no ML models are registered (backward-compatible by design). |
| `PromptNormalizer` / `PromptValidator` / `PromptFeatureExtractor` / `RuleEngine` / `SecurityDecisionEngine` (`q_guardian/security/`) | All pipeline stages run inside the plugin; the UI only reads the resulting `PromptAnalysis` payload. |
| `PromptAnalysis`, `PromptFinding`, `PromptFeatures` (`q_guardian/security/models.py`) | Result rendering: decision, risk score, findings, features, normalized text, timing. |
| `RuleEngine.list_rules()` | Read-only rules catalog page. |
| `ModelManager` / `InferenceEngine` (`q_guardian/ml/`) | Read-only ML model/health status. |
| Quantum backends `local-simulator`, `qiskit-aer`, `qiskit-runtime` (`q_guardian/quantum/backends/`) | Read-only provider availability status. |
| `get_settings()` + `PromptSecurityConfig` / `MLConfig` | Read-only, sanitized configuration page. |
| FastAPI app factory (`q_guardian/api/app.py`), `ResponseSchema`/`PaginatedResponseSchema` (`q_guardian/schemas/base.py`) | API envelope and app mounting for the UI. |

## 2. Architecture Decision

**Technology: vanilla HTML/CSS/JS single-page app served by FastAPI.**

Why:

- The project is Python/FastAPI with no existing frontend. Introducing Node,
  a build toolchain, or a framework like React would violate the project's
  "no large unnecessary technology stack" constraint and complicate the
  Docker/pip deployment story.
- The console is a **presentation/control layer**. Its only job is to call the
  v1 JSON API and render results — no framework is required for that.
- The static assets live inside the Python package
  (`src/q_guardian/ui/static/`) and are mounted by FastAPI at `/ui`, so the
  same `uvicorn src.q_guardian.main:app` invocation that runs the API also
  serves the UI. Docker and local dev both work unchanged.

### Integration layer (smallest clean layer)

The existing API exposed only health/version/status. To make the console a
control layer we add a thin, read-mostly API facade — no detection logic is
reimplemented:

1. **`AnalysisService`** (`q_guardian/api/services/analysis.py`) — a singleton
   facade over `ThreatAnalysisPlugin` (the existing orchestrator) plus a
   bounded in-memory scan history. This is the only new service code.
2. **New v1 endpoints** (registered in `api/v1/router.py`):
   - `POST /api/v1/analysis/scan` — run the existing pipeline on a prompt.
   - `GET /api/v1/analysis` / `GET /api/v1/analysis/{id}` — scan history.
   - `GET /api/v1/console/rules` — enabled detection rules.
   - `GET /api/v1/console/models` — ML + quantum provider status.
   - `GET /api/v1/console/components` — pipeline stage inventory.
   - `GET /api/v1/console/configuration` — sanitized configuration.
   - `GET /api/v1/console/summary` — overview aggregates for the landing page.

## 3. Information Architecture

Single-page application with tab navigation (no router library):

| Page | Purpose | Backing endpoint(s) |
|---|---|---|
| **Overview** | System status, pipeline stage status, model/rule counts, recent scans, quick-scan entry | `/api/v1/system/status`, `/api/v1/system/version`, `/api/v1/console/summary`, `/api/v1/analysis` |
| **Scanner** | Primary workflow: submit prompt → run pipeline → inspect decision, findings, features, normalized text, timing | `POST /api/v1/analysis/scan` |
| **History** | Browsable table of past scans, drill into any result | `GET /api/v1/analysis`, `GET /api/v1/analysis/{id}` |
| **Rules** | Read-only catalog of active detection rules | `GET /api/v1/console/rules` |
| **Models** | Read-only ML model registry + quantum backend availability | `GET /api/v1/console/models` |
| **Configuration** | Read-only, sanitized application + security configuration | `GET /api/v1/console/configuration` |
| **About** | Architecture explanation, links to `/docs`, repository | — (static) |

### Primary user workflow

1. Open Q-Guardian Console → **Overview** shows system status and capability
   summary (component readiness, rule count, model count).
2. Enter a prompt in the quick scan box (or go to **Scanner**) and submit.
3. The console POSTs to the existing pipeline and renders:
   - the decision banner (ALLOW / WARN / REVIEW / BLOCK),
   - risk score, processing time, validation status,
   - each finding: category, severity, description, matched text, confidence,
   - the extracted feature grid and the normalized prompt.
4. **History** retains every scan for inspection; each row links back to the
   full result.
5. **Rules / Models / Configuration** pages make the system legible without
   exposing internals that must stay private.

## 4. Data Mapping

| UI feature | Source | Function | Transformation | New adapter/endpoint? |
|---|---|---|---|---|
| Scan a prompt | Detection pipeline | `ThreatAnalysisPlugin.scan_prompt()` | none (returns `PromptAnalysis.model_dump()`) | `POST /api/v1/analysis/scan` |
| Scan history | In-memory (bounded) | `AnalysisService.history()` | none | `GET /api/v1/analysis` |
| Rule catalog | `RuleEngine` | `rule_engine.list_rules()` | none | `GET /api/v1/console/rules` |
| Model status | `ModelManager` | `model_manager.health()` / `list_models()` | dict mapping | `GET /api/v1/console/models` |
| Quantum status | `q_guardian.quantum.backends` | backend class inventory + optional SDK import checks | availability flags | `GET /api/v1/console/models` |
| Config view | `get_settings()`, `PromptSecurityConfig`, `MLConfig` | `model_dump()` | **redaction** of secrets | `GET /api/v1/console/configuration` |
| Overview aggregates | all of the above | service summary() | counts + status | `GET /api/v1/console/summary` |

No duplicate source of truth is created: the console reads live state from the
existing pipeline objects.

## 5. Security Review (what the UI must NOT expose)

- **Secrets**: the configuration endpoint never returns `security.secret_key`,
  `JWT` secrets, API keys, or the password portion of the MongoDB URL. It is
  explicitly redacted at the source.
- **Sensitive paths**: internal filesystem paths (log dirs, model storage
  paths) are surfaced only as present/absent flags where relevant, not as
  full absolute paths on the configuration page.
- **No arbitrary code execution / command execution**: the console exposes no
  shell, no eval, no file operations, no write endpoints except submitting a
  prompt to the existing scan pipeline.
- **Input bounds**: scan requests are length-limited at the API schema layer
  (consistent with `PromptValidator` limits), and the existing validator
  rejects oversized/malformed input before any processing.
- **Raw logs**: not exposed. Only structured analysis results are returned.
- **Read-only surface**: rules, models, configuration, and component pages are
  strictly read-only.
- **Auth**: the new endpoints match the existing application's
  unauthenticated API surface. Deploying the console publicly must go through
  the existing reverse-proxy/network controls; see §9 and the deployment
  guide. Wiring the existing (placeholder) `RateLimitService` / auth into the
  API is tracked as a remaining improvement, not silently omitted.

## 6. Serving Strategy

- `create_app()` mounts `StaticFiles(directory=ui/static, html=True)` at
  `/ui` and a redirect from `/ui` is **not** added — the existing `/` JSON
  root and its tests are preserved.
- Static assets are shipped as package data
  (`[tool.setuptools.package-data] q_guardian = ["ui/static/**"]`) so the
  wheel and the Docker image both include the console.
- The UI calls relative API paths (`/api/v1/...`) so it works behind a
  reverse proxy or prefix.

## 7. Testing Strategy

- New integration tests (`tests/integration/test_console_api.py`) cover:
  scan of a benign prompt, scan of a suspicious prompt, scan of invalid input
  (empty/oversized), history listing and lookup, rules catalog, models
  status, configuration redaction, component inventory, summary, and static
  UI file serving.
- Existing `tests/integration/test_api.py` must continue to pass unchanged.
- `ruff check` / `ruff format --check` / `mypy` (strict) must pass for all new
  modules; `python -m build` + `twine check` must still pass.

## 8. Documentation

This document serves as both the plan and the implementation record. The
following are updated: this page, `docs/04_Configuration_File_Documentation.md`,
`docs/11_Deployment_Guide.md`, and the README (UI section + roadmap note).

## 9. Known Limitations / Remaining Improvements

- Scan history is in-memory and bounded (200 entries); it resets on process
  restart. Persisting analyses via the existing MongoDB repositories is a
  natural follow-up.
- API authentication/rate limiting for the console endpoints is not wired in
  (the app currently has no auth on any endpoint); deployment must rely on
  existing network-level controls until this lands.
- The console reports the framework's built-in model/quantum inventory but
  does not train models or retrain anything.
