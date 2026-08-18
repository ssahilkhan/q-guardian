# Training Pipeline Audit Report

> **Status:** verified — commit `e4b3718`.
> **Scope:** final validation of the dataset-preparation + training + evaluation
> pipeline (`src/q_guardian/training/` + `src/q_guardian/cli.py`), the
> `dedup.enabled` semantics decision, offline end-to-end runs with the real
> `HybridEvaluator`, reproducibility, and the full quality gates.

---

## 1. What was verified

| Item | Result |
|---|---|
| `configs/training.json` exists and is schema-valid | PASS — loaded via `TrainingPipelineConfig.from_file`; all keys map to real fields (`caps`, `datasets`, `seed`, `validation_ratio`, `max_samples_per_class`, `dedup`, `model`, `eval`, `output_dir`) |
| `q-guardian` console script (`pyproject.toml` `[project.scripts]`) | PASS — editable install refreshed (was stale `0.10.0rc1`); `q-guardian --help` works, version `1.1.0` |
| prepare → train → evaluate wiring | PASS — dedup applied to train pool only; leakage detection + removal applied to validation/test/external before training |
| Full test suite | PASS — **2,753 tests passed** (was 2,751; +2 new) in ~2 minutes |
| Ruff lint (`ruff check src/ tests/`) | PASS — clean |
| Ruff format (`ruff format --check src/ tests/`) | PASS — 480 files formatted |
| mypy (`mypy src/q_guardian/`) | PASS — clean (338 files); the pre-existing `yaml` stub warning is resolved by installing `types-PyYAML` (already in the `dev` extra) |
| Secrets scan | PASS — no API keys / private keys / tokens in `src/`, `tests/`, `configs/` |
| Training-package coverage | 95% overall (87–97% per module; `schema.py`, `config.py` at 100% and skipped) |

## 2. `dedup.enabled` semantics — decision

**Decision (documented, not behavior-changed):** `DedupConfig.enabled` is the
master switch for **within-pool deduplication only**. Train↔eval **leakage
detection runs regardless of `enabled`**.

Rationale: disabling deduplication is a data-policy choice about the training
pool; it must never silently allow training rows to contaminate evaluation
splits. `exact` / `normalized` select which hash families both mechanisms use.

Where it is now documented:
- `src/q_guardian/training/config.py` — `DedupConfig` docstring.
- `src/q_guardian/training/dedup.py` — `detect_leakage` docstring.
- `docs/21_Training_Pipeline_Documentation.md` §4 — explicit bullet.

Locked in by tests:
- `tests/unit/test_training_dedup.py::TestLeakage::test_enabled_false_does_not_disable_leakage`
- `tests/unit/test_training_prepare.py::TestPreparationPipeline::test_leakage_removed_even_when_dedup_disabled`
  (end-to-end: `enabled=False` keeps train duplicates, `deduplicated == 0`,
  yet external-eval leakage is still removed).

## 3. Offline end-to-end run (real `HybridEvaluator`)

Local `jsonl` sources → `DatasetPreparationPipeline.prepare` →
`TrainingPipeline.train` (real `HybridEvaluator.fit`) →
`EvaluationPipeline.evaluate` (loads checkpoint from disk).

Results (seed 42, `n_estimators=30`, unique synthetic texts):

```
pools          train=128  validation=32  test=60  external_eval=40   leaked removed=0
internal test  detection_rate=0.9333  benign_rejection=1.0  F1=0.9655
external       mean detection_rate=0.9  benign_rejection=1.0  mean F1=0.9474
```

All 14 documented artifacts were produced, including
`model/hybrid_evaluator.joblib` + `model/params.json` (checkpoint round-trip).

**Note on duplicated data:** with deliberately duplicated synthetic texts the
validation pool correctly collapses to 0 — the validation split is drawn before
dedup, and rows whose text duplicates a kept training row are reported and
removed as leaked. This is the intended contamination safeguard, not a bug.

## 4. Reproducibility

Two full runs with the same seed:

| Artifact | Identical |
|---|---|
| split `*.jsonl` files | YES |
| `metrics.json` (excluding wall-clock `elapsed_seconds`) | YES |
| `score_texts` probe predictions on a loaded checkpoint | YES |
| `model/hybrid_evaluator.joblib` bytes | NO (benign pickle variance) |

Splits and predictions are fully reproducible. `joblib` bytes are not
byte-identical between runs but this has no effect on outputs (identical
metrics and predictions). Documented caveat, not a defect.

## 5. Other findings

- **`cli.py` fix (already in working tree, now verified):** `_print_counts`
  must use attribute access (`counts.source`), since `DatasetCounts` is a
  dataclass — the committed dict-style access (`counts['source']`) would crash
  `q-guardian dataset prepare`. Verified the fix renders correctly.
- **`.gitignore`:** added `artifacts/` and `runs/` so pipeline run outputs are
  never committed (an untracked `artifacts/training/` run existed).
- **Test counts:** docs/21 §9 claims match reality — 106 training/evaluation
  tests + 2 new = 108; full suite 2,753.

## 6. Caveats

- The offline E2E uses synthetic local `jsonl` sources; real HF downloads were
  not exercised (offline session).
- `elapsed_seconds` in `metrics.json` is naturally non-deterministic.
- `joblib` checkpoints are not byte-identical across runs (see §4).
