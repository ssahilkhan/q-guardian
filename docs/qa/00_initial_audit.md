# Q-Guardian — Phase 0 Initial Audit (Person 4: QA / Security / Release Engineering)

- **Date:** 2026-08-21
- **Repository:** `q-guardian` @ `D:\projects\q-guardian`
- **Branch:** `main` (`705f034` — "feat(experiments): add training diversity experiments, calibration, ablation studies, and pipeline fixes")
- **Working tree:** clean at audit start
- **Version:** `1.1.0` (pyproject.toml, core constants, CHANGELOG all agree; `.env.example` disagrees — see findings)
- **Auditor:** Person 4 — QA / Security / CI/CD / Packaging / Deployment / Monitoring / Release

---

## 1. Architecture Discovered (verified by inspection)

Clean Architecture with 10 modules under `src/q_guardian/`:

| Layer | Location | Notes |
|---|---|---|
| Entry points | `main.py` (`app = create_app()`), `cli.py` (`q-guardian` console script) | ASGI app + research CLI |
| API | `api/app.py`, `api/v1/endpoints/{health,system,analysis,console}.py` | FastAPI factory, `/docs`, `/openapi.json` |
| Prompt Security | `security/` (pipeline, rule engine via `RuleEngine`, decision engine) | normalize → validate → features → rules → decision |
| Classical ML | `ml/models/{anomaly,classifier,ensemble}.py`, `ml/inference/engine.py`, `ml/storage.py` | IsolationForest, RF, XGBoost, Ensemble; joblib persistence |
| Quantum / Fusion | `quantum/` (backends, feature maps, kernels, QSVM), `quantum/fusion/` | Hybrid fusion engine, 5 strategies (2 interface-only) |
| Risk & Policy | `risk/`, `policy/` | scoring, explainability, policy-as-code, RBAC |
| Response & Recovery | `response/` | playbooks, quarantine, evidence, SOAR integrations |
| Observability | `observability/` | metrics, tracing, analytics, alerts, health, exporters |
| Config | `config/settings.py` (pydantic-settings), `.env.example` | env-aware |
| Database | `database/client.py` (motor/pymongo async) | degrades gracefully if Mongo unavailable at startup |

### API surface (verified from router + endpoint files)

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | App info |
| GET | `/api/v1/health`, `/api/v1/health/` | Liveness/readiness incl. DB health → `healthy`/`degraded` |
| GET | `/api/v1/system/version` | Version + environment info |
| GET | `/api/v1/system/status` | Operational status from live dependency health |
| POST | `/api/v1/analysis/scan` | Full detection pipeline scan of a prompt |
| GET | `/api/v1/console/rules` `/models` `/components` (+ config/overview per console service) | Read-only console inventory |
| GET | `/ui/` | Dependency-free web console (static assets) |

### ML runtime reality (important)

- **No trained model artifacts are shipped.** `ModelStorage` defaults to `models/ml`; no such directory exists in the repo. The API pipeline runs **rules-only** unless models are trained/loaded locally.
- Model code (RF/XGBoost/IsolationForest/Ensemble) is fully implemented and unit-tested.
- Training datasets exist under `experiments/training_diversity/` (`jailbreakv.jsonl` ~6 MB, `trustair_jailbreaks.jsonl` ~3.8 MB, `trustair_regular.jsonl` ~4.2 MB, `harmful_behaviors_{train,test}.jsonl`) plus curated train sets (`arm_a`–`arm_d`, `control`) — usable as **external evaluation data** for QA without retraining production models.

---

## 2. Testing Infrastructure Status

- **134 test files** across `tests/unit` (~110), `tests/response` (9), `tests/observability` (24), `tests/integration` (3).
- README claims **2,755 tests passing** — must be re-verified in Phase 1 (badge is a claim, not evidence).
- pytest config: `testpaths=tests`, `asyncio_mode=auto`, markers `unit/integration/slow`.
- Root `conftest.py`: Windows event-loop policy fix, autouse test-env fixture (testing env, mongo URL), session `app` fixture via httpx ASGITransport.
- Fixtures dir exists but contains only conftest/init — no shared security/QA datasets yet.

### Gaps identified

1. **No dedicated security test suite** (`tests/security/` does not exist). Injection/jailbreak/obfuscation robustness and false-positive rates are not systematically tested.
2. **No edge-case suite** for empty/unicode/oversized/malformed inputs at the API boundary.
3. No security regression dataset committed for release gating (data files exist but are not wired into tests).

---

## 3. CI/CD Status

`.github/workflows/ci.yml` (push/PR → main):

| Job | Content | Assessment |
|---|---|---|
| lint | `ruff check src/ tests/` + `ruff format --check` | Present |
| typecheck | `mypy src/q_guardian/` (strict) | Present |
| test | matrix py3.12/3.13, pytest + coverage XML artifact | Present; **no coverage threshold enforced** |
| package | `python -m build` + `scripts.packaging.validate` | Present |

Additional workflows: `release.yml` (tag-triggered build → GitHub Release → PyPI trusted publishing), `benchmark.yml`.

### Gaps identified

1. **No dependency vulnerability scanning** (e.g., pip-audit).
2. **No secret scanning** (e.g., gitleaks/trufflehog) despite repo containing large external datasets and auth scaffolding.
3. **No explicit security-test stage** (depends on gap above in testing).
4. **Coverage has no gate** — coverage is uploaded but never enforced.
5. **Docker image is never built in CI** — deployment artifact unvalidated.
6. Test matrix claims py3.13 support while classifiers list 3.12/3.13 — fine; local verification will cover 3.12 only (NOT VERIFIED for 3.13 on this machine).

---

## 4. Packaging Status

- `pyproject.toml`: setuptools backend, src layout, extras (`ml`, `ml-xgboost`, `datasets`, `quantum`, `quantum-pennylane`, `dev`), console script `q-guardian`, package data `ui/static/**`.
- `scripts/packaging/validate.py` runs in CI (build + validation).
- **requirements.txt issues found:**
  - Line `# --- Utilities orjson==3.10.13` — **orjson pin accidentally swallowed into a comment** → orjson not installed from requirements.txt.
  - **Missing core runtime deps** that `pyproject.toml` declares as mandatory for the public API: `numpy`, `scikit-learn`, `joblib`, `orjson`, `python-dateutil`(present). The analysis service imports the ML stack at module import time → a Docker image built from requirements.txt alone is expected to fail at import. To be verified empirically in Phase 7/8 (P1 candidate).

---

## 5. Deployment Status

- `docker/Dockerfile`: python:3.12-slim, non-root user, HEALTHCHECK against `/api/v1/health`, CMD uvicorn `src.q_guardian.main:app`.
  - Concern: installs only `requirements.txt` (see packaging gaps); never `pip install .` — relies on cwd layout.
- `docker-compose.yml`: api + mongo:7 with healthcheck; dev-style source volume mount `../src:/app/src`.
- Docker availability on this machine: **to be checked** in Phase 8; if unavailable → deployment verified via local uvicorn smoke test + documented limitation (no fabricated deployment claims).

---

## 6. Monitoring Status

- Health endpoints exist (`/api/v1/health` includes DB status; `/system/status` truthful degraded reporting).
- structlog configured with log level/dir/format settings.
- Observability module 10 provides metrics/tracing/alerts engines (unit-tested separately).
- Gaps: no verified end-to-end check that prompts/sensitive data are not logged verbatim (redaction audit needed); performance baselines exist as scripts but no recorded results in repo.

---

## 7. Release Status

- Version sources: `pyproject.toml` = `1.1.0`; `core/constants.APP_VERSION` = `1.1.0`; CHANGELOG `[1.1.0] – 2026-08-06`. **Consistent**, except:
  - `.env.example` has `APP_VERSION=0.1.0` (stale example value; P3 doc/config hygiene).
- Release automation: tag-triggered workflow builds, creates GH release, publishes to PyPI via trusted publishing.
- Roadmap marks v1.2.0 "In progress" — current tree is post-1.1.0 development state on main.

---

## 8. Documentation Status

- Extensive docs set (`docs/00…22`, 17 user guides) including deployment guide, security overview, API reference.
- Missing for this assignment: `docs/qa/` (created by this audit), dedicated security-testing methodology/results, API contract test documentation, release-readiness report, smoke-test evidence.

---

## 9. Known Blockers / Issues Register (initial)

| ID | Severity | Area | Finding |
|---|---|---|---|
| F-01 | P1 | Packaging/Docker | requirements.txt missing numpy/scikit-learn/joblib/orjson required by the public API path → Docker image expected broken (verify in Phase 7/8) |
| F-02 | P2 | Packaging | requirements.txt orjson pin commented out by formatting accident |
| F-03 | P1 | Security/QA | No security test suite / regression corpus wired into CI |
| F-04 | P2 | CI | No dependency-vulnerability or secret scanning |
| F-05 | P2 | CI | Coverage measured but not gated |
| F-06 | P3 | Config | `.env.example` APP_VERSION stale (0.1.0 vs 1.1.0) |
| F-07 | P3 | Tooling | Makefile `clean` target uses Unix-only commands (project targets Linux CI; note only) |
| F-08 | P2 | Deployment | Docker image build not validated anywhere in CI |

---

## 10. Recommended Implementation Plan

1. **Phase 1** — Baseline full test run; fix in-scope breakages; add edge-case tests where gaps found.
2. **Phase 2** — Build `tests/security/` (injection/jailbreak/obfuscation/benign) + reusable fixtures + metrics report generator.
3. **Phase 3** — API tests for all v1 endpoints (valid/invalid/malicious/empty) + `docs/api/` contract doc.
4. **Phase 4** — ML QA: exercise RF/IF/XGBoost/ensemble paths with seeded synthetic + external datasets; produce confusion matrix/precision/recall/F1 without touching production thresholds; label experimental artifacts accordingly.
5. **Phase 5** — Integration/E2E: benign/review/block flows through real app via ASGI transport; DB via mongomock/temp store.
6. **Phase 6** — Extend CI: security-tests job, pip-audit + gitleaks, coverage gate, docker build job.
7. **Phase 7** — Clean-env install + `pip install dist/*.whl` smoke; fix requirements.txt issues (F-01/F-02).
8. **Phase 8** — Build Docker image if toolchain available; run smoke test against local server (uvicorn) regardless.
9. **Phase 9** — Monitoring/perf/failure-recovery checks (model-missing fallback, bad config, oversized payloads).
10. **Phase 10–11** — Version/changelog/release checklist/readiness reports + QA/security/deployment docs.
11. **Final** — Full pipeline rerun, git diff review, final report `docs/qa/person4_final_report.md`.

---

## Verification Note

Everything above was determined by direct repository inspection (files read, directories listed, git state queried). Claims marked "expected" require empirical verification in later phases and will be reported as PASS/FAIL/BLOCKED/NOT VERIFIED — never assumed.
