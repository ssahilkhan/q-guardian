# Console Integration Contracts & Backend Dependencies

This document describes the API contracts consumed by the Q-Guardian web console (served at `/ui/`) and identifies backend dependencies that must be satisfied for full functionality.

## 1. Console API Endpoints (Frontend → Backend)

All endpoints below are mounted under `/api/v1` and require authentication (JWT Bearer token or `X-API-Key` header) **except** the auth bootstrap endpoints.

| Method | Path | Auth | Description | Frontend Consumer |
|--------|------|------|-------------|-------------------|
| **Auth Bootstrap** |
| POST | `/auth/login` | ❌ | Username/password → JWT access + refresh token pair | `login.js` |
| POST | `/auth/refresh` | ❌ | Refresh token → new access token (refresh reused) | `auth.js` (silent retry) |
| **System** |
| GET | `/health` | ✅ | Liveness + MongoDB health | `console.js` (status poll) |
| GET | `/system/version` | ✅ | Application version + environment | `console.js` (version badge), `login.js` (credential probe) |
| GET | `/system/status` | ✅ | Operational status (degraded/healthy) | — |
| **Console** |
| GET | `/console/summary` | ✅ | Overview: components, rules, ML, quantum, history counts | `dashboard.js`, `audit.js` |
| GET | `/console/rules` | ✅ | Detection rule catalog | `rules.js` |
| GET | `/console/models` | ✅ | ML model registry + quantum backend status | `models.js`, `quantum.js`, `dashboard.js` |
| GET | `/console/components` | ✅ | Pipeline stage inventory (live status) | `pipeline.js`, `dashboard.js`, `audit.js` |
| GET | `/console/configuration` | ✅ | Sanitized application config (no secrets/paths) | `configuration.js`, `audit.js` |
| GET | `/console/research` | ✅ | On-disk artifact inventory (datasets, models, evaluation, benchmarks, loadtests) | `training.js`, `evaluation.js`, `benchmarks.js` |
| GET | `/console/observability` | ✅ | Live in-process metrics (request counts, latency, scan decisions) | `observability.js` |
| **Analysis (Scan History)** |
| POST | `/analysis/scan` | ✅ | Run detection pipeline on a prompt | `scanner.js`, `dashboard.js` |
| GET | `/analysis?limit=N` | ✅ | Bounded history (most recent N, max 200) | `detection.js` (list), `dashboard.js` (recent) |
| GET | `/analysis/{id}` | ✅ | Full analysis record by ID | `detection.js` (detail) |

## 2. Request/Response Shapes (Key Fields)

### `/auth/login` — Request
```json
{ "username": "string", "password": "string" }
```

### `/auth/login` — Response (200)
```json
{
  "success": true,
  "message": "Login succeeded",
  "data": {
    "username": "string",
    "roles": ["string"],
    "tokens": { "access": "jwt...", "refresh": "jwt..." }
  }
}
```
Error (401): `{ "error": { "code": "AUTHENTICATION_ERROR", "message": "Invalid username or password", "details": { "reason": "invalid_credentials" } } }`

### `/auth/refresh` — Request/Response
```json
// Request
{ "refresh_token": "jwt..." }
// Response 200
{ "success": true, "data": { "username": "...", "roles": [...], "tokens": { "access": "new-jwt...", "refresh": "same-refresh-jwt" } } }
```

### `/console/models` — ML Model Fields (extended)
```json
{
  "ml": {
    "active": true,
    "detector_count": 2,
    "classifier_count": 1,
    "total_models": 3,
    "loaded_models": 2,
    "models": [{
      "name": "isolation-forest-v1",
      "model_type": "anomaly",
      "backend": "sklearn",
      "version": "1.0.0",
      "status": "loaded",
      "description": "Isolation Forest anomaly detector",
      "training_samples": 50000,
      "feature_count": 42,
      "created_at": "2026-01-15T10:30:00+00:00",
      "updated_at": "2026-01-15T10:30:00+00:00",
      "artifact_registered": true,
      "tags": ["anomaly", "production"]
    }]
  },
  "quantum": { ... }
}
```

### `/console/components` — Dynamic ML Status
The `ml` component now reports `status: "active"` when models are loaded, otherwise `"available"` (research layer).

### `/console/observability` — Response
```json
{
  "success": true,
  "data": {
    "generated_at": "2026-08-24T10:00:00Z",
    "window": "current server process",
    "uptime_seconds": 3600.5,
    "total_requests": 1523,
    "error_count": 12,
    "error_rate": 0.0078,
    "routes": [
      { "method": "POST", "route": "/api/v1/analysis/scan", "status_code": 200, "count": 45, "avg_ms": 12.4, "max_ms": 89.2 }
    ],
    "scan_decisions": { "allow": 80, "warn": 12, "review": 5, "block": 3 },
    "note": "Latency is average/max per route template; percentiles are not computed. Counters reset on restart."
  }
}
```

### `/console/research/evaluation` — Report Shape
The evaluation endpoint surfaces the complete `scripts/evaluate_pipeline.py` output:
```json
{
  "present": true,
  "generated_at": "2026-08-24T10:00:00Z",
  "report": {
    "config": { "k": 5, "seed": 42, "threshold": 0.5, "dataset": "builtin", "evaluator": {...} },
    "dataset": { "total": 1000, "threats": 400, "benign": 600, "threat_ratio": 0.4, "categories": {...} },
    "cross_validation": {
      "fold_count": 5,
      "folds": [{ "fold": 1, "train_size": 800, "test_size": 200, "fusion_roc_auc": 0.98, "fusion_f1": 0.92, "fusion_accuracy": 0.95 }, ...],
      "metrics": {
        "fusion": { "accuracy": { "mean": 0.94, "std": 0.02, "min": 0.91, "max": 0.96 }, "f1_score": {...}, "roc_auc": {...}, ... },
        "rule-engine": {...},
        "isolation-forest": {...},
        "random-forest": {...},
        "qsvm": {...}
      },
      "roc_auc_ranking": [{ "provider": "fusion", "mean_roc_auc": 0.98 }, ...]
    },
    "ablation_summary": {
      "rule-engine": { "removed": "rule-engine", "kept": ["isolation-forest", "random-forest", "qsvm"], "fusion_roc_auc": { "mean": 0.97, "std": 0.01 }, "fusion_f1_mean": 0.94 },
      "qsvm": { "removed": "qsvm", "kept": ["rule-engine", "isolation-forest", "random-forest"], ... }
    }
  },
  "scores_csv": true,
  "report_md": true,
  "note": null
}
```

## 3. Frontend State Requirements

### Authentication
- Tokens stored in `sessionStorage` (keys: `qg.access`, `qg.refresh`, `qg.kind`, `qg.user`)
- On 401: one silent refresh attempt → retry original request; on failure → redirect to `#/login?next=...`
- Credentials never logged or rendered; login view accepts username/password **or** pasted JWT/API key

### UI States (Every Data View)
| State | Handling |
|-------|----------|
| Loading | Spinner + "Loading…" message |
| Success | Real data rendered |
| Empty | "No data available" with context |
| Error | User-friendly message, no internals |
| Unauthorized | Redirect to login (preserves `next`) |
| Forbidden | "You do not have permission" |
| Rate Limited | "Rate limit reached — please wait" + Retry-After |
| Backend Unavailable | "Cannot reach the Q-Guardian API… Is the server running?" |

### Observability Freshness
- **LIVE**: fetch succeeded < 30s ago
- **STALE**: fetch succeeded > 30s ago
- **UNAVAILABLE**: fetch failed

## 4. Backend Dependencies (Must Be Provided by Person 2 / Backend Team)

| Feature | Required Backend Contract | Status |
|---------|---------------------------|--------|
| **Persistent Scan History** | `AnalysisHistoryRepository.list_recent()` returns MongoDB-backed records (max 200) | ✅ Implemented (commit 9a34123) |
| **Model Registry Metadata** | `ModelManager.list_models()` returns `ModelMetadata` with `training_samples`, `feature_count`, `created_at`, `artifact_path`, `tags` | ✅ Fields exist; wired in `AnalysisService.models_status()` |
| **Observability Metrics** | In-process registry (`api.metrics.snapshot()`) fed by `ResponseTimingMiddleware` | ✅ Implemented; exposed via `/console/observability` |
| **Evaluation Report** | `scripts/evaluate_pipeline.py` writes `docs/output/evaluation/report.json` | ✅ File exists; read by `research_snapshot()` |
| **Benchmark/Loadtest Artifacts** | `scripts/benchmarks/results_*.json`, `scripts/loadtest/results/*.json` | ✅ Read by `research_snapshot()`; truthful empty state when absent |
| **Quantum Research Data** | Evaluation report includes `qsvm` provider metrics + ablation | ✅ Present in real report |

| Feature | Required Backend Contract | Status |
|---------|---------------------------|--------|
| **Dedicated Audit Trail** | `AuditTrail` records persisted per scan decision (currently in-memory only); API endpoint `GET /console/audit` with pagination/filters | ❌ **NOT YET IMPLEMENTED** — backend `AuditTrail` exists but is not wired to pipeline; frontend documents this gap honestly |
| **External Generalization Datasets** | Evaluation report with per-external-dataset metrics (beyond `builtin`) | ❌ **NOT YET AVAILABLE** — no saved external results on disk; `scripts/training_diversity` experiments exist but no JSON results produced |
| **Full DashboardEndpoints Wiring** | `DashboardAPI` instantiated with `MetricsEngine`, `HealthEngine`, `AnalyticsEngine`, `AlertEngine` and registered as FastAPI routes | ❌ **NOT YET WIRED** — engines only created inside `ObservabilityPlugin` (framework lifecycle, not running in API app); minimal `/console/observability` exposes existing registry instead |
| **True Pagination for History** | `AnalysisHistoryRepository.list_recent(limit, offset)` + endpoint `GET /analysis?limit=N&offset=M` | ❌ **NOT YET IMPLEMENTED** — repository/endpoint only support `limit`; frontend shows "most recent N of up to 200 retained" |

## 5. Files Changed by This Integration

### Backend (New / Modified)
- `src/q_guardian/schemas/auth.py` — **NEW** Login/Refresh request schemas
- `src/q_guardian/api/v1/endpoints/auth.py` — **NEW** `/auth/login`, `/auth/refresh` endpoints
- `src/q_guardian/api/app.py` — Include auth router (unauthenticated) + console router
- `src/q_guardian/api/services/analysis.py` — Extended `models_status()` with real metadata; dynamic `components()` ML status
- `src/q_guardian/api/v1/endpoints/console.py` — Added `/console/observability` endpoint

### Frontend (New / Modified)
- `src/q_guardian/ui/static/js/auth.js` — **NEW** Session layer (storage, headers, 401 handling)
- `src/q_guardian/ui/static/js/api.js` — Credential attachment, 401→refresh→login flow, new endpoints
- `src/q_guardian/ui/static/js/console.js` — Route guard, user badge + logout, fixed breadcrumb links
- `src/q_guardian/ui/static/js/views/login.js` — **NEW** Username/password + credential paste login
- `src/q_guardian/ui/static/js/views/observability.js` — **NEW** Live metrics view (LIVE/STALE/UNAVAILABLE)
- `src/q_guardian/ui/static/js/views/evaluation.js` — Full report rendering (folds, matrix, ranking, ablation)
- `src/q_guardian/ui/static/js/views/models.js` — Extra metadata columns (samples, features, created, artifact, tags)
- `src/q_guardian/ui/static/js/views/detection.js` — Corrected "session history" → persistent history copy
- `src/q_guardian/ui/static/js/views/audit.js` — Honest framing: audit trail pending backend
- `src/q_guardian/ui/static/js/views/documentation.js` — Fixed false memory-history claim; added auth/observability endpoints
- `src/q_guardian/ui/static/index.html` — New script tags, cache-bust `?v=3`
- `src/q_guardian/ui/static/css/console.css` — Minimal additions (session badge, login form, dist bars)

### Tests (New / Modified)
- `tests/integration/test_auth_endpoints.py` — **NEW** Auth endpoint contract tests
- `tests/integration/test_console_api.py` — Extended `TestStaticUi` for new JS assets

## 6. Quantum Status

The console **does not** claim quantum is in the production scan path. The Quantum page explicitly states:
> "Quantum is a research capability in this release. The default scan pipeline runs normalize → validate → features → rules → optional classical ML → decision."

Real QSVM evaluation metrics (from `evaluation.report.json`) are surfaced under **Evaluation** with `provider: "qsvm"` in cross-validation metrics, ROC-AUC ranking, and ablation summary — clearly labeled as research results.

## 7. Recommended Next Backend Work (Priority Order)

1. **Wire AuditTrail to pipeline** — Persist `AuditRecord` per decision; expose `GET /console/audit` with filters/pagination.
2. **Generate external generalization results** — Run `scripts/training_diversity` experiments to produce per-dataset evaluation JSON.
3. **Instantiate DashboardEngines in API app** — Wire `MetricsEngine`/`HealthEngine`/`AnalyticsEngine`/`AlertEngine` for full `/console/observability` parity with `DashboardEndpoints`.
4. **Add offset pagination to history** — Repository + endpoint support for `offset` parameter.