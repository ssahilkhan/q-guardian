# 11 - Deployment Guide

> Target: Q-Gaudrail v1.1.0 — Python ≥3.12, FastAPI/uvicorn, MongoDB (Motor).
> This guide covers local development, containerized deployment, CI/CD,
> packaging, and the operational scripts shipped with the repo.

---

## 1. Deployment Topology

```
                         +----------------------------+
   HTTP clients -------> | q-guardian-api (uvicorn)   |   :8000
                         |   src.q_guardian.main:app  |
                         +----------------------------+
                              | MONGODB_URL=mongodb://mongo:27017
                              v
                         +----------------------------+
                         | q-guardian-mongo (mongo:7) |   :27017
                         |   volume: mongo-data:/data/db
                         +----------------------------+

   Per-process local state (JSON, optional):
     risk_storage/            (RiskStorage)
     observability_storage/   (ObservabilityStorage)
     response_storage/        (ResponseStorage)
     models/ml/               (ML joblib artifacts)
     quantum model files      (model_metadata.json / model_state.json)
     logs/                    (structured logs)
```

The API is a single ASGI process (uvicorn). MongoDB is a single node in
development; for production, point `MONGODB_URL` at your managed replica set and
put the API behind a TLS-terminating reverse proxy (nginx/Caddy) or an ingress.

---

## 2. Configuration Surface

All runtime configuration is environment-driven (`.env` or shell env). See
`src\q_guardian\config\settings.py` and `docs/04_Configuration_File_Documentation.md`
for the full reference. Critical knobs for deployment:

| Variable | Default | Production advice |
|----------|---------|-------------------|
| `ENVIRONMENT` | `development` | set `production` |
| `DEBUG` | `true` | set `false` |
| `HOST` | `0.0.0.0` | keep for containers; use 127.0.0.1 behind a proxy |
| `PORT` | `8000` | — |
| `LOG_LEVEL` | `INFO` | `WARNING` or `INFO` |
| `LOG_DIR` | `logs` | persist to a volume |
| `MONGODB_URL` | `mongodb://localhost:27017` | use your replica-set URI |
| `MONGODB_DATABASE` | `q_guardian` | — |
| `SECRET_KEY` | placeholder | **must change**; validated at boot in production |
| `CORS_ORIGINS` | localhost:3000/8080 | whitelist real origins |

**Boot safety**: `SecuritySettings.validate_secret_key` refuses to start with the
default placeholder when `ENVIRONMENT=production`
(`ValueError("SECRET_KEY must be changed in production!")`). Rotate it with e.g.
`python -c "import secrets; print(secrets.token_urlsafe(64))"`.

---

## 3. Local Development

Requires Python 3.12+.

```powershell
# from repo root D:\Projects\Quantum\Q_Gaudrail
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"          # editable + dev extras (ruff, mypy, pytest, pre-commit)
Copy-Item .env.example .env      # then edit values
make dev                         # (POSIX) also runs pre-commit install

# run the API with reload
uvicorn src.q_guardian.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000
```

Verify:

```
GET http://localhost:8000/api/v1/health      -> HealthResponseSchema (status healthy/degraded)
GET http://localhost:8000/api/v1/system/version
GET http://localhost:8000/api/v1/system/status
```

The Makefile exposes equivalent targets: `install`, `dev`, `run`, `test`,
`test-cov`, `lint`, `format`, `typecheck`, `benchmark`, `loadtest-quick`,
`profile-snapshot`, `build`, `package-validate`, `docker-up`, `docker-down`,
`docker-build`, `clean`.

---

## 4. Containerized Deployment (Docker Compose)

### 4.1 Image — `docker\Dockerfile`

- Base: `python:3.12-slim`; `gcc` installed for native wheels.
- Build: installs `requirements.txt`, copies `src/` and `pyproject.toml`.
- Runs as non-root user `appuser`.
- Healthcheck every 30s (timeout 10s, start 5s, 3 retries):
  `httpx.get('http://localhost:8000/api/v1/health').raise_for_status()`.
- `EXPOSE 8000`; `CMD ["uvicorn", "src.q_guardian.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

> Note: the image builds from `requirements.txt` pins, not the `[project.dependencies]`
> extras. `orjson==3.10.13` is pinned in `requirements.txt` but commented out —
> it is therefore **not** installed from that file (see
> `docs/04_Configuration_File_Documentation.md` for the quirk).

### 4.2 Compose stack — `docker-compose.yml`

| Service | Image / Build | Ports | Depends on |
|---------|---------------|-------|------------|
| `api` | `docker/Dockerfile` (context `..`) | `8000:8000` | `mongo` (condition: service_healthy) |
| `mongo` | `mongo:7` | `27017:27017` | — |

- API env wired by compose: `ENVIRONMENT=development`, `DEBUG=true`,
  `MONGODB_URL=mongodb://mongo:27017`, `MONGODB_DATABASE=q_guardian`,
  `LOG_LEVEL=INFO`.
- Volumes: `../src:/app/src` (live code), `../logs:/app/logs`, `mongo-data:/data/db`.
- Mongo healthcheck: `mongosh --eval "db.adminCommand('ping')"`.

Commands:

```powershell
docker-compose build
docker-compose up -d
docker-compose down
```

(Or `make docker-build` / `make docker-up` / `make docker-down`.)

### 4.3 Web Console UI

The API process also serves the Q-Guardian **Web Console** — a dependency-free
single-page app shipped as package data (`src/q_guardian/ui/static/`, mounted at
`/ui` by the FastAPI app factory):

- No build step, no Node toolchain, no extra service. The console is served by
  the same `uvicorn src.q_guardian.main:app` process as the API, in both the
  Docker image and local dev.
- Open `http://<host>:8000/ui/` for the console. It drives the existing v1 API
  only (`/api/v1/analysis/scan`, `/api/v1/console/*`, …). Interactive docs stay
  at `/docs` / `/redoc`.
- The console is **read-only** except for submitting prompts to the scan
  pipeline; secrets, internal paths and raw logs are never returned by the
  console endpoints (see `docs/21_Web_Console_UI.md`).
- Deployment hardening: the console currently inherits the application's
  unauthenticated API surface. Behind a public reverse proxy, protect `/ui` and
  `/api` with your existing authentication/rate-limiting layer until the app's
  built-in auth lands.

---

## 5. CI / CD Pipelines — `.github\workflows\`

| Workflow | Triggers | Jobs |
|----------|----------|------|
| `ci.yml` | push/PR to `main` | `lint` (ruff check + format check), `typecheck` (mypy), `test` (pytest + coverage XML, matrix 3.12/3.13, uploads `coverage.xml` artifact), `package` (needs lint+test; `python -m build` + `python -m scripts.packaging.validate`, uploads `dist/`). |
| `benchmark.yml` | push to `main`, manual | `benchmark` — `python -m scripts.benchmarks.run_benchmarks --iterations 10 --output-format json --output benchmark-results.json`, uploads results artifact. |
| `release.yml` | tags `v*` | `release` — builds + validates and creates the GitHub release with `dist/*` (`softprops/action-gh-release`); `publish` (needs `release`, environment `release`) publishes the `dist/` artifact to PyPI via `pypa/gh-action-pypi-publish` (trusted publishing, `id-token: write`). |

All jobs run on `ubuntu-latest` with Python 3.12 (`setup-python@v5`, pip cache).

---

## 6. Packaging & Release Process

```powershell
python -m build                          # build wheel + sdist into dist/
python -m scripts.packaging.validate     # verify metadata, version match, exports
```

`scripts\packaging\validate.py` checks:

1. Required `[project]` fields: `name`, `version`, `description`, `license`,
   `requires-python`.
2. Version consistency between `pyproject.toml` and `src/q_guardian/__init__.py`
   (`__version__`).
3. `LICENSE` and `README.md` exist and are non-empty.
4. Every `__all__` entry in `src/q_guardian/__init__.py` has a corresponding import.

Release flow (mirrors `release.yml`): tag `vX.Y.Z` → CI builds/validates →
GitHub Release with `dist/*` → publish to PyPI (trusted publishing; requires a
PyPI trusted publisher registered for `ssahilkhan/q-guardian`, workflow
`release.yml`, environment `release`).

---

## 7. Operational Scripts

| Tool | Module | Purpose |
|------|--------|---------|
| Prompt CLI | `scripts/prompt_cli.py` | interactive prompt scanning against the security pipeline |
| Dataset tooling | `scripts/train_data.py`, `scripts/build_dataset.py` | build labeled datasets for ML training |
| Benchmarks | `scripts/benchmarks/` (`benchmarks.py`, `benchmark_runner.py`, `run_benchmarks.py`) | smoke/iteration benchmarks of pipeline stages (uses `MetricsEngine` and `TraceEngine`); `--iterations`, `--output-format json`, `--output` |
| Load tests | `scripts/loadtest/` (`load_tester.py`, `reporter.py`, `scenarios.py`, `run_loadtest.py`) | session lifecycle / prompt scan / mixed / burst scenarios; JSON results under `scripts/loadtest/results/` (e.g. `prompt_scan_20260719_035029.json`) |
| Profiling | `scripts/profile/` (`memory_profiler.py`, `optimization_report.py`, `run_profiler.py`) | memory snapshots and optimization reports (`run_profiler snapshot`) |
| Packaging | `scripts/packaging/` (`build.py`, `validate.py`) | build and validate release artifacts |

Run via `python -m scripts.<tool>.<entry>` (see the `Makefile` targets `benchmark`,
`loadtest-quick`, `profile-snapshot`, `package-validate`).

---

## 8. Production Runbook

### 8.1 Health & Readiness

- `GET /api/v1/health` reports `status=healthy` when the app is up and the
  MongoDB ping succeeds; degraded/unhealthy otherwise (see
  `src\q_guardian\database\health.py` and `src\q_guardian\api\v1\endpoints\health.py`).
- Container HEALTHCHECK polls this endpoint; use it for orchestrator readiness.

### 8.2 Storage Directories to Persist

Beyond MongoDB data, module storage defaults to working-dir subdirectories. Mount
a persistent volume for: `risk_storage/`, `observability_storage/`,
`response_storage/`, `models/ml/`, and any quantum model artifacts — otherwise they
are lost on container recreation.

### 8.3 Logging

Structured JSON logs via structlog (see `src\q_guardian\logging\config.py`); the
app logs to `LOG_DIR` (default `logs/`) with rotation (10 MB × 30 backups, from
`LoggingSettings`). Every request carries a correlation ID
(`X-Correlation-ID` header), echoed into observability traces.

### 8.4 Scaling & Limits

- The API is stateless except for module-local JSON stores; scale horizontally once
  those stores are moved to shared volume/Mongo collections.
- Current limits are defaults in `PromptSecurityConfig` (max prompt 100k chars,
  10k lines) — tune per tenant.
- `TrustedHostMiddleware` is registered in development only
  (see `src\q_guardian\api\app.py`).

### 8.5 Upgrades

- No DB migration framework exists yet — Mongo collections are currently undefined
  (`docs/09_Database_Schema_Documentation.md` §8), so upgrades are safe today.
- Re-run `scripts.packaging.validate` before tagging; CI blocks non-consistent
  versions (`release.yml` runs it).

---

## 9. Deployment Checklist

- [ ] `SECRET_KEY` rotated; `ENVIRONMENT=production`, `DEBUG=false`
- [ ] `CORS_ORIGINS` whitelist set
- [ ] `MONGODB_URL` points at HA Mongo; pools sized via `MONGODB_MIN/MAX_POOL_SIZE`
- [ ] Persistent volumes for `logs/`, `*_storage/`, `models/`
- [ ] TLS termination + `X-Correlation-ID` passthrough at the proxy
- [ ] Health endpoint reachable by orchestrator; container HEALTHCHECK passes
- [ ] `python -m scripts.packaging.validate` green; `dist/` artifacts reviewed
- [ ] Benchmarks + load tests recorded as baseline (artifacts in CI)
