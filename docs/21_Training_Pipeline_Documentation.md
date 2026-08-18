# Training Pipeline Documentation — `src/q_guardian/training/` + `cli.py`

> **Status:** implemented (V2.0 roadmap M1c).
> **Scope:** production-grade, reproducible **dataset preparation + training +
> evaluation** for the prompt-injection detector. Reuses the existing
> `q_guardian.benchmark` registry (`DatasetSpec` / `DatasetRegistry` /
> `DatasetDownloader` / `DatasetValidator`) and the framework's real detector
> (`q_guardian.evaluation.HybridEvaluator`) — no second training framework, no
> redesigned model. Exposed through the `q-guardian` CLI.

---

## 1. Overview

The pipeline turns configured third-party datasets into a trained, checked,
evaluated detector. It runs in three stages:

```
datasets.train ─┐
datasets.validation ─┼─► dataset prepare ──► splits/ ──► model train ──► model/
datasets.test ─┘          (download,          (jsonl)     (HybridEvaluator    (checkpoint
datasets.external_eval ─── normalize,                     fit + metrics)       + params.json)
                           split, dedup,
                           leakage check)                        │
                                                                  ▼
                                               model evaluate ──► evaluation.json/md
                                               (per-dataset security matrix)
```

Stage 1 reuses the benchmark platform's ingestion (`docs/19_Benchmark_Platform_Documentation.md`).
Stages 2–3 fit and score the framework's existing `HybridEvaluator`
(`normalizer → features → rules → IsolationForest → RandomForest → XGBoost →
optional QSVM → weighted-voting fusion`).

Canonical label space: **`0 = benign`**, **`1 = malicious`**. Rows without an
explicit category that resolve to `malicious` are tagged with the generic
category `malicious` (never mislabeled `benign`).

## 2. Dataset groups

Groups are **configurable, not hard-coded** (`configs/training.json`). Each
group is a list of stable registry `dataset_id`s:

| Group | Role | Data-role guarantee |
|---|---|---|
| `datasets.train` | Training pool | Only ever fits the model |
| `datasets.validation` | Holdout | Stratified split out of the train sources; scored after training |
| `datasets.test` | Internal test | Official `test` split when a source provides one; never trained on |
| `datasets.external_eval` | Generalization | **Never enters training.** Missing/gated optional sources warn and continue |

Rules:

- A dataset may appear in several groups. When a source with official
  train/test splits appears in both `train` and `test`, its official
  `test` rows go to the internal test pool and only official `train` rows are
  used for training (`splitting.assign_groups`).
- External-eval sources **must never** enter training; they are evaluated
  after training to measure generalization.
- Required sources (train/validation) that cannot be downloaded **raise**.
  Optional sources (external eval) that are missing or gated are recorded as
  `available: false` and skipped — no metrics are fabricated for them.
- Every dataset's lifecycle is auditable via `dataset_manifest.json`.

### 2.1 Defaults

```
train          = deepset-prompt-injections, dolly-benign
validation     = deepset-prompt-injections
test           = deepset-prompt-injections
external_eval  = jbb-behaviors + 8 gated ids (jailbreakbench-attacks, wildjailbreak,
                 harmbench-behaviors, advbench, hex-phi, pal, agentdojo,
                 cyberseceval-prompt-injections)
caps           = dolly-benign: 2000, wildjailbreak: 5000   (per-source, recorded in manifest)
```

Per-dataset caps are `None` = no cap. Caps are never silent: every cap is
recorded in the manifest.

## 3. Modules

| Module | Public API | Responsibility |
|---|---|---|
| `schema.py` | `DatasetRecord` (dataclass), `DEFAULT_CATEGORY`, `GENERIC_MALICIOUS_CATEGORY` | Canonical record: `text`, `label` (0/1), `source`, `split`, `category`, metadata; `to_dict` / `from_dict` |
| `normalize.py` | `DatasetRecordPreprocessor.preprocess(spec, split_paths)` | Maps raw rows onto `DatasetRecord` via the benchmark column-mapping rules; skips + counts invalid rows |
| `config.py` | `TrainingPipelineConfig`, `DatasetGroupConfig`, `DedupConfig`, `ModelConfig`, `EvalConfig` | Pydantic config (JSON file or dict); masked `hf_token`; `from_file`; `evaluator_kwargs()` |
| `dedup.py` | `normalized_text`, `exact_hash`, `text_hash`, `dedup_records`, `detect_leakage`, `remove_leaked`, `LeakageReport` | Exact + normalized SHA-256 hashing; per-pool dedup; train↔eval leakage detection |
| `splitting.py` | `assign_groups`, `split_by_label`, `split_train_pool`, `cap_records` | Seeded, label-stratified deterministic splits; official-test routing; capping |
| `manifest.py` | `DatasetManifest`, `DatasetCounts` | Auditable per-dataset + per-pool counts |
| `prepare.py` | `DatasetPreparationPipeline.prepare(config, output_dir, include_only=None)` | Orchestrates download → normalize → cap → dedup → split → leakage removal → artifacts; returns `PreparedDatasets` |
| `train.py` | `TrainingPipeline.train(config, prepared, max_samples_per_class=...)` | Fits `HybridEvaluator`, writes `metrics.json`, `training_config.json`, `training_log.txt`, `model/` checkpoint |
| `evaluate.py` | `EvaluationPipeline.evaluate(config, prepared, checkpoint_dir=...)` | Scores test/validation/external pools, produces `evaluation.json`/`evaluation.md` |
| `__init__.py` | re-exports the public API | Package surface |
| `cli.py` | `main()` → `q-guardian` | `dataset prepare/validate`, `model train/evaluate`, `benchmark` subcommands |

## 4. Deterministic splits, dedup and leakage

- **Deterministic splits** — seeded `random.Random(seed)` per label, so runs are
  reproducible. Official `test` splits are preferred when available.
- **Dedup** — two hash families over text:
  - `exact_hash` — SHA-256 of case-folded, trimmed raw text.
  - `text_hash` — SHA-256 of **NFKC-normalized**, case-folded,
    whitespace-collapsed text with invisible/control characters (Unicode
    categories `Cf`/`Cc`) stripped. Encoding-trick prompts therefore hash with
    their plaintext variants.
  `dedup_records` keeps the earliest (or, with `keep_first=False`, the latest)
  occurrence and records every removal.
- **Leakage detection** — before training, every evaluation sample
  (validation/test/external) is checked against the final training pool with
  both hash families. Leaked samples are removed from the eval pools and
  reported in `leakage_report.json` (kind, train source, eval source).
- **`dedup.enabled` semantics (explicit)** — `enabled` is the master switch for
  **within-pool deduplication only**. Setting `"enabled": false` leaves the
  training pool untouched, but **does not** disable train↔eval leakage
  detection: leaked evaluation rows are still removed and reported, so a
  disabled dedup can never silently contaminate evaluation results.
  `exact` / `normalized` select the hash families used by *both* mechanisms.

## 5. Run artifacts

Every run directory contains:

| Artifact | Content |
|---|---|
| `dataset_manifest.json` | seed, groups, per-dataset counts (`requested/filtered/loaded/capped/deduplicated/leaked/final/available`), per-pool stats |
| `leakage_report.json` | train↔eval contamination per split |
| `label_distribution.json` | benign/malicious counts per split |
| `splits/{train,validation,test,external_eval}.jsonl` | canonical records |
| `training_config.json` | frozen config (token always masked as `***`) |
| `metrics.json` | train/validation sample counts + per-provider validation metrics |
| `training_log.txt` | human-readable run log |
| `model/hybrid_evaluator.joblib` | fitted `HybridEvaluator` checkpoint |
| `model/params.json` | provider/weight/model params restored with the checkpoint |
| `evaluation.json` | full evaluation report (`config`, `matrix`, `per_category`, `threshold_analysis`, `summary`) |
| `evaluation.md` | human-readable report |

Checkpoints round-trip: `HybridEvaluator.save_state(dir)` writes
`hybrid_evaluator.joblib` + `params.json`; `load_state(dir)` restores the model
and its providers without refitting.

## 6. Metrics

- Metrics come **only from real model output**. Unavailable datasets appear in
  the matrix as `available: false` with `samples: 0` — no fabricated numbers.
- Per-dataset matrix rows include `detection_rate` (recall), `benign_rejection_rate`
  (specificity), `fpr`, `fnr`, `f1`, `accuracy`, `roc_auc`, `pr_auc` at the
  configured `threshold`.
- `threshold_analysis` sweeps the configured thresholds over the internal test
  pool and reports precision/recall/F1/FPR per threshold; `best_threshold*`
  land in the summary.
- Summary aggregates: `internal_test_*`, `external_datasets_evaluated`,
  `mean_external_detection_rate`, `mean_external_f1`, `mean_external_benign_rejection_rate`.

## 7. Configuration

Configuration is a JSON file (or dict) validated by the existing pydantic
stack — no YAML. Example: `configs/training.json`.

```json
{
  "datasets": {
    "train": ["deepset-prompt-injections", "dolly-benign"],
    "validation": ["deepset-prompt-injections"],
    "test": ["deepset-prompt-injections"],
    "external_eval": ["jbb-behaviors", "wildjailbreak"]
  },
  "seed": 42,
  "validation_ratio": 0.2,
  "model": { "quantum": false, "n_estimators": 50, "contamination": 0.2 },
  "eval": { "threshold": 0.5 }
}
```

HF authentication: `HF_TOKEN` environment variable, or `hf_token` in config
(`SecretStr`, masked in `as_dict()`, never persisted). Gated downloads without
a token raise `DatasetError` for required sources.

## 8. CLI usage

The `q-guardian` entry point is defined in `pyproject.toml`:

```bash
q-guardian dataset prepare  --config configs/training.json --output-dir runs/01
q-guardian dataset validate --config configs/training.json
q-guardian model train     --config configs/training.json --output-dir runs/01 --max-samples 500
q-guardian model evaluate  --config configs/training.json --output-dir runs/01 --threshold 0.5
q-guardian benchmark       --config configs/training.json --k 3
```

- `model train` automatically runs preparation first if `splits/train.jsonl`
  is missing, and reuses existing splits when present.
- `model evaluate` exits non-zero when no checkpoint exists.
- `--epochs` / `--batch-size` / `--learning-rate` are accepted for CLI parity
  and recorded in run metadata, but the hybrid pipeline is
  scikit-learn/quantum based and does not apply them.
- `benchmark` runs the existing `BenchmarkRunner` over public datasets by
  default (`--datasets` to restrict, `--no-quantum` to skip QSVM).

## 9. Quality gates

- **Ruff** — `python -m ruff check src/ tests/` → clean (line-length 100).
- **Format** — `python -m ruff format --check src/ tests/` → clean.
- **mypy** — `python -m mypy src/q_guardian/` → clean for all changed modules
  (the single `yaml` stub warning in `framework/config.py` is pre-existing;
  `types-PyYAML` ships in the `dev` extra used by CI).
- **Tests** — 106 tests across
  `tests/unit/test_training_{schema,normalize,config,dedup,splitting,artifacts,prepare,train,evaluate,cli}.py`
  plus checkpoint round-trip coverage in `test_evaluation_pipeline.py`; the full
  suite (2,751 tests) passes.

## 10. Honest-measurement notes

- `external_eval` generalization numbers are the point of the pipeline: a
  detector that scores well in-distribution but poorly on held-out external
  datasets is surfaced as `mean_external_detection_rate`, not hidden.
- JBB-Behaviors contains harmful *goal statements*, not injection prompts; low
  detection there is a legitimate benchmark result quantifying current-engine
  limits (see `docs/19`).
- Local `jsonl` sources (the benchmark downloader's pass-through) make the
  whole prepare→train→evaluate chain runnable offline in CI and in unit tests.

## 11. XGBoost provider integration (real-data results)

The classical classifier ensemble in `HybridEvaluator`
(`src/q_guardian/evaluation/pipeline.py`) was extended to train, fuse,
persist, and report the existing `XGBoostThreatClassifier`
(`src/q_guardian/ml/models/classifier.py`) — previously implemented but never
wired into the real-data training path. The provider:

- joins `ALL_PROVIDERS` under `XGBOOST_PROVIDER = "xgboost"` and is exported by
  `q_guardian.evaluation`;
- is trained in `fit()` on the same scaled feature vectors as Random Forest;
- is registered in `_setup_providers()` as a `ClassicalModelProvider` (weight
  **0.25** in the default weights, alongside rule 0.15 / isolation-forest 0.10 /
  random-forest 0.35 / qsvm 0.15);
- round-trips through `save_state()` / `load_state()`;
- is labelled `XGBoost` in `_PROVIDER_LABELS` (`report.py`) and surfaced in the
  training log (`available=True/False`);
- remains an **optional extra** (`pyproject.toml` → `ml-xgboost`): when the
  dependency is missing it is skipped with a logged warning, never silently
  disabled when installed.

The fusion logs went from `num_providers=3` (rule, isolation-forest,
random-forest) to `num_providers=4` once XGBoost joined the ensemble.

### 11.1 Real-data run

Re-ran the pipeline on the prepared real splits (2,425 train / 110 validation
samples, `configs/training.json`, `quantum=false`) into
`artifacts/training_xgboost_fix/`:

- `model train` → `metrics.json`, `training_log.txt`, `model/hybrid_evaluator.joblib`
- `model evaluate` → `evaluation.json` / `evaluation.md`
- `scripts/evaluate_pipeline.py --dataset <test.jsonl> --k 5 --no-quantum`
  → `benchmark/report.md`

**Validation metrics** (`metrics.json`):

| Provider | Accuracy | Precision | Recall | F1 | ROC-AUC |
| --- | --- | --- | --- | --- | --- |
| Hybrid Fusion | 0.8091 | 1.0000 | 0.4878 | 0.6557 | 0.9063 |
| Rule Engine | 0.6818 | 1.0000 | 0.1463 | 0.2553 | 0.5732 |
| Isolation Forest | 0.6727 | 0.5581 | 0.5854 | 0.5714 | 0.7529 |
| Random Forest | 0.8455 | 1.0000 | 0.5854 | 0.7385 | 0.9145 |
| **XGBoost** | **0.8273** | **0.9583** | **0.5610** | **0.7077** | **0.9194** |

XGBoost achieved the highest individual ROC-AUC on the held-out validation set
(0.9194), above Random Forest (0.9145).

**5-fold cross-validation on the real test split** (116 samples, `benchmark/report.md`):

| Provider | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC | ECE | Brier | MCC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hybrid Fusion | 0.8279 | 0.8895 | 0.7833 | 0.8253 | 0.9295 | 0.9456 | 0.2059 | 0.1334 | 0.6719 |
| Rule Engine | 0.5598 | 1.0000 | 0.1500 | 0.2558 | 0.5750 | 0.4579 | 0.4616 | 0.4483 | 0.2754 |
| Isolation Forest | 0.6551 | 0.9267 | 0.3667 | 0.5186 | 0.7258 | 0.7762 | 0.1544 | 0.2328 | 0.4115 |
| Random Forest | 0.8109 | 0.8314 | 0.8333 | 0.8209 | 0.9379 | 0.9480 | 0.1618 | 0.1178 | 0.6382 |
| **XGBoost** | **0.8196** | **0.8509** | **0.8167** | **0.8249** | **0.9106** | **0.9343** | **0.1491** | **0.1336** | **0.6510** |

ROC-AUC ranking: Random Forest (0.9379) > Hybrid Fusion (0.9295) > XGBoost
(0.9106) > Isolation Forest (0.7258) > Rule Engine (0.5750). XGBoost's F1
(0.8249) and MCC (0.6510) are the best among individual providers and
practically match the fused ensemble.

**Ablation (fusion with one provider removed)**:

| Removed provider | Fused ROC-AUC | Δ AUC | F1 | Δ F1 |
| --- | --- | --- | --- | --- |
| Rule Engine | 0.9295 | +0.0000 | 0.8282 | −0.0029 |
| Isolation Forest | 0.9309 | −0.0014 | 0.8253 | +0.0000 |
| Random Forest | 0.9116 | +0.0179 | 0.8220 | +0.0033 |
| XGBoost | 0.9385 | −0.0090 | 0.7912 | +0.0342 |
| Quantum QSVM | 0.9295 | +0.0000 | 0.8253 | +0.0000 |

> Report recommendation: removing xgboost hurts the fused result most
> (composite delta 0.0252); the fusion relies most on xgboost (its removal
> lowers fused F1 by 0.0342, the largest drop of any provider). Removing
> isolation-forest, qsvm, rule-engine neither lowers ROC-AUC nor F1; these
> providers are candidates for weight reduction or removal.

### 11.2 Regression coverage

- New `test_xgboost_trained_and_in_fusion` in
  `tests/unit/test_evaluation_pipeline.py` asserts XGBoost is trained,
  registered in `provider_ids()`, and present in evaluation results when the
  package is installed.
- Provider-set assertions and the benchmark ablation/CV assertions are now
  availability-aware, so a future regression that silently drops XGBoost is
  caught by CI.
- Verification for this change: **1,865 unit tests + 14 integration tests
  pass**; `ruff check` and `mypy` clean.
