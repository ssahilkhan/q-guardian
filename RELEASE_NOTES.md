# Release Notes — Q-Guardian v1.1.0

**Release date:** 2026-08-06
**Version:** 1.1.0 (semantic versioning — minor bump)
**Branch:** main
**Base release:** v1.0.0

## Highlights

- **Benchmark platform** (`q_guardian.benchmark`) — runs the framework's real hybrid detection pipeline over curated third-party datasets: dataset registry (11 specs), Hugging Face / local downloader, dataset validator, preprocessor, K-fold benchmark runner, and `BenchmarkReport` with provider metrics and rankings.
- **Evaluation toolkit** (`q_guardian.evaluation`) — `PromptBenchmarkDataset`, metrics, hybrid evaluator, K-fold benchmark, and reporting, reused as-is by the benchmark platform.
- **Embeddings layer** (`q_guardian.embeddings`) — pluggable providers (local sentence-transformers, cloud, deterministic hasher), LRU-cached embedding manager, hybrid-mode fusion with explainability, and pipeline integration.
- **Packaging validation hardened** — `__all__` export check rewritten on `ast`, eliminating 43 false "no corresponding import" failures.
- **Docs & version sync** — full documentation set synchronized to v1.1.0; new `docs/19_Benchmark_Platform_Documentation.md` and `docs/20_Embedding_Pipeline.md`.

## Quality Gates

All six release gates pass sequentially on a clean run:

| Gate | Command | Result |
|---|---|---|
| Lint | `ruff check src/ tests/` | pass |
| Format | `ruff format --check src/ tests/` | pass (458 files) |
| Typecheck | `mypy src/q_guardian/` | pass (326 files, 0 errors) |
| Tests | `pytest tests/ -q` | 2,650 passed |
| Build | `python -m build` | sdist + wheel |
| Packaging validation | `python -m scripts.packaging.validate` | pass |

## Tests

- **2,650 tests across 123 test files** — green on Python 3.12 (3.12.10) and Python 3.13.
- New suites: 5 `test_benchmark_*`, 4 `test_evaluation_*`, and 10 `test_embeddings_*` unit test files.

## Packaging

- Version bumped to `1.1.0` in `pyproject.toml`, `src/q_guardian/__init__.py`, `src/q_guardian/core/constants.py` (`APP_VERSION`), and `src/q_guardian/config/settings.py` (`AppSettings.version`, surfaced by `/api/v1/system/version`).
- sdist + wheel (`q_guardian-1.1.0-py3-none-any.whl`) build cleanly; package validation passes.
- Mypy overrides extended with `sentence_transformers.*` for the optional local embedding provider.

## CI

- GitHub Actions: `ci.yml` (lint / format / typecheck / test on Python 3.12 + 3.13), `benchmark.yml`, `release.yml` (build + validate + GitHub release on `v*` tags).
- Workflow behavior unchanged; the release gate was verified locally with the same commands CI runs.

## Documentation

- `docs/19_Benchmark_Platform_Documentation.md` and `docs/20_Embedding_Pipeline.md` added.
- Module map and project structure updated for the new `benchmark`, `evaluation`, and `embeddings` packages.
- Version references synchronized to v1.1.0 across the README and the documentation set; test-count references refreshed to 2,650 passing.

## Benchmark Status

- Phase 1 of the V2.0 research program (M1a): the ingestion + orchestration platform is implemented and fully unit-tested.
- `data/benchmark_prompts.jsonl` sample dataset committed; the dataset registry provides 11 curated specs.

## Evaluation Status

- `q_guardian.evaluation` is implemented and unit-tested, and is reused as-is by the benchmark platform (no runtime changes to existing modules).

## Known Caveats

- Benchmark ingestion requires network access to the Hugging Face datasets-server rows API (or locally provided files); gated datasets are skipped without a token.
- The local embedding provider requires the optional `sentence-transformers` package; the deterministic and cloud providers have no third-party dependency.
- Quantum backends beyond the local simulator and live MongoDB/observability integrations remain covered by unit tests only.

## Files Changed

- **Source (`src/q_guardian/`)**: new `benchmark/`, `evaluation/`, and `embeddings/` packages; version updates in `__init__.py`, `core/constants.py`, and `config/settings.py`.
- **Packaging**: `pyproject.toml` (version 1.1.0, mypy overrides); `scripts/packaging/validate.py` (AST-based export check).
- **Tests**: `tests/unit/test_benchmark_*.py` (5 files), `tests/unit/test_evaluation_*.py` (4 files), `tests/unit/test_embeddings_*.py` (10 files).
- **Docs**: `docs/19_Benchmark_Platform_Documentation.md` and `docs/20_Embedding_Pipeline.md` added; version and test-count sync across the README and documentation set; `CHANGELOG.md` entry added.
- **Data**: `data/benchmark_prompts.jsonl`.
- **Tooling**: `scripts/evaluate_pipeline.py`.
- **Config**: `.gitignore` (excludes `docs/Research/` binaries).
