# Benchmark Platform Documentation — `src/q_guardian/benchmark/`

> **Status:** implemented (V2.0 roadmap M1a).
> **Scope:** run the framework's *real* hybrid detection pipeline
> (`normalizer → features → rules → IsolationForest → RandomForest → QSVM →
> weighted-voting fusion`) over curated **third-party** datasets, replacing the
> built-in 62-sample corpus with independently sourced, externally comparable
> benchmarks. Reuses `q_guardian.evaluation` as-is — no new runtime
> dependencies, no modifications to existing modules.

---

## 1. Overview

The platform is a small ingestion + orchestration layer in front of the existing
`q_guardian.evaluation` package. Its job is to turn raw public datasets into
`PromptBenchmarkDataset` objects and to run `DetectionBenchmark` over them,
producing a traceable, reproducible report per dataset.

```
DatasetRegistry ──spec──► DatasetDownloader ──split files──► DatasetValidator
      (11 specs)              (HF rows API / local files)        (quality checks)
                                                                      │
                                                                      ▼
BenchmarkReport ◄── DetectionBenchmark.run ◄── PromptBenchmarkDataset ◄── DatasetPreprocessor
 (metadata + validation    (K-fold CV + provider                     (text/label/category
  + metric aggregates)        ablation)                                   mapping)
```

Four pipelines therefore run in order for every dataset:

1. **Registry** — resolve a `dataset_id` to a `DatasetSpec` (column mapping, splits,
   licensing, gating).
2. **Download** — fetch each split into a local cache (Hugging Face datasets-server
   rows API, or local `jsonl`/`csv`/`json` files).
3. **Validate** — structural + semantic checks on the downloaded rows.
4. **Preprocess + run** — map rows onto the evaluation schema, run K-fold
   cross-validation, wrap results in a `BenchmarkReport`.

## 2. Modules

| Module | Public API | Responsibility |
|---|---|---|
| `registry.py` | `DatasetSpec` (frozen dataclass), `DatasetRegistry` (`builtin`, `get`, `all`, `public`, `gated`, `public_ids`) | Catalog of dataset specs keyed by stable `dataset_id` |
| `download.py` | `DatasetDownloader`, `DatasetError` | Fetch HF splits via the datasets-server rows API; pass-through for local files; gating checks; pagination |
| `validate.py` | `DatasetValidator`, `DatasetValidation` | Row schema, non-empty text, resolvable 0/1 label and category checks; aggregate `valid` flag |
| `preprocessing.py` | `DatasetPreprocessor`, `extract_text`, `resolve_label`, `extract_category` | Map raw rows to `PromptBenchmarkDataset`; skip bad rows; label resolution precedence |
| `run.py` | `BenchmarkRunner.run`, `BenchmarkRunner.run_all` | Orchestrate download → validate → preprocess → `DetectionBenchmark.run` |
| `report.py` | `BenchmarkReport` | Dataset metadata + validation outcome + raw benchmark report; `as_dict`, `provider_metrics`, `ranking` |
| `metrics.py` | `BenchmarkMetrics` | Read-only metric facade: `provider(id)`, `fusion()`, `ranking`, static `compute` |
| `__init__.py` | re-exports the above | Public package surface |

### 2.1 `DatasetSpec` — the ingestion contract

A spec encodes *everything* needed to ingest one dataset. Labels are resolved in
precedence order:

1. `label_field`, optionally through `label_map` (explicit label column),
2. `label_from_split` (split implies the label — e.g. JBB `harmful`/`benign`),
3. `default_label` (benign corpora with no label column).

Text is extracted from the first non-empty of `text_fields`; category from
`category_field` (or `default_category`). `max_samples` caps rows per split;
`requires_token` marks HF-gated sources.

### 2.2 `DatasetDownloader`

- Cache directory: `$QGUARDIAN_BENCHMARK_CACHE` if set, else `~/.qguardian/benchmark`
  (both gitignored).
- HF datasets are fetched with **`httpx`** (already a core dependency — no new deps)
  from `datasets-server.huggingface.co/rows` with 100-row pagination driven by the
  server's `num_rows_total`.
- Gated datasets without a token raise `DatasetError` whose message contains
  `gated`; an explicit `token` argument or the `HF_TOKEN` environment variable
  adds an `Authorization` header.
- Local `jsonl`/`csv`/`json` sources are returned in place (useful for CI and
  unit-test fixtures).
- All files are read with `encoding="utf-8"` (Windows-safe).

### 2.3 `BenchmarkRunner`

`run(dataset_id, *, k=5, seed=42, threshold=0.5, ablate=False, progress=None)`
chains all four stages and returns a `BenchmarkReport`. `run_all()` defaults to
`registry.public_ids()` (token-less datasets only). Every component is injectable,
so tests substitute a local dataset and a small `DetectionBenchmark` config
(e.g. `{"quantum": False, "n_estimators": 20}`).

## 3. Dataset catalog

### 3.1 Public (token-less) — benchmarked in M1a

| `dataset_id` | Source | Config | Splits | Text field | Label | Category | License | Rows (live) |
|---|---|---|---|---|---|---|---|---|
| `deepset-prompt-injections` | `deepset/prompt-injections` | `default` | `train`, `test` | `text` | `label` (0/1) | — (default) | Apache-2.0 | 662 (546 train + 116 test); 263 threat / 399 benign |
| `jbb-behaviors` | `JailbreakBench/JBB-Behaviors` | `behaviors` | `harmful`, `benign` | `Goal` | from split | `Category` (10) | public | 200 (100 + 100); 100 / 100 |
| `dolly-benign` | `databricks/databricks-dolly-15k` | `default` | `train` | `instruction` | default 0 | `category` | CC BY-SA 3.0 | capped at 2000 |

All three verified against the live Hugging Face datasets-server API during M1a
(valid = schema + non-empty text + resolvable labels, zero issues).

### 3.2 Gated (token required) — registered for M1b

These mission datasets return HTTP 401 without a token. They are registered with
`requires_token=True` so the catalog documents the full Phase 1 set, and downloads
fail loudly until authenticated wiring (M1b):

| `dataset_id` | Source | License |
|---|---|---|
| `jailbreakbench-attacks` | `JailbreakBench/JBB-Attacks` | public |
| `wildjailbreak` | `allenai/wildjailbreak` | MIT |
| `harmbench-behaviors` | `cais/harmbench_behaviors` | research-only |
| `advbench` | `DeepMind/AdvBench` | research-only |
| `hex-phi` | `walledai/HEx-PHI` | research-only |
| `pal` | `ProtectAI/PAL` | research-only |
| `agentdojo` | `ibm/agentdojo` | CC BY 4.0 |
| `cyberseceval-prompt-injections` | `facebook/CyberSecEval-PromptInjections` | research-only |

Their exact column mappings are finalized in M1b once authenticated access is
available.

## 4. Usage

```python
from q_guardian.benchmark import BenchmarkRunner

runner = BenchmarkRunner()

# One public dataset end-to-end (downloads to ~/.qguardian/benchmark by default).
report = runner.run("deepset-prompt-injections", k=3, ablate=False)

report.as_dict()["dataset"]           # id / name / license / homepage
report.as_dict()["validation"]        # total, valid_rows, labels, categories, issues
report.metrics.fusion()               # fused aggregate metric block
report.metrics.provider("random_forest")
report.ranking()                      # provider ROC-AUC ranking, best first
report.metrics.compute([0, 1], [0.2, 0.9], threshold=0.5)   # arbitrary-score metrics

# Every public dataset:
all_reports = runner.run_all(k=3)

# Controlled reproduction / CI:
import os
os.environ["QGUARDIAN_BENCHMARK_CACHE"] = "C:\\path\\to\\cache"
```

Gated datasets: `runner.run("wildjailbreak")` raises `DatasetError` mentioning
`gated` until a token is supplied (`DatasetDownloader(token=...)` or `HF_TOKEN`).

## 5. Quality gates

- **Ruff** — `python -m ruff check src/q_guardian/benchmark tests/unit/test_benchmark_*.py`
  → clean (line-length 100; select E,W,F,I,N,UP,B,A,C4,T20,SIM,TCH,RUF).
- **mypy strict** — `python -m mypy src/q_guardian/benchmark` → clean
  (python_version 3.12, pydantic plugin).
- **Tests** — 35 unit tests in `tests/unit/test_benchmark_{registry,download,validate,preprocessing,runner}.py`
  (all synchronous, `httpx.MockTransport` for download, local fixture datasets).
- **Regression** — `tests/unit/test_evaluation_*.py` (42 tests) still pass; no
  existing module was modified.

### Reproducing the live numbers

Live artifacts are gitignored (`docs/output/`), so the platform documents *how to
reproduce* rather than committing reports:

```bash
set QGUARDIAN_BENCHMARK_CACHE=C:\path\to\cache
python -c "from q_guardian.benchmark import BenchmarkRunner; r = BenchmarkRunner(); print(r.run('jbb-behaviors', k=3, seed=42).as_dict())"
```

## 6. Honest-measurement notes

- **JBB-Behaviors scores near chance (~0.51) under the current engine.** JBB
  behaviors are *harmful goal statements*, not prompt-injection prompts; the
  rule/feature engine sees little separating signal. This is a legitimate, valuable
  benchmark result — it quantifies what the current pipeline can and cannot detect —
  rather than a bug. It is precisely the kind of externally comparable measurement
  this platform is built to surface.
- Provider metric keys follow the exact `DetectionBenchmark` report shape
  (`cross_validation.metrics.*`, `cross_validation.roc_auc_ranking`); if that
  internal shape ever changes, `BenchmarkReport.provider_metrics()` / `ranking()`
  are the single place to adapt.
- The built-in 62-sample corpus (`data/benchmark_prompts.jsonl`) remains the
  in-repo sanity check; the platform extends it with third-party datasets rather
  than replacing it (dataset merge is a later phase).

## 7. Roadmap hooks

- **M1b** — authenticated downloads for the 8 gated datasets (HF token / gated-cli
  path), finalized column mappings, and gated-suite reports.
- **M2** — a `scripts/benchmark_cli.py` (or similar) wrapping `BenchmarkRunner` with
  `--datasets --k --seed --output`, matching `scripts/evaluate_pipeline.py`'s CLI
  conventions; dataset-merge + cross-dataset aggregate reports.
