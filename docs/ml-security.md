# ML Security Module

## Overview

Module 5 adds machine learning-based threat detection, classification, and analysis to Q-Guardian's prompt security pipeline. It works alongside the rule-based Prompt Security Engine (Module 4) and is designed so Module 6 (Hybrid Quantum Analysis) can add new models without modifying the inference pipeline.

## Architecture

```
ml/
├── __init__.py            # Public API re-exports
├── base.py                # BaseThreatModel ABC, ModelRegistry
├── config.py              # MLConfig (thresholds, storage, training defaults)
├── data.py                # Domain models (ModelMetadata, InferenceResult, etc.)
├── enums.py               # ModelType, ModelBackend, TrainingStatus, etc.
├── events.py              # ML lifecycle events
├── feature_pipeline.py    # MLFeatureProvider (model-agnostic feature extraction)
├── storage.py             # ModelStorage (joblib persistence)
├── plugin.py              # ThreatAnalysisPlugin (unified orchestrator)
├── models/                # Concrete ML model implementations
│   ├── anomaly.py         # IsolationForestDetector
│   ├── classifier.py      # RandomForestThreatClassifier, XGBoostThreatClassifier
│   ├── ensemble.py        # EnsembleDetector
│   └── model_manager.py   # ModelManager (lifecycle, lazy loading, versioning)
├── datasets/              # Dataset loading abstractions
│   ├── base.py            # DatasetLoader ABC
│   ├── csv_loader.py      # CSVLoader
│   ├── json_loader.py     # JSONLoader
│   └── huggingface_loader.py  # HuggingFaceLoader (optional)
├── training/              # Training pipeline
│   └── trainer.py         # ModelTrainer, CrossValidator
├── inference/             # Inference pipeline
│   └── engine.py          # InferenceEngine
└── evaluation/            # Evaluation metrics
    └── metrics.py         # BenchmarkMetrics, ResearchMetrics
```

## Key Components

### BaseThreatModel

Common interface for all ML models. Every algorithm (Isolation Forest, Random Forest, XGBoost, future QSVM) implements this interface:

```python
from q_guardian.ml import BaseThreatModel

class MyModel(BaseThreatModel):
    @property
    def metadata(self) -> ModelMetadata: ...

    async def predict(self, features: list[float]) -> dict[str, Any]: ...
```

### ModelManager

Manages model lifecycle, lazy loading, versioning, and health:

```python
from q_guardian.ml import ModelManager, IsolationForestDetector

manager = ModelManager()
detector = IsolationForestDetector()
manager.register_model(detector)

# Lazy loading from disk
model = manager.get_model("isolation-forest")

# Health check
health = manager.health()
```

### MLFeatureProvider

Model-agnostic feature extraction. Produces numeric vectors reusable by classical ML and quantum models:

```python
from q_guardian.ml import MLFeatureProvider
from q_guardian.security.models import PromptFeatures

provider = MLFeatureProvider()
features = await provider.extract_features(prompt_text, base_features)
vector = features["feature_vector"]  # list[float]
```

### ThreatAnalysisPlugin

Generic orchestrator that combines:
1. Rule-based analysis (from Module 4)
2. Classical ML detection (registered detectors/classifiers)
3. Future quantum analysis (Module 6)

```python
from q_guardian.ml import ThreatAnalysisPlugin, MLConfig

config = MLConfig(enabled=True)
plugin = ThreatAnalysisPlugin(config=config)

# Register ML models
plugin.register_ml_detector(isolation_forest_detector)
plugin.register_ml_classifier(random_forest_classifier)

# Use with Guardian
guardian.register_plugin(plugin)
await guardian.start()
results = await guardian.scan_prompt(prompt)
```

## Detectors

### IsolationForestDetector

Anomaly detection using sklearn Isolation Forest. Detects prompts that deviate from normal patterns:

```python
from q_guardian.ml import IsolationForestDetector

detector = IsolationForestDetector(contamination=0.1)
detector.train(X_train)  # Unsupervised, no labels needed

result = await detector.detect(prompt, features)
# result.findings, result.risk_score, result.confidence
```

### RandomForestThreatClassifier

Multi-class threat classification:

```python
from q_guardian.ml import RandomForestThreatClassifier

classifier = RandomForestThreatClassifier(n_estimators=100)
classifier.train(X_train, y_train)  # Supervised

probabilities = await classifier.classify(prompt, features)
# {"benign": 0.1, "prompt_injection": 0.8, ...}
```

### XGBoostThreatClassifier

Optional gradient boosting classifier. Only available if xgboost is installed:

```python
from q_guardian.ml import XGBoostThreatClassifier

classifier = XGBoostThreatClassifier()
# Falls back gracefully if xgboost not installed
if classifier.is_available:
    classifier.train(X_train, y_train)
```

### EnsembleDetector

Weighted voting across multiple detectors:

```python
from q_guardian.ml import EnsembleDetector

ensemble = EnsembleDetector(
    detectors=[detector_a, detector_b],
    weights={"detector-a": 2.0, "detector-b": 1.0},
)
result = await ensemble.detect(prompt, features)
```

## Training

```python
from q_guardian.ml import ModelTrainer, ModelStorage

storage = ModelStorage(base_path="models/ml")
trainer = ModelTrainer(storage=storage)

# Train classifier
result = await trainer.train(classifier, X, y, feature_names=names)
print(result.metrics["accuracy"], result.cv_mean)

# Train anomaly detector (unsupervised)
result = await trainer.train_anomaly_detector(detector, X)
```

## Datasets

```python
from q_guardian.ml.datasets import CSVLoader, JSONLoader, HuggingFaceLoader

# CSV
loader = CSVLoader()
entries = await loader.load("data/training.csv")

# JSON/JSONL
loader = JSONLoader()
entries = await loader.load("data/training.json")

# Hugging Face (requires pip install q-guardian[datasets])
loader = HuggingFaceLoader()
entries = await loader.load("security-ai/prompt-injection", split="train")
```

## Evaluation

```python
from q_guardian.ml import BenchmarkMetrics, ResearchMetrics

metrics = BenchmarkMetrics()

# Classification metrics
result = metrics.compute_classification_metrics(y_true, y_pred)
print(result.accuracy, result.f1_score, result.auc_roc)

# Anomaly detection metrics
result = metrics.compute_anomaly_metrics(y_true_anomaly, y_pred_anomaly)
print(result["detection_rate"])

# Research metrics with severity weighting
research = ResearchMetrics()
result = research.compute_prompt_security_metrics(
    y_true, y_pred, y_true_severity, y_pred_severity
)
```

## Configuration

```python
from q_guardian.ml import MLConfig

config = MLConfig(
    enabled=True,
    anomaly_threshold=0.5,
    classification_threshold=0.5,
    model_storage_path="models/ml",
    default_cv_folds=5,
    random_state=42,
)
```

## Dependencies

```bash
# Core ML (required)
pip install q-guardian[ml]

# With XGBoost (optional)
pip install q-guardian[ml,ml-xgboost]

# With Hugging Face datasets (optional)
pip install q-guardian[ml,datasets]
```

## Module 6 Extension Point

To add a quantum model (e.g., QSVM):

1. Implement `BaseThreatModel` and `ThreatClassifier` ABCs
2. Register with `ThreatAnalysisPlugin.register_ml_detector()`
3. No changes needed to InferenceEngine or training pipeline

```python
from q_guardian.security.extensibility import ThreatClassifier

class QSVMModel(ThreatClassifier, BaseThreatModel):
    async def classify_quantum(self, prompt, features):
        # Quantum classification logic
        return DetectionResult(...)
```
