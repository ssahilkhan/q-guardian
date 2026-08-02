# 04. Configuration File Documentation — Q-Gaudrail

> **Document index:** this is document 04 of the Q-Gaudrail technical documentation set.
>
> **Coverage:** every configuration, packaging, CI, and deployment file in the repository, plus the config-adjacent scripts/examples artifacts. Source files are covered in `03_Source_File_Documentation.md`.

## 1. `pyproject.toml` — Build System & Project Metadata

Single source of truth for package build and tooling config (142 lines).

| Section | Content |
|---|---|
| `[build-system]` | `setuptools>=75.0` + `wheel`, backend `setuptools.build_meta` |
| `[project]` | `name = "q-guardian"`, `version = "0.10.0rc1"`, description *"Q-Guardian: A Hybrid Quantum-Classical Framework for Runtime Security of Autonomous AI Agents"*, `readme = "README.md"`, `license = MIT`, `requires-python = ">=3.12"`, author "Q-Guardian Research Team", keywords, classifiers (Beta, Python 3.12/3.13, MIT, Security/AI) |
| `dependencies` | fastapi, uvicorn[standard], pydantic, pydantic-settings, python-dotenv, motor, pymongo, structlog, httpx, python-jose[cryptography], passlib[bcrypt], orjson |
| `[project.optional-dependencies]` | `ml` (scikit-learn, numpy), `ml-xgboost` (xgboost), `datasets` (datasets), `quantum` (qiskit, qiskit-machine-learning, qiskit-aer, numpy), `quantum-pennylane` (pennylane, pennylane-lightning), `dev` (pytest, pytest-asyncio, pytest-cov, ruff, mypy, pre-commit, mongomock) |
| `[project.urls]` | Homepage/Documentation/Repository/Issues (GitHub / ReadTheDocs) |
| `[tool.setuptools.packages.find]` | `where = ["src"]` — src layout |
| `[tool.ruff]` | target `py312`, line-length 100, src `["src","tests"]` |
| `[tool.ruff.lint]` | select E, W, F, I, N, UP, B, A, C4, T20, SIM, TCH, RUF; ignore `T201`; isort known-first-party `q_guardian` |
| `[tool.mypy]` | strict, Python 3.12, pydantic.mypy plugin; `tests.*` override relaxes `disallow_untyped_defs` |
| `[tool.pytest.ini_options]` | `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `addopts = "-v --tb=short --strict-markers"`, markers `unit`, `integration`, `slow` |
| `[tool.coverage]` | source `src/q_guardian`, omits `tests/*` and `**/__init__.py`; report excludes `pragma: no cover`, `__repr__`, `__main__`, `NotImplementedError`, `pass` |

> **Note:** `asyncio_mode = "auto"` in pyproject.toml conflicts with the finding that async tests use explicit `@pytest.mark.asyncio` (see `05_Test_File_Documentation.md`); the mode declared here is "auto".

## 2. `requirements.txt` — Pinned Requirements

Pin file used by the Docker image (44 lines):

- **Core:** fastapi==0.115.6, uvicorn[standard]==0.34.0, pydantic==2.10.4, pydantic-settings==2.7.1, python-dotenv==1.0.1, python-multipart==0.0.20
- **Database:** motor==3.7.0, pymongo==4.11.3
- **Security:** python-jose[cryptography]==3.3.0, passlib[bcrypt]==1.7.4, bcrypt==4.2.1
- **Logging:** structlog==24.4.0
- **HTTP:** httpx==0.28.1
- **Utilities:** python-dateutil==2.9.0.post0
- **Testing:** pytest==8.3.4, pytest-asyncio==0.25.0, pytest-cov==6.0.0, httpx==0.28.1, mongomock==4.2.0.post1
- **Code quality:** ruff==0.8.6, mypy==1.14.1, pre-commit==4.0.1
- **Docker:** gunicorn==23.0.0

> **Known quirk:** line 28 reads `# --- Utilities orjson==3.10.13`. The `orjson==3.10.13` pin is commented out by a trailing comment on the section header, so **orjson is not installed from this file**. The `security-review.md` guide documents this formatting error.

## 3. `.env.example` — Environment Variable Template

Documented template for `src/q_guardian/config/settings.py`:

| Group | Variables |
|---|---|
| Application | `APP_NAME=Q-Guardian`, `APP_VERSION=0.1.0`, `ENVIRONMENT=development`, `DEBUG=true`, `HOST=0.0.0.0`, `PORT=8000`, `LOG_LEVEL=INFO`, `LOG_DIR=logs` |
| MongoDB | `MONGODB_URL=mongodb://localhost:27017`, `MONGODB_DATABASE=q_guardian`, `MONGODB_MIN_POOL_SIZE=1`, `MONGODB_MAX_POOL_SIZE=10`, `MONGODB_TIMEOUT_MS=5000` |
| Security | `SECRET_KEY`, `JWT_ALGORITHM=HS256`, `JWT_EXPIRATION_MINUTES=30`, `JWT_REFRESH_EXPIRATION_DAYS=7` |
| API Keys | `API_KEY_HEADER=X-API-Key` |
| CORS | `CORS_ORIGINS=[...]`, `CORS_ALLOW_CREDENTIALS=true`, `CORS_ALLOW_METHODS=["*"]`, `CORS_ALLOW_HEADERS=["*"]` |
| Rate limiting | `RATE_LIMIT_ENABLED=false`, `RATE_LIMIT_REQUESTS=100`, `RATE_LIMIT_WINDOW_SECONDS=60` |
| Future services | commented `QUANTUM_SERVICE_URL`, `AI_ANALYSIS_SERVICE_URL`, `THREAT_INTEL_SERVICE_URL` |

> **Warning:** the example ships a placeholder `SECRET_KEY` and dev CORS defaults; `10_Security_Overview.md` and `security-review.md` flag these as findings for production.

## 4. `docker/Dockerfile` — Container Image

- Base: `python:3.12-slim`.
- Installs `gcc` (system dependency), copies `requirements.txt`, `pip install --no-cache-dir -r requirements.txt`, copies `src/` and `pyproject.toml`.
- Creates non-root user `appuser`; runs as `appuser`.
- `HEALTHCHECK` pings `http://localhost:8000/api/v1/health` via httpx.
- `EXPOSE 8000`; `CMD ["uvicorn", "src.q_guardian.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

## 5. `docker-compose.yml` — Local Orchestration

- `version: "3.9"`.
- **api service:** builds `docker/Dockerfile` from parent context, container `q-guardian-api`, port `8000:8000`, env (`ENVIRONMENT`, `DEBUG`, `MONGODB_URL=mongodb://mongo:27017`, `MONGODB_DATABASE`, `LOG_LEVEL`), bind-mounts `../src` and `../logs`, `depends_on` mongo healthy, restart `unless-stopped`.
- **mongo service:** `mongo:7`, port `27017:27017`, named volume `mongo-data`, healthcheck via `mongosh ping`, restart `unless-stopped`.
- Network: `q-guardian-network` (bridge).

## 6. `.dockerignore` / `.gitignore`

- `.dockerignore` — excludes build-noise from the Docker context (venv, caches, logs, etc.).
- `.gitignore` — ignores `__pycache__/`, `*.pyc`, `.env`, virtualenvs, caches (`.pytest_cache`, `.mypy_cache`, `.ruff_cache`), `htmlcov/`, `coverage.xml`, `dist/`, `build/`, `*.egg-info`, `models/ml/*`, and runtime logs.

## 7. GitHub Actions Workflows

### 7.1 `.github/workflows/ci.yml` — Continuous Integration
- Trigger: push/PR to `main`.
- Jobs: `lint` (ruff check + format check), `typecheck` (mypy), `test` (matrix Python 3.12/3.13, pytest with coverage, uploads `coverage.xml` artifact on 3.12), `package` (build + `scripts.packaging.validate`, uploads `dist/`).

### 7.2 `.github/workflows/release.yml` — Release
- Trigger: push of `v*` tags.
- Build + validate, create GitHub release with `dist/*` via `softprops/action-gh-release`, publish to PyPI via `pypa/gh-action-pypi-publish` (env `release`).

### 7.3 `.github/workflows/benchmark.yml` — Benchmarks
- Trigger: push to `main` + `workflow_dispatch`.
- Runs `scripts.benchmarks.run_benchmarks --iterations 10 --output-format json`, uploads `benchmark-results.json`.

## 8. `Makefile` — Dev Task Runner

Targets:

| Target | Command |
|---|---|
| `help` | print help |
| `install` | `pip install -e .` |
| `dev` | `pip install -e ".[dev]"` + `pre-commit install` |
| `test` | `pytest tests/ -v --tb=short` |
| `test-cov` | `pytest ... --cov=q_guardian --cov-report=html --cov-report=term` |
| `lint` | `ruff check src/ tests/` |
| `format` | `ruff format src/ tests/` |
| `typecheck` | `mypy src/q_guardian/` |
| `run` | `uvicorn src.q_guardian.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000` |
| `docker-up/down/build` | compose lifecycle |
| `build` | `python -m build` |
| `package-validate` | `python -m scripts.packaging.validate` |
| `benchmark` | `python -m scripts.benchmarks.run_benchmarks --iterations 10` |
| `loadtest-quick` | `python -m scripts.loadtest.run_loadtest --profile quick` |
| `profile-snapshot` | `python -m scripts.profile.run_profiler snapshot` |
| `clean` | remove `__pycache__`, `*.pyc`, caches, coverage output |

## 9. Community & Project Docs (Root)

| File | Content |
|---|---|
| `README.md` | Project landing page (badges incl. 1636-tests claim; see note), feature list, install/quick-start, module summary, test commands |
| `CHANGELOG.md` | Release notes across versions (0.5.x → 0.10.x) |
| `SECURITY.md` | Vulnerability reporting policy, response timeline (ack 48h, assessment 1 week), in/out-of-scope |
| `CONTRIBUTING.md` | Contribution guidelines, dev setup, test/code-quality commands |
| `CODE_OF_CONDUCT.md` | Contributor Covenant v2.1 |
| `LICENSE` | MIT License, © 2026 Q-Guardian Research Team (development license) |
| `LICENSE_PENDING.md` | Statement: private research phase; final license chosen before v1.0.0; MIT is the interim development license |

> **Note on README test count:** the README badge claims 1636 tests, while the audit in `05_Test_File_Documentation.md` counts **2,339 test functions**. The audit count is authoritative; the badge is stale.

## 10. `docs/` — Pre-existing User Guides

17 guides already ship in `docs/` (covered in `00_Project_Overview.md` §11 and summarized in `01_Project_Structure.md`). Highlights: `user-guide.md`, `architecture-guide.md`, `configuration-guide.md`, `deployment-guide.md`, `developer-guide.md`, `event-system.md`, `framework-architecture.md`, `migration-guide.md`, `ml-security.md`, `operations-guide.md`, `plugin-development.md`, `plugin-dev-guide.md`, `quantum-analysis-research.md`, `runtime-architecture.md`, `security-review.md`, `troubleshooting-guide.md`, `api-reference.md`.

## 11. `scripts/` Config-Adjacent Files

- `scripts/loadtest/results/*.json` — generated load-test reports (6 files, e.g. `burst_20260719_035126.json`, `prompt_scan_20260719_035029.json`). Timestamps encode run date (2026-07-19).
- `scripts/packaging/build.py` — package build helper (cleans egg-info).
- `scripts/packaging/validate.py` — package validation (used by CI).
- `examples/qg_state/*` — generated example artifacts: `anomaly.pkl`, `rf.pkl`, `scaler.pkl` (pickle model files), `qsvm.json`, `corpus.json`.
- `examples/qg_memory.jsonl` — CLI memory persisted by `scripts/prompt_cli.py`.

## 12. Build Artifacts (`src/q_guardian.egg-info/`)

Generated by editable installs (PEP 517/518). **Build artifacts, not source** — regenerated automatically and cleaned by `scripts/packaging/build.py`. Three files:

- `PKG-INFO` — distribution metadata (name `q-guardian`, version `0.10.0rc1`, description, URLs, classifiers, `Requires-Python >=3.12`, full deps + extras).
- `requires.txt` — legacy pip requirements mirroring `Requires-Dist`.
- `SOURCES.txt` — sdist file manifest.

> These files exist in the working tree but are excluded from the canonical documentation inventory because they are regenerated build metadata.
