# API Endpoint Testing & Contract Reference

Verified against the running application on commit-time code (v1.1.x).
Every behavior listed below is asserted by `tests/integration/test_api_contract.py`.

Base URL (local): `http://localhost:8000` · Prefix: `/api/v1`

---

## POST /api/v1/analysis/scan

Run a prompt through the full detection pipeline.

### Request

```json
{ "prompt": "text to analyze" }
```

| Field | Type | Constraints |
|---|---|---|
| `prompt` | string | required, minLength=1, maxLength=100000 |

### Response 200

Standard envelope (`ResponseSchema[AnalysisItemSchema]`):

```json
{
  "success": true,
  "message": "Analysis completed with decision allow",
  "data": {
    "analysis_id": "uuid",
    "decision": "allow | warn | review | block",
    "risk_score": 0.0,
    "is_valid": true,
    "finding_count": 0,
    "high_severity_count": 0,
    "processing_time_ms": 6.8,
    "timestamp": "...",
    "payload": { "...full analysis..." }
  }
}
```

Notes:
- Decision values are lowercase enum values.
- Benign prompts return `ALLOW`; injection/jailbreak patterns return
  `WARN`/`REVIEW`/`BLOCK` per the severity cascade.

### Errors

| Input | Status |
|---|---|
| Missing/null/wrong-type prompt | 422 |
| Empty prompt | 422 |
| Prompt > 100,000 chars | 422 |
| Malformed JSON body | 422 |
| Unknown extra fields | ignored (200) |

Validation errors never include stack traces or file paths.

---

## GET /api/v1/analysis/{analysis_id}

Retrieve a stored analysis by ID.

- 200: same item schema as scan.
- 404: unknown ID (`{"detail": "Analysis not found"}`), no internals leaked.

## GET /api/v1/analysis?limit={n}

Recent analyses, most recent first (bounded in-memory history).

- Default limit 20; valid range 1–200.
- Out-of-range limits (0, negative, >200) → 422.

---

## Console endpoints (read-only)

All return the standard success envelope and require no parameters:

| Route | Data shape |
|---|---|
| `/api/v1/console/rules` | list of rule dicts (`rule_id`, `name`, `severity`, ...) |
| `/api/v1/console/models` | model registry + quantum backend status (truthful when untrained) |
| `/api/v1/console/components` | pipeline stage inventory with live status |
| `/api/v1/console/configuration` | sanitized configuration view |
| `/api/v1/console/summary` | overview counters |
| `/api/v1/console/research` | research artifact snapshot |

Security property (tested): the sanitized configuration view must not
contain secrets or absolute filesystem paths.

---

## GET /api/v1/health (and `/health/`)

Liveness/readiness probe.

```json
{
  "status": "healthy | degraded",
  "application": "Q-Guardian",
  "version": "1.1.0",
  "environment": "...",
  "timestamp": "...",
  "database": { "status": "...", "database": "mongodb", "message": "..." }
}
```

`degraded` is reported when MongoDB is unreachable — failures are surfaced,
never hidden.

## GET /api/v1/system/version

Version + environment info; version matches package metadata (tested).

## GET /api/v1/system/status

Truthful operational status derived from live dependency health;
always agrees with `/health`.

---

## Cross-cutting contract

- Every response carries an `X-Correlation-ID` header.
- Security headers present (e.g., `X-Content-Type-Options`).
- OpenAPI schema served at `/openapi.json`; all v1 endpoints documented
  (asserted by test); request constraints reflected in the schema.
- Interactive docs at `/docs`, `/redoc`.
