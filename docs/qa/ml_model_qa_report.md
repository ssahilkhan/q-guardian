# ML Model QA Evaluation Report

- Generated: 2026-08-21T15:32:04.580278+00:00
- Commit: `705f034`
- Version: 1.1.0
- Python: 3.12.7
- Seed: 42 (deterministic)
- Features: PromptNormalizer -> PromptFeatureExtractor -> MLFeatureProvider (43-dim)

## Datasets

| Dataset | Samples | Benign | Malicious | Role |
|---|---|---|---|---|
| prompt_injections.jsonl | 662 | 399 | 263 | train/validation pool |
| benchmark_prompts.jsonl | 62 | 30 | 32 | external held-out test |

> **Status: EXPERIMENTAL/QA VALIDATION.** No production model artifacts ship with
> the framework. These numbers validate the ML code path, not a shipped model.

## Classifier Results

### random-forest (531 training samples)

| Split | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | FPR | FNR |
|---|---|---|---|---|---|---|---|---|---|---|
| validation | 45 | 70 | 9 | 7 | 0.8779 | 0.8333 | 0.8654 | 0.849 | 0.1139 | 0.1346 |
| external | 23 | 27 | 3 | 9 | 0.8065 | 0.8846 | 0.7188 | 0.7931 | 0.1 | 0.2812 |

### xgboost (531 training samples)

| Split | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | FPR | FNR |
|---|---|---|---|---|---|---|---|---|---|---|
| validation | 44 | 69 | 10 | 8 | 0.8626 | 0.8148 | 0.8462 | 0.8302 | 0.1266 | 0.1538 |
| external | 18 | 26 | 4 | 14 | 0.7097 | 0.8182 | 0.5625 | 0.6667 | 0.1333 | 0.4375 |

## Anomaly Detection (Isolation Forest)

Trained on: benign training split only (unsupervised)

| Split | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | FPR | FNR |
|---|---|---|---|---|---|---|---|---|---|---|
| validation | 40 | 68 | 11 | 12 | 0.8244 | 0.7843 | 0.7692 | 0.7767 | 0.1392 | 0.2308 |
| external | 14 | 28 | 2 | 18 | 0.6774 | 0.875 | 0.4375 | 0.5833 | 0.0667 | 0.5625 |

## Limitations

- No production model artifacts ship with the framework; these models were trained inside this QA run.
- Results are QA validation of the ML code path, NOT production performance claims.
- External set is small (62 samples); treat external metrics as indicative.
- Binary labels: pool uses 0=benign/1=malicious; classifier maps class indices accordingly.
