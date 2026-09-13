# Phase 1 — Cross-Dataset Analytics: Schema Analysis

This document is written before implementation. It records the existing result
schemas, the inconsistencies between them, what is reusable, and why the new
`q_guardian.analytics` package does not duplicate any existing (or in-flight)
functionality.

## 1. Scope of the new module

The task is a **backend** layer that aggregates Q-Guardian's existing
benchmark/evaluation results **across datasets** and produces aggregate
reports. It consumes already-produced artifacts; it does not run new
experiments.

Three artifacts are produced today:

| Producer | Artifact | Shape |
| --- | --- | --- |
| `benchmark run` (CLI) | `<output>/benchmark/<dataset_id>.json` | `BenchmarkReport.as_dict()` |
| `model evaluate` (CLI) | `<run_dir>/evaluation.json` | `EvaluationReport.as_dict()` |
| training QA scripts | `reports/ml_baseline/baseline_metrics.json` | pool-wise `metrics_at_default` |
| external study | `reports/ml_external_study/final_report.json` | study narrative (not in scope to normalize) |

## 2. Existing benchmark result schema

`BenchmarkReport.as_dict()` (`src/q_guardian/benchmark/report.py:30`) produces:

```json
{
  "dataset": {"id": "...", "name": "...", "license": "...", "homepage": "..."},
  "validation": {"total": 0, "valid_rows": 0, "labels": {}, "issues": []},
  "benchmark": {
    "config": {"k": 5, "seed": 42, "threshold": 0.5,
               "evaluator": {"quantum": true, "quantum_feature_count": 5,
                             "n_estimators": 50, "contamination": 0.2, ...},
               "dataset_id": "..."},
    "dataset": {"total": 0, "threats": 0, "benign": 0, "threat_ratio": 0.0,
                "categories": {}},
    "cross_validation": {
      "fold_count": 5,
      "folds": [{"fold": 1, "train_size": 0, "test_size": 0,
                 "fusion_roc_auc": 0.0, "fusion_f1": 0.0, "fusion_accuracy": 0.0}],
      "metrics": {
        "fusion":        {"accuracy": {"mean":0,"std":0,"min":0,"max":0}, "...": {...}},
        "rule-engine":   {"...": {...}},
        "isolation-forest": {"...": {...}},
        "random-forest": {"...": {...}},
        "xgboost":       {"...": {...}},
        "qsvm":          {"...": {...}}
      },
      "roc_auc_ranking": [{"provider": "...", "mean_roc_auc": 0.0}]
    },
    "ablation": {...},
    "ablation_summary": {...}
  }
}
```

Provider metric aggregates are always `{mean, std, min, max}` over CV folds.

`docs/output/evaluation/report.json` is the same inner `benchmark` dict written
as a standalone file (no `dataset`/`validation` envelope; `config.dataset` is a
string).

## 3. Evaluation report schema (`model evaluate`)

`EvaluationReport.as_dict()` (`src/q_guardian/training/evaluate.py:53`) produces:

```json
{
  "config": {...},
  "matrix": [
    {"dataset": "test", "pool": "test", "samples": 0, "benign": 0, "malicious": 0,
     "detection_rate": 0.0, "benign_rejection_rate": 0.0,
     "fpr": 0.0, "fnr": 0.0, "f1": 0.0, "accuracy": 0.0,
     "roc_auc": 0.0, "pr_auc": 0.0, "available": true, "note": ""},
    {"dataset": "<external id>", "pool": "external_eval", "...": ...}
  ],
  "per_category": [...],
  "threshold_analysis": [...],
  "summary": {...}
}
```

Rows are **scalars** for a single detector (the trained hybrid fusion model),
**not** per-provider CV aggregates. Row metrics use different names:
`detection_rate` = recall, `benign_rejection_rate` = specificity,
`fpr`/`fnr`, `f1`, `accuracy`, `roc_auc`, `pr_auc`. Unavailable datasets carry
`available: false` and `None` metrics — **never fabricate or aggregate those**.

## 4. Baseline metrics schema (training QA)

`reports/ml_baseline/baseline_metrics.json`:

```json
{
  "generated_at": "...", "commit": "...", "checkpoint_dir": "...",
  "feature_schema": {"handcrafted_dims": 43, "total_dims": 43, ...},
  "providers_active": ["rule-engine", "isolation-forest", "random-forest", "xgboost"],
  "default_threshold": 0.5,
  "pools": {
    "validation": {"split_file": "...", "samples": 0, "malicious": 0, "benign": 0,
      "metrics_at_default": {"fusion": {"accuracy": 0.0, "...": 0.0}, "...": {}},
      "latency": {...}},
    "test": {...},
    "external_jbb": {...}
  },
  "operating_point": {...}
}
```

Provider metrics here are flat scalars at the default threshold, **no std** (a
single evaluation, not CV folds). They additionally carry `specificity`,
`false_positive_rate`, `false_negative_rate`, and confusion-matrix counts
(`true_positives`, ...).

## 5. Inconsistencies between schemas

| Aspect | benchmark | evaluation | baseline |
| --- | --- | --- | --- |
| per-provider detail | yes (6 providers) | no (single fusion detector) | yes (providers_active) |
| distribution (mean/std) | `{mean,std,min,max}` | scalar (`None` allowed) | scalar |
| metric names | `recall`,`specificity` (via `fpr`), `f1_score`, `roc_auc`, ... | `detection_rate`, `fpr`, `f1`, `roc_auc`, ... | `recall`, `specificity`, `false_positive_rate`, ... |
| dataset identity | `dataset.id` + metadata | matrix `dataset` string | pool name (`validation`/`test`/`external_jbb`) |
| sample size | `benchmark.dataset.total` | `matrix[i].samples` | `pools[<name>].samples` |
| internal/external scope | implicit (each dataset is a held-out corpus) | explicit (`matrix[i].pool`) | pool name implies scope |
| availability flag | n/a | `available: false` | n/a |

**Consequences for the new layer:**

1. A normalization step must map all three formats onto one canonical model and
   record the origin format (so the report can say where each number came from).
2. metrics must be remapped: `detection_rate → recall`,
   `benign_rejection_rate → specificity`, `fpr → false_positive_rate`,
   `fnr → false_negative_rate`, `f1 → f1_score`.
3. `std/min/max` may be absent; synthesized "±" values must **never** be
   invented. Reports must show `-` when a distribution is unavailable.
4. The aggregation semantics must be explicit: **macro** (unweighted mean of
   dataset means), **weighted** (dataset-size weighted mean), **micro**
   (pooled — equal to weighted when per-dataset sizes are available). These are
   reported as distinct numbers.
5. Datasets that share sample text between themselves (documented leakage,
   e.g. JBB↔external splits) must appear only as a **warning**, not silently
   combined.
6. Incompatible experiments (different fold counts, thresholds, feature
   contracts) must fail or warn loudly rather than being silently averaged.

## 6. What already exists and is reusable

- `src/q_guardian/observability/analytics/statistics.py` — pure statistics
  (`mean`, `median`, `percentile`, `linear_regression`). Reuse for distribution
  summaries; the aggregator adds weighted mean/std on top.
- `src/q_guardian/training/artifacts.py::write_json` — canonical JSON writer.
- `src/q_guardian/evaluation/pipeline.py::ALL_PROVIDERS` and the `fusion`
  provider name — single source of truth for provider IDs.
- `src/q_guardian/evaluation/benchmark.py::_METRIC_KEYS` — canonical metric key
  set for the CV path.
- `src/q_guardian/evaluation/report.py::to_markdown` — single-dataset markdown
  rendering pattern (table style to mimic).
- `src/q_guardian/observability/exporters/csv.py` — CSV writer pattern.
- `src/q_guardian/benchmark/registry.py::DatasetRegistry` — stable dataset ids.

## 7. What is explicitly out of scope (no duplication)

- `observability/analytics` (`AnalyticsEngine`) is **operational telemetry**
  (in-memory threat/policy/risk/response trends and forecasts for the running
  service). Different data, different consumers. Not touched.
- `observability/dashboard` is a runtime dashboard API. Not touched.
- PR #9 (`feature/ui-integration`, open) adds a **frontend** historical
  analytics view + console dashboard. Its only backend changes are console
  authentication endpoints (`api/v1/endpoints/auth.py`,
  `api/v1/dependencies/auth.py`), not analytics. No backend overlap.
- `reports/ml_external_study/final_report.json` is a hand-written study
  narrative; not a normalized artifact.
- The new module does **not** run detectors, download datasets, or recompute
  per-sample scores.

## 8. Design of the new package

New package: `src/q_guardian/analytics/`

| Module | Responsibility |
| --- | --- |
| `provider.py` | provider → class (classical/quantum/fusion) mapping |
| `models.py` | canonical dataclasses (`NormalizedResult`, metric stats, aggregation) |
| `normalizer.py` | accept `BenchmarkReport` / dict / `Path`; detect format; map to canonical model |
| `compatibility.py` | cross-dataset compatibility check (errors/warnings) |
| `aggregator.py` | macro / weighted / micro cross-dataset aggregates + ranking |
| `comparison.py` | classical vs quantum vs fusion comparison with honesty guardrails |
| `generalization.py` | internal→external gap + cross-dataset consistency |
| `reporting.py` | JSON / CSV / Markdown renderers |
| `service.py` | facade: `analyze(...)` → report; `analyze_files(...)` |

CLI: new `q-guardian analytics` subcommand in `src/q_guardian/cli.py`.

Testing: `tests/unit/test_analytics_*.py` using small dict fixtures (never
real downloads) modelled on `tests/unit/test_training_cli.py` conventions.