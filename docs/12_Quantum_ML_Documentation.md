# 12 - Quantum & ML Documentation

> Module: `src\q_guardian\` — Machine Learning Security (Module 5) + Quantum Computing Layer (Module 6)
> Scope: the complete `q_guardian\ml\` and `q_guardian\quantum\` packages, their public APIs,
> internal pipelines, and the hybrid fusion layer that lets rules + classical ML + quantum
> models cooperate on a single prompt decision.
> Relationship: the Quantum module is explicitly designed as an *extension point* of the ML
> module — `q_guardian\quantum\models\base.py` imports `q_guardian.ml.base.BaseThreatModel`.

---

## 1. Two Modules, One Pipeline

The Q-Gaudrail threat-detection pipeline is built in layers. Rules run first
(`security`), then optional ML models (`ml`), then optional quantum models (`quantum`).
The hybrid fusion engine (`quantum\fusion`) combines every available prediction source.

```
   prompt ──► PromptNormalizer ──► PromptValidator ──► PromptFeatureExtractor
                                                           │
                                     ┌─────────────────────┴─────────────────────┐
                                     ▼                                           ▼
                         RuleEngine (security)                  FeatureVector (43-dim, ml)
                                     │                                           │
                                     │                     ┌─────────────────────┼────────────────────┐
                                     │                     ▼                     ▼                    ▼
                                     │           IsolationForest           RandomForest /        QSVMModel
                                     │           (anomaly)                  XGBoost (classify)   (quantum)
                                     │                     │                     │                    │
                                     │                     └──────────┬──────────┘                    │
                                     │                                ▼                               │
                                     │                   InferenceEngine (ml)                         │
                                     │                                │                               │
                                     └────────────────────────────────┼───────────────────────────────┘
                                                                      ▼
                                   HybridFusionEngine ──► FusedPrediction ──► SecurityDecisionEngine
                                                                      │
                                                                      ▼
                                                            PromptDecision (ALLOW / BLOCK / ...)
```

Key design principle shared by both modules: **interfaces over implementations**.
`BaseThreatModel` (ml), `QuantumBackend` (quantum), `QuantumFeatureMap` (quantum),
`QuantumKernel` (quantum), and `PredictionProvider` (fusion) are abstract contracts, so
new models, backends, feature maps, kernels, and prediction sources plug in without
changing any orchestration code.

---

## 2. Feature Representation: 43 vs 12 Dimensions

There are **two distinct feature vectors** in the pipeline. Getting them straight is
essential to using the modules correctly.

### 2.1 `MLFeatureProvider` — the 43-dimensional vector

`q_guardian\ml\feature_pipeline.py` produces a fixed **43-feature** vector intended for
the training pipeline and future models:

| Group | Count | Features |
|---|---|---|
| Statistical (from `PromptFeatures`) | 9 | `length, word_count, line_count, token_estimate, entropy, uppercase_ratio, digit_ratio, special_char_count, suspicious_keyword_count` |
| Keyword flags | 24 | `kw_ignore … kw_extract` — one per suspicious keyword |
| Pattern + character distribution | 10 | `code_block_count, url_count, markdown_usage, has_unicode_escaped, has_html_tags, repeated_pattern_count, unique_char_ratio, avg_word_length, punctuation_ratio, whitespace_ratio` |

The 24 keywords (`_KEYWORDS`): `ignore, forget, override, bypass, jailbreak, system,
prompt, injection, reveal, secret, password, admin, root, sudo, execute, inject,
malicious, exploit, hack, attack, payload, exfiltrate, dump, extract`.

### 2.2 Built-in models — the 12-dimensional vector

The built-in classical and quantum models do **not** use the 43-dim vector. Instead they
build a hand-crafted **12-dimension** vector directly from `PromptFeatures` fields via
their own `_extract_vector`:

```
[length, word_count, line_count, token_estimate, entropy,
 uppercase_ratio, digit_ratio, special_char_count,
 code_block_count, url_count,
 len(suspicious_keywords), len(repeated_patterns)]
```

This identical layout is used by:
- `ml\models\anomaly.py` — `IsolationForestDetector._extract_vector`
- `ml\models\classifier.py` — `RandomForestThreatClassifier` and `XGBoostThreatClassifier`
- `quantum\models\qsvm.py` — `QSVMModel.classify_quantum`

---

## 3. The ML Module — `src\q_guardian\ml\`

### 3.1 Configuration — `ml\config.py`

`MLConfig(BaseModel)`, `ConfigDict(extra="allow")`. Selected fields:

| Field | Default | Meaning |
|---|---|---|
| `enabled` | `False` | enable ML analysis |
| `model_storage_path` | `Path("models/ml")` | persisted artifact directory |
| `auto_save` | `True` | auto-save after training |
| `anomaly_threshold` | `0.5` | anomaly-detection cutoff |
| `classification_threshold` | `0.5` | classification-confidence cutoff |
| `ensemble_weights` | `{}` | per-model weights (empty = equal) |
| `default_test_size` / `default_cv_folds` | `0.2` / `5` | trainer defaults |
| `random_state` | `42` | reproducibility seed |
| `xgboost_available` | `False` | XGBoost installation flag |

TF-IDF fields (`max_features`, `ngram_range`, `use_tfidf`) are declared but unused —
extraction is keyword/statistical/character-based.

### 3.2 Core abstractions — `ml\base.py`, `ml\enums.py`, `ml\data.py`

- **`BaseThreatModel(ABC)`**: `metadata -> ModelMetadata` (property, abstract) and
  `async predict(features: list[float]) -> dict[str, Any]` (abstract); concrete
  `health()`. Quantum models subclass this (via `BaseQuantumModel`).
- **`ModelRegistry`**: in-memory `name -> model` + `name -> metadata`; `register`,
  `unregister`, `get`, `get_metadata`, `list_models`, `list_by_type`, `list_by_backend`,
  `count`, `clear`.
- **Enums** (`ml\enums.py`):
  - `ModelBackend`: `SKLEARN, XGBOOST, QUANTUM, CUSTOM`
  - `ModelStatus`: `UNLOADED, LOADING, READY, ERROR`
  - `ModelType`: `CLASSIFICATION, ANOMALY_DETECTION, ENSEMBLE, ...`
  - `DatasetFormat`, `FeatureType`, `TrainingStatus`
- **Data models** (`ml\data.py`): `ModelMetadata`, `FeatureVector`, `DatasetEntry`,
  `InferenceResult`, `EvaluationMetrics`, `TrainingResult` (all Pydantic).
- **Events** (`ml\events.py`): declared `ml.*` events (e.g. `ModelTrained →
  "ml.training.completed"`, `ThreatClassified → "ml.inference.threat_classified"`).
  Not currently emitted by ml source; `ThreatAnalysisPlugin` emits the *security*
  module's events instead.

### 3.3 Feature pipeline — `ml\feature_pipeline.py`

`MLFeatureProvider(FeatureProvider)`, name `"ml-feature-provider"`. Public methods:
`feature_names` (43 ordered names, lazily computed), `async extract_features(prompt,
base_features)` (returns dict + `feature_vector` + `feature_names`), and the synchronous
`extract_vector(prompt, base_features)` used by training pipelines.

### 3.4 Orchestrator plugin — `ml\plugin.py`

`ThreatAnalysisPlugin(Plugin)`, name `"threat-analysis"`, version `"1.0.0"`,
`interfaces=["prompt_scanner"]`. Holds a rule pipeline (`PromptNormalizer`,
`PromptValidator`, `PromptFeatureExtractor`, `RuleEngine`, `SecurityDecisionEngine`), a
`ModelManager`, and an `InferenceEngine`.

`scan_prompt` workflow (abridged):
1. normalize → validate → extract features;
2. run `RuleEngine.analyze` for `rule_findings`;
3. if `ml_config.enabled` and detectors/classifiers are registered, run
   `InferenceEngine.run` and merge findings + ML scores into `analysis.metadata`
   (ML failure is logged as `ml_inference_error` and never blocks the rule pipeline);
4. `SecurityDecisionEngine.decide(analysis)`, publish events, return `model_dump()`.

Register detectors/classifiers with `register_ml_detector` / `register_ml_classifier`
(registers into both `InferenceEngine` and `ModelManager`).

### 3.5 Persistence — `ml\storage.py`

`ModelStorage(base_path="models/ml")` persists with **joblib** (`.joblib`), layout
`<base_path>/<name>/<name>_v<version>.joblib`. `save` sets status `READY` and refreshes
`updated_at`; `load` raises `ValueError` (no artifact path) / `FileNotFoundError`;
`delete`, `exists`, `list_artifacts` (via `rglob("*.joblib")`).

### 3.6 Detectors & classifiers — `ml\models\`

- **`IsolationForestDetector(PromptDetector, BaseThreatModel)`** — name
  `"isolation-forest"`. `train(X)` fits sklearn `IsolationForest(contamination=0.1,
  n_estimators=100, random_state=42)`. Anomaly score = `clamp(0.5 - decision_function,
  0, 1)`; `is_anomaly` from raw prediction `-1`; finding severity `MEDIUM` (<0.7) or
  `HIGH`. Untrained `predict` returns `{"is_anomaly": False, "anomaly_score": 0.0}`.
- **`RandomForestThreatClassifier(PromptClassifier, BaseThreatModel)`** — name
  `"random-forest-classifier"`. Fits `RandomForestClassifier(n_estimators=100)`; 8
  threat categories (see §5). `classify` returns per-category probabilities; `predict`
  returns top class + confidence.
- **`XGBoostThreatClassifier`** — name `"xgboost-classifier"`, optional. Probes
  `import xgboost` at construction; unavailable → status `UNLOADED`, `train` raises
  `RuntimeError`. Fits `XGBClassifier(use_label_encoder=False, eval_metric="mlogloss",
  verbosity=0, max_depth=6)` on `np.float32`/`np.int32`.
- **`EnsembleDetector(PromptDetector, BaseThreatModel)`** — name `"ensemble-detector"`.
  Weighted voting (`default weight 1.0`); `detect` runs every sub-detector (twice —
  findings pass + confidence pass), computes `combined_risk = Σ(risk·weight)/Σweight`,
  deduplicates findings by `rule_id` keeping the highest severity
  (`INFO:0 … CRITICAL:4`), tags findings with `metadata["source_detector"]`.
- **`ModelManager`** — wraps `ModelRegistry` + `ModelStorage`. `_lazy_load`: status
  `LOADING` → storage load → inject into `model._model` → `READY`; failures → `ERROR`.
  `save_model`, `save_all`, `unload_model`, `version_info`, `health`.

### 3.7 Inference engine — `ml\inference\engine.py`

`InferenceEngine(registry=None, config=None)`:
- `register_detector` / `register_classifier` / `unregister_*`, `detector_count`,
  `classifier_count`;
- `async run(prompt, features) -> InferenceResult`: runs every detector and classifier,
  aggregates `avg_risk`, `avg_confidence`, merged `category_scores` (max per category);
  `is_threat = avg_risk > classification_threshold or max_category_score >
  classification_threshold`; `is_anomaly = avg_risk > anomaly_threshold`; per-model
  exceptions logged and skipped (`inference_detector_error`,
  `inference_classifier_error`).

### 3.8 Datasets & evaluation & training

- **`ml\datasets\`**: `DatasetLoader(ABC)` (`name`, `async load(source, **kwargs)`,
  `async load_split`); `CSVLoader` (columns `prompt`, `label`, optional `severity`,
  `is_malicious`), `JSONLoader` (JSON array / JSONL / dict wrapper), `HuggingFaceLoader`
  (optional `datasets` dependency; kwargs `split`, `prompt_column`, `label_column`,
  `max_samples`, `streaming`).
- **`ml\evaluation\metrics.py`**: `BenchmarkMetrics.compute_classification_metrics`
  (accuracy/precision/recall/F1/AUC via `_approximate_auc_roc = clamp((tpr+(1-fpr))/2,
  0, 1)`, confusion matrix, per-class metrics); `compute_anomaly_metrics`;
  `ResearchMetrics.compute_prompt_security_metrics` (severity-weighted accuracy with
  weights `info 0.1, low 0.2, medium 0.5, high 0.8, critical 1.0`).
- **`ml\training\trainer.py`**: `ModelTrainer.train(model, X, y, feature_names=None,
  test_size=None, cv_folds=None)` → train/test split, fit, `cross_val_score` (accuracy,
  `cv=min(folds, len(X_train))`), test metrics, `feature_importances_` zipped with
  `feature_names`, auto-save via `ModelStorage`. Returns `TrainingResult(COMPLETED|FAILED)`.
  `train_anomaly_detector(model, X)` is unsupervised. `CrossValidator.cross_validate`
  returns `{"scores", "mean", "std", "folds", "scoring"}`.

---

## 4. The Quantum Module — `src\q_guardian\quantum\`

The quantum package is self-contained: the only place any quantum SDK (Qiskit) may be
imported is `backends\qiskit_backend.py`. Everything else works against the local
pure-Python simulator.

### 4.1 Config, enums, data, exceptions

- **`quantum\config.py`** — five Pydantic configs:
  - `QuantumBackendConfig`: `backend_type=SIMULATOR`, `num_qubits=5`, `shots=1024`,
    `optimization_level=1`, `timeout_seconds=30.0`, `max_parallel_jobs=4`,
    `provider_options={}`;
  - `QuantumFeatureMapConfig`: `encoding_type=ANGLE`, `feature_map_depth=2`,
    `entanglement="linear"`, `feature_range=(0.0, 3.14159)`, `normalize_features=True`,
    `max_features=32`;
  - `QuantumTrainingConfig`: `optimizer=COBYLA`, `max_iterations=100`, `batch_size=32`,
    `validation_split=0.2`, `early_stopping_patience=10`, `random_state=42`;
  - `QuantumFusionConfig`: `strategy=STACKING`, `quantum_weight=0.3`,
    `classical_weight=0.5`, `rule_weight=0.2`, `confidence_threshold=0.5`,
    `stacking_meta_learner="logistic_regression"`;
  - `QuantumConfig`: `enabled=False`, nested backend/feature_map/training/fusion,
    `model_storage_path=Path("models/quantum")`, `evaluation_shots=4096`,
    `benchmark_repetitions=3`. (Distinct from the slim
    `q_guardian.framework.config.QuantumConfig`.)
- **`quantum\enums.py`** — `QuantumBackendType` (simulator, qiskit_aer, qiskit_runtime,
  ibm_quantum, pennylane, cudaq, local, custom), `EncodingType` (angle, amplitude,
  zz_feature_map, pauli, custom), `CircuitType` (feature_map, variational, kernel,
  measurement, hybrid), `MeasurementBasis`, `OptimizerType` (cobyla, l_bfgs_b, spsa,
  adam, gradient_descent, nelder_mead, powell), `QuantumModelType` (qsvm, vqc, qnn,
  kernel_estimator, ensemble, custom), `ExecutionStatus`, `BackendStatus`,
  `FusionStrategyType` (weighted_voting, confidence_based, stacking, adaptive, bayesian,
  max_confidence).
- **`quantum\data.py`** — DTOs (all `populate_by_name=True`): `CircuitResult`,
  `QuantumCircuitInfo`, `QuantumModelMetadata`, `BackendInfo`, `QuantumTrainingResult`,
  `QuantumInferenceResult`, `QuantumEvaluationMetrics`, `FusedResult` (legacy fusion
  output; the Phase-3 path uses `FusedPrediction`). All `*_id` fields default to
  `generate_uuid()`; timestamps are `datetime.now(UTC)`.
- **`quantum\exceptions.py`** — hierarchy rooted at `QuantumError`:
  `BackendError` → `BackendNotAvailableError`, `CircuitExecutionError`,
  `TranspilationError`; `FeatureMapError` → `EncodingDimensionError`; `KernelError`,
  `ModelNotTrainedError`, `TrainingError`, `ConfigurationError`, `FusionError`,
  `QuantumInferenceError` (carries `detail` + `model_name`).
- **`quantum\events.py`** — declared `quantum.*` events (backend/circuit/model/
  training/fusion/calibration). Not emitted by current source; reserved for event-bus
  wiring.

### 4.2 Backends — `quantum\backends\`

- **`QuantumBackend(ABC)`** — abstract `name`, `backend_info`, `is_available()`,
  `async execute_circuit(circuit, shots=1024, **kwargs)`, `transpile(circuit,
  optimization_level=1)`; concrete `health()` and `supports_operation()`.
- **`LocalSimulatorBackend`** — pure-Python statevector simulator (no SDK), name
  `"local-simulator"`. Gates: H, X, Y, Z, Rx, Ry, Rz, CX, CZ, Measure. Simulation:
  `state = zeros(2^n)`, `state[0]=1`, per-gate `_apply_gate`, Born-rule probabilities,
  `np.random.choice` sampling. Backend `capabilities=["statevector", "measurements",
  "expectation_values"]`. This is the default backend created by
  `BackendManager.create_default_backend()`.
- **`QiskitAerBackend`** — optional `qiskit_aer` simulator; name `"qiskit-aer"`;
  unavailable → `is_available()==False`.
- **`QiskitRuntimeBackend`** — IBM Quantum hardware via `QiskitRuntimeService`;
  name `"qiskit-runtime"`; default backend `ibm_brisbane`.
- **`BackendManager(config=None)`** — register/unregister/get/list backends;
  `set_active_backend` (raises `BackendNotAvailableError`), `get_active_or_fallback()`
  (active → fallback order → first available → raise), `set_fallback_order`,
  `health_check()`, `create_default_backend()` (lazy `LocalSimulatorBackend`).

### 4.3 Feature maps — `quantum\feature_maps\`

- **`QuantumFeatureMap(ABC)`** — abstract `name`, `encoding_type`, `num_qubits`,
  `encode(features) -> EncodedCircuit`; concrete `encode_batch`, `validate_features`,
  `health()`.
- **`EncodedCircuit(BaseModel)`** — `circuit: Any`, `num_qubits`, `encoding_type`,
  `metadata` (`arbitrary_types_allowed=True`).
- **`AngleEncodingMap`** — name `"angle-encoding"`, `EncodingType.ANGLE`. One rotation
  gate per feature (default Ry; supports Rx/Ry/Rz via `rotation_gates`); needs
  `ceil(d)` qubits for `d` features; `_normalize` min-max rescales into
  `config.feature_range` (constant input → midpoint).
- **`ZZFeatureMap`** — name `"zz-feature-map"`, `EncodingType.ZZ_FEATURE_MAP`. Data
  re-uploading: per layer Ry(`x_i·π`) rotations + CZ entanglement. Entanglement modes:
  `"linear"` (adjacent pairs), `"circular"` (adjacent + wrap), `"full"` (all pairs),
  unknown → linear.
- **`PauliFeatureMap`** — name `"pauli-feature-map"`, `EncodingType.PAULI`. Ry rotations
  + ZZ (as CZ) interactions between adjacent qubits per layer; rotation angle
  `x_i·π`, ZZ phase `x_i·x_{i+1}·π`.

### 4.4 Kernels — `quantum\kernels\`

- **`QuantumKernel(ABC)`** — abstract `name`, `num_qubits`,
  `compute_kernel_matrix(X1, X2=None)`, `evaluate(x1, x2)`, `get_circuit_info()`;
  concrete `health()`.
- **`QuantumKernelEstimator(QuantumKernel)`** — name `"quantum-kernel-<feature_map>"`.
  Estimates fidelity `K(x1,x2) = |⟨φ(x1)|φ(x2)⟩|²`:
  1. `feature_map.encode(x)` each point;
  2. build combined circuit on `2n` qubits — circuit1 gates unchanged, circuit2 gates
     offset by `+n`; Hadamard test: `H(q0)`, `cx(i, i+n)` for all `i`, `H(q0)`;
  3. execute with `shots` (default 4096), read all-zero outcome probability.
  `get_circuit_info()`: `CircuitType.KERNEL`, `depth=2n`, `gate_count=4n`.
  Evaluation runs through a `ThreadPoolExecutor` + `asyncio.run` (30s timeout) when a
  loop is already running. Results cached (key = `id(x)` for short vectors, else
  `hash(tuple(x))`).

### 4.5 Execution — `quantum\execution\`

**`CircuitExecutor(backend_manager=None, config=None)`**:
- `async execute(circuit, shots=None, backend_name=None, **kwargs)`: resolves backend
  (by name or `get_active_or_fallback()`), times execution, tracks `execution_count` /
  `average_execution_time_ms`; wraps unexpected exceptions in `CircuitExecutionError`.
- `get_backend_for_model(num_qubits, needs_hardware=False)`: first available backend
  with enough qubits (and hardware support when required), else active/fallback, else
  raise.

### 4.6 Models — `quantum\models\`

- **`BaseQuantumModel(BaseThreatModel, ThreatClassifier, ABC)`** — the bridge between
  modules. Inherits the ML `BaseThreatModel` contract (`metadata`, `predict`) plus the
  security `ThreatClassifier` contract, and adds abstract `quantum_metadata`,
  `is_trained`, `async predict_quantum(features)`. `health()` extends the ML base with
  `quantum_model_type`, `num_qubits`, `is_trained`.
- **`QSVMModel(BaseQuantumModel)`** — Quantum Support Vector Machine, name `"qsvm"`,
  version `"1.0.0"`. Depends only on Phase-1 abstractions (kernel + feature map +
  backend); never imports Qiskit.
  - `metadata`: backend `CUSTOM`, type `CLASSIFICATION`, status `READY` (trained) /
    `UNLOADED`, tags `["quantum", "qsvm"]`.
  - `train(X, y)`: validates inputs (`TrainingError` on mismatch), computes the full
    kernel matrix, then `_fit_smo`: all samples become support vectors with uniform
    dual coefficients `α_j = 1/n` and
    `bias = mean_i( y_i − Σ_j α_j·y_j·K[i,j] )` (a heuristic — not full SMO).
  - `async predict(features)`: one-vs-rest score
    `score_cls = Σ_j sign(y_j==cls)·α_j·K(features, sv_j) + bias`;
    `probabilities[cls] = max(0, |score| / Σ|scores|)`; confidence = max prob.
  - `async predict_quantum(features)`: wraps `predict`; `risk_score = 1 − confidence`
    unless predicted class is benign.
  - `async classify_quantum(prompt, features)`: builds the 12-dim vector (§2.2),
    predicts, and if `class_idx != 0 and confidence > 0.5` emits a
    `PromptFinding(rule_id="qsvm-detection")` with severity `MEDIUM`/`HIGH` and the
    matching `PromptCategory`.
  - `save()`/`load(data)`: serializes weights, support vectors, timing, kernel/feature
    map names.
- **`QuantumModelManager`** — lifecycle/registration for quantum models
  (`ModelRegistration` dataclass tracks `registered_at`, `last_inference_at`,
  `inference_count`, `error_count`, `tags`, `metadata`). `record_inference`,
  `get_best_model` (fewest errors), `health`, `save_state`, `clear`.

### 4.7 Training — `quantum\training\`

- **`QuantumTrainer(config=None)`**: `train(model, X, y=None, X_val=None, y_val=None)` →
  `model.train(...)`, optional validation accuracy via `asyncio.run(model.predict(xi))`;
  returns `QuantumTrainingResult(completed|failed)`. `cross_validate(model, X, y,
  n_folds=5)` uses contiguous folds, returns `cv_scores`/`cv_mean`/population `cv_std`.
- **`QuantumKernelTrainer(kernel, feature_map)`** — hyper-parameter search for QSVM
  kernels:
  - dataclasses `KernelHyperparams` (defaults: `num_qubits=4`, `feature_map_reps=1`,
    `entanglement="linear"`, `depth=3`, `regularization=1e-3`, `shots=1024`,
    `optimizer=ADAM`, `learning_rate=0.1`), `KernelCandidate` (`composite_score =
    cv_score_mean − 0.1·cv_score_std`), `KernelSearchResult`;
  - `search_grid(X, y, param_grid, cv_folds=5)` / `search_random(X, y,
    param_distributions, n_iter=20)` (numeric 2-tuples → uniform sampling, else
    `np.random.choice`);
  - `cross_validate(X, y, cv_folds=5, hyperparams=None)` — per fold, kernel matrices
    for train and (test vs train); classification by mean kernel similarity per class
    `pred = argmax_cls mean_j K[test, j]`;
  - `train_kernel`, `get_kernel_info`, `clear_cache`.

### 4.8 Inference & evaluation — `quantum\inference\`, `quantum\evaluation\`

- **`QuantumInferenceEngine`**: registers models (with optional `fallback_priority`),
  `select_model` (by name → first trained in fallback order → first trained → None),
  `async infer(features, model_name=None)` (raises `QuantumInferenceError` when no model
  selected; falls back through `_fallback_order` on failure), `infer_batch`, performance
  stats (`error_rate`, `model_usage`, avg/min/max latency), `clear_history`, `health`.
- **`QuantumEvaluator`**: `evaluate(model, X_test, y_test, class_names=None)` computes
  TP/TN/FP/FN, accuracy/precision/recall/F1, FPR/FNR, avg confidence/time, plus
  `circuit_width`, `backend_used`, into `QuantumEvaluationMetrics`. `compare_models`
  evaluates a list and returns `{name: metrics}`.

### 4.9 Storage & plugin — `quantum\storage.py`, `quantum\plugin.py`

- **`QuantumModelStorage(storage_root)`** — JSON persistence, layout:
  `root/<name>/model_metadata.json`, `model_state.json`, `versions/<version>.json`.
  `save` (state + metadata, optional version), `load`, `load_version`, `rollback`
  (writes `rolled_back_from` / `rollback_time` metadata), `delete`, `list_models`,
  `get_storage_stats`.
- **`QuantumAnalysisPlugin(Plugin)`** — name `"quantum-analysis"`, version `"1.0.0"`,
  `interfaces=["quantum_analyzer"]`. Constructs `BackendManager` + `CircuitExecutor`;
  `initialize` creates the default simulator backend when `config.enabled` and no
  backends exist; `register_model`/`unregister_model`/`get_model`/`list_models`;
  `health`/`configuration`.

---

## 5. Hybrid Fusion — `src\q_guardian\quantum\fusion\`

The Hybrid Intelligence Layer (Phase 3) lets rules, classical ML, and quantum models
produce standardized `ThreatPrediction` objects that one engine fuses.

### 5.1 Prediction model — `fusion\prediction.py`

- **`ReasoningTrace`**: `steps`, `evidence`, `rules_triggered`, `feature_importances`,
  `metadata` — explainability trace decoupled from model internals.
- **`ThreatPrediction`**: `prediction_id`, `provider_id` (required), `predicted_label`,
  `confidence` [0,1], `probabilities`, `risk_score` [0,1], `latency_ms`, `backend`,
  `model_name`/`model_version`, `reasoning`, `metadata`, `timestamp`, `is_valid`,
  `error_message`.

### 5.2 Provider interface & adapters — `fusion\providers.py`, `fusion\adapters.py`

- **`PredictionProvider(ABC)`** — abstract `provider_id`, `provider_type` ('rule' |
  'classical' | 'quantum' | 'external'), `async predict(prompt, features=None)`;
  concrete `display_name`, `version="1.0.0"`, `train` (no-op), `health`, `configuration`.
- **`RuleEngineProvider`** — wraps a `RuleEngine`; labels `"threat"` (≥2 high/critical
  findings, `confidence = min(0.5 + high_count·0.15, 0.95)`), `"suspicious"` (1 finding,
  `confidence=0.6`), or `"benign"`.
- **`ClassicalModelProvider`** — wraps any model exposing `predict`; risk defaults to
  `1 − confidence` for non-benign labels.
- **`QuantumModelProvider`** — prefers `predict_quantum` else `predict`; reads
  `quantum_metadata.backend_type` into `backend`.
- **`GenericProvider`** — wraps an arbitrary sync/coroutine callable.

### 5.3 Calibration — `fusion\calibrator.py`

**`ConfidenceCalibrator(method="none", temperature=1.0, smoothing=0.01)`** — normalizes
confidences across providers. Methods:
- `min_max`: `(conf − min)/(max − min)` per provider (0.5 when range ≈ 0);
- `z_score`: `sigmoid((conf − mean)/std)`;
- `temperature`: `sigmoid(logit/T)` where `logit = clip(ln(conf/(1−conf+ε)), −10, 10)`,
  with probability temperature-softmax;
- `none`: passthrough.

`_ProviderStats` keeps Welford online mean/variance + min/max.

### 5.4 Engine — `fusion\engine.py`

**`HybridFusionEngine(strategy=None, calibrator=None, provider_weights=None)`**:
- **Default strategy is `StackingFusionStrategy`**; default calibrator `method="none"`.
- Provider management: `register_provider(provider, weight=None)`,
  `unregister_provider`, `get_provider`, `provider_ids`.
- Strategy management: `register_strategy`, `unregister_strategy` (raises `FusionError`
  if active), `set_strategy` (raises `ConfigurationError` if unknown),
  `available_strategies`.
- `async fuse(prompt, features=None, strategy_name=None, weights=None, calibrate=True)`:
  collect all provider predictions → optionally calibrate → run strategy with merged
  weights → on strategy failure build a degraded `FusedPrediction` (`label="unknown"`,
  `confidence=0.0`, `num_failed`) → record history (cap 500) and stats.
- `get_performance_stats`, `health`, `clear_history`.

### 5.5 Strategies — `fusion\strategies\`

- **`FusionStrategy(ABC)`** — abstract `name`, `fuse(predictions, weights=None)` →
  `FusedPrediction`; concrete `display_name`, `description`, `health`,
  `validate_predictions` (keeps `is_valid`).
- **`FusedPrediction`** — `fused_id`, `predicted_label`, `confidence`,
  `probabilities`, `risk_score`, `strategy_name`, `provider_contributions`,
  `source_predictions`, `calibrated`, `num_providers`, `num_failed`,
  `reasoning_summary`, `metadata`. `to_fused_result()` converts to the legacy
  `FusedResult` dict and derives `quantum_contribution` / `classical_contribution` /
  `rule_contribution` by matching provider-id keywords.
- **`WeightedVotingStrategy`** (`name="weighted_voting"`) — votes weighted by
  `weights.get(pid, 1.0)`; confidence = winning vote share.
- **`ConfidenceFusionStrategy`** (`name="confidence_fusion"`) — weights by each
  provider's own confidence (normalized).
- **`AdaptiveFusionStrategy`** (`name="adaptive"`, `window_size=100`) — rolling
  per-provider accuracy (`update_outcome(provider_id, prediction_label,
  ground_truth)`); weight = `max(0.1, rolling_accuracy)`.
- **`StackingFusionStrategy`** (`name="stacking"`) — meta-learner (logistic
  regression / softmax) trained via `train_metalearner(training_samples,
  ground_truth_labels)`; feature vector = per-provider confidences in sorted provider
  order; untrained → confidence-weighted fallback. **This is the default.**
- **`BayesianFusionStrategy`** (`name="bayesian"`) — fusion in log-odds space:
  `logit(p_post) = w0 * logit(prior) + Σ w_i * logit(p_i)` (see
  `docs/Bayesian_Fusion.md`). Default `prior=0.5`, `decision_threshold=0.7`,
  `reliability_mode="uniform"` (naive Bayes). `predict_with_uncertainty`
  returns posterior + evidence; `update_posterior` is outcome-bookkeeping
  only and never mutates the runtime reliability weights.

---

## 6. Cross-Module Integration Facts

1. **Module 6 reuses Module 5's contracts**: `quantum\models\base.py` imports
   `q_guardian.ml.base.BaseThreatModel`; `quantum\models\qsvm.py` imports
   `ml.data.ModelMetadata` and `ml.enums.{ModelBackend, ModelStatus, ModelType}`.
   `QSVMModel.metadata` builds `ModelMetadata(backend=CUSTOM, model_type=CLASSIFICATION,
   tags=["quantum", "qsvm"])`.
2. **Same 12-dim feature layout** is shared by IsolationForest, RandomForest, XGBoost,
   and QSVM (§2.2).
3. **`InferenceEngine` and `ThreatAnalysisPlugin` need no changes** to accept quantum
   models — quantum models implement `PromptDetector`/`PromptClassifier` via
   `classify_quantum` / the ML base contracts.
4. **No SDK leaks**: Qiskit is confined to `backends\qiskit_backend.py`; `QSVMModel`,
   kernels, and the simulator use dict-based circuits.
5. **Persistence differs by module**: ML uses joblib (`ml\storage.py`); quantum uses
   JSON + versions (`quantum\storage.py`). Paths default to `models/ml` and
   `models/quantum`.
6. **Examples** (`examples\prompt_test_harness.py`) wire `MLFeatureProvider`,
   `IsolationForestDetector(n_estimators=50, contamination=0.2)`, and
   `RandomForestThreatClassifier(n_estimators=50)`.
7. **Threat categories (8)**: `benign, prompt_injection, jailbreak,
   role_manipulation, system_prompt_leak, data_exfiltration, excessive_encoding,
   suspicious_formatting` — shared by classical classifiers and `QSVMModel`.

---

## 7. Key Numbers Cheat-Sheet

| Item | Value |
|---|---|
| ML feature vector | 43 dims (`MLFeatureProvider`) |
| Built-in model vector | 12 dims (classical + quantum) |
| Suspicious keywords | 24 |
| Isolation Forest | `contamination=0.1`, `n_estimators=100` |
| Random Forest | `n_estimators=100`, `max_depth=None` |
| XGBoost | `max_depth=6`, `eval_metric="mlogloss"`, optional |
| Ensemble | weighted voting, dedupe by `rule_id` |
| ML persistence | joblib `.joblib` |
| Quantum persistence | JSON + `versions/` |
| Quantum kernel | fidelity `\|⟨φ(x1)\|φ(x2)⟩\|²` via Hadamard test, `2n` qubits, `4n` gates |
| Kernel shots | 4096 (estimator) / 1024 (trainer) |
| Default fusion strategy | `StackingFusionStrategy` |
| Default fusion weights | quantum 0.3 / classical 0.5 / rule 0.2 (config) |
| Fusion history cap | 500 records |
| Inference history cap | 1000 records |
| Severity weights (research) | info .1, low .2, medium .5, high .8, critical 1.0 |
