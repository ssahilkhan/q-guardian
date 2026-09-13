# Cross-Dataset Analytics & Aggregate Reporting

`q_guardian.analytics` is the backend layer that turns Q-Guardian's existing
benchmark, evaluation and baseline artifacts into one cross-dataset report.
It aggregates per-dataset results, ranks providers, compares classical vs
quantum providers and analyzes internal-to-external generalization.

It **does not run detectors, download datasets or change any measurement**. It
consumes already-produced JSON artifacts and never synthesizes measurements
that were not actually recorded.

- Schema analysis: [`docs/analytics/schema_analysis.md`](schema_analysis.md)

## Quick start

```bash
# Aggregate everything produced in two locations
q-guardian analytics \
  --reports reports/ml_baseline docs/output/evaluation \
  --aggregation macro \
  --output-dir reports/analytics

# Pass files directly (directories are globbed for *.json)
q-guardian analytics --reports reports/ml_baseline/baseline_metrics.json

# Proceed even when experiments are not fully comparable
q-guardian analytics --reports ... --no-strict
```

Output:

| File         | Contents                                            |
| ------------ | --------------------------------------------------- |
| `report.json` | Machine-readable document (all stages)             |
| `report.csv`  | Flat long-table for pivoting                        |
| `report.md`   | Human-readable report                              |

## Input artifacts

Three existing formats are normalized onto a single canonical model
(`NormalizedResult`):

| Format    | Example artifact                                    | Notes                              |
| --------- | --------------------------------------------------- | ---------------------------------- |
| benchmark | `BenchmarkReport.as_dict()` and standalone inner reports (`docs/output/evaluation/report.json`) | CV fold aggregates; distribution kept |
| evaluation| `EvaluationReport.as_dict()` matrix rows            | Single-pass fusion scalars; renamed canonical metrics |
| baseline  | `reports/ml_baseline/baseline_metrics.json` pools  | Per-provider scalars per pool       |

Normalization handles the metric naming differences — e.g. evaluation rows map
`detection_rate -> recall`, `benign_rejection_rate -> specificity`,
`fpr -> false_positive_rate`, `fnr -> false_negative_rate`,
`f1 -> f1_score` — preserving the measured values and the originating format.
Bookkeeping fields embedded in some artifacts (`support`, confusion-matrix
counts, `threshold`) are excluded from metric aggregation.

## Aggregation modes

| Mode      | Definition                                                        |
| --------- | ----------------------------------------------------------------- |
| `macro`   | unweighted mean of per-dataset means (each dataset equal)         |
| `weighted`| dataset-size weighted mean                                        |
| `micro`   | pooled estimate over samples (approximated as the sample-size weighted mean; true micro pooling needs per-sample score files) |

The standard deviation across datasets is reported only when more than one
dataset contributes; a single-dataset estimate renders `-` instead of a
fabricated `0`.

## Compatibility checks

Cross-dataset averages are only meaningful when experiments are comparable.
`CompatibilityReport` distinguishes hard errors from soft warnings:

- **Errors** (aggregation refused in strict mode): duplicate dataset ids,
  non-finite metric values, empty input.
- **Warnings** (always shown): mixed measurement protocols, differing fold
  counts, differing decision thresholds, differing evaluator/feature
  contracts, no external datasets present for generalization analysis.

`--no-strict` still refuses the report (warnings are always surfaced) — it
simply proceeds when a hard error is present so you can inspect the damaged
collection.

## Classical vs quantum comparison

Providers are classified centrally in `analytics/provider.py`
(fusion, classical: rule-engine / isolation-forest / random-forest / xgboost,
quantum: qsvm). Per-class summaries and classical-minus-quantum deltas are
reported per metric, and **advantage claims are guarded**:

- with fewer than two datasets on either side, the report says the evidence
  is not conclusive;
- a difference is only described as an advantage when it exceeds the combined
  cross-dataset spread;
- when no quantum results are present, the report says so instead of silently
  comparing to an empty estimate;
- deltas are aggregate comparisons, never paired statistical tests — the
  report says this explicitly.

## Generalization analysis

Using the recorded pool scope (internal hold-out vs external datasets), the
report computes the fused detector's internal-to-external gap on F1, ROC-AUC,
recall, specificity and accuracy, plus per-dataset external tables and an
external-consistency summary (mean/std/min/max). A single external dataset is
flagged as not conclusive evidence of a trend.

## Library API

```python
from q_guardian.analytics import CrossDatasetAnalytics

service = CrossDatasetAnalytics(aggregation_mode="macro", strict=True)

# From report objects, dicts, paths or directories
report = service.analyze([{"pools": {...}}, "benchmark/reports/x.json"])
report = service.from_files(["reports/ml_baseline", "docs/output/evaluation"])

# Write JSON/CSV/Markdown
paths = service.save(report, "reports/analytics")

# Inspect a previously generated report
loaded = service.load_report(paths["json"])
```

Lower-level stages are importable individually for bespoke pipelines:
`normalizer.normalize`, `compatibility.validate`, `aggregator.aggregate_results`,
`ranking.build_leaderboard`, `comparison.compare_classical_quantum`,
`generalization.analyze_generalization`, `reporting.generate_report`.

## API integration

No new HTTP endpoints are introduced by this module. Consumers use the
`q-guardian analytics` CLI or the `CrossDatasetAnalytics` library directly.

- `observability/analytics` (runtime operational telemetry) and
  `observability/dashboard` (runtime dashboard API) are intentionally left
  untouched — different data, different consumers.
- PR #9 (`feature/ui-integration`, open) supplies the **frontend** console
  dashboard with console-auth backend endpoints only; it has no
  cross-dataset analytics backend and therefore does not overlap. If the
  console later wants to render aggregate reports, it can read the
  `report.json` output above — no new analytics endpoint is required.

## Design decisions

- **Dataclass models, not pydantic** — consistent with the benchmark and
  evaluation packages; the report is a plain document.
- **No synthesizing** — missing fold distributions are rendered `-`; unknown
  sample sizes in weighted modes fall back to weight `1.0` and are reported in
  `weighted_fallback_count`.
- **Honest conclusion language** — the report never claims a quantum advantage
  unless the evidence meets the guards described above.
- **KISS / single source of truth** — per-dataset raw values are always
  included alongside aggregates so every number can be traced back to a
  dataset and artifact.