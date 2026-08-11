"""Configuration for the dataset preparation + training pipeline.

The pipeline deliberately reuses the framework's existing configuration
stack (pydantic) instead of introducing YAML. Configuration can be supplied
as a JSON file, a dict, or individual CLI flags. Dataset groups follow the
canonical data roles:

    TRAINING DATA                 -> ``datasets.train``
    VALIDATION DATA               -> ``datasets.validation``
    INTERNAL TEST DATA            -> ``datasets.test``
    EXTERNAL GENERALIZATION DATA  -> ``datasets.external_eval`` (never trained on)

Dataset ids are the stable ``dataset_id`` keys of ``DatasetRegistry``, not the
Hugging Face repository paths (see ``docs/19_Benchmark_Platform_Documentation.md``
for the id -> source mapping).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator

from q_guardian.evaluation.pipeline import DEFAULT_PROVIDER_WEIGHTS

# Default dataset groups (registry ids). Only public/token-less datasets are
# in the active train/validation/test pools; gated sources stay in
# ``external_eval`` so they never silently enter training.
DEFAULT_TRAIN_SOURCES: list[str] = ["deepset-prompt-injections", "dolly-benign"]
DEFAULT_VALIDATION_SOURCES: list[str] = ["deepset-prompt-injections"]
DEFAULT_TEST_SOURCES: list[str] = ["deepset-prompt-injections"]
DEFAULT_EXTERNAL_EVAL_SOURCES: list[str] = [
    "jbb-behaviors",
    "jailbreakbench-attacks",
    "wildjailbreak",
    "harmbench-behaviors",
    "advbench",
    "hex-phi",
    "pal",
    "agentdojo",
    "cyberseceval-prompt-injections",
]

# Per-dataset caps. ``None`` means "no cap". Caps are applied per source and
# never silently: every cap is recorded in the dataset manifest.
DEFAULT_CAPS: dict[str, int | None] = {
    "dolly-benign": 2000,
    "wildjailbreak": 5000,
}


class DatasetGroupConfig(BaseModel):
    """Which datasets feed which pool.

    A dataset may appear in several groups. When a source with official
    train/test splits appears in both ``train`` and ``test``, its official
    test-split rows go to the internal test pool and only the official
    train-split rows are used for training.
    """

    train: list[str] = Field(default_factory=lambda: list(DEFAULT_TRAIN_SOURCES))
    validation: list[str] = Field(default_factory=lambda: list(DEFAULT_VALIDATION_SOURCES))
    test: list[str] = Field(default_factory=lambda: list(DEFAULT_TEST_SOURCES))
    external_eval: list[str] = Field(default_factory=lambda: list(DEFAULT_EXTERNAL_EVAL_SOURCES))

    def all_ids(self) -> list[str]:
        """Return every configured dataset id (deduplicated, order-preserving)."""
        seen: set[str] = set()
        result: list[str] = []
        for group in (self.train, self.validation, self.test, self.external_eval):
            for dataset_id in group:
                if dataset_id not in seen:
                    seen.add(dataset_id)
                    result.append(dataset_id)
        return result


class DedupConfig(BaseModel):
    """Duplicate-detection settings.

    ``exact`` compares case-folded raw text; ``normalized`` compares
    Unicode/whitespace-normalized text so near-identical variants that differ
    only in whitespace or invisible characters are caught too.
    """

    enabled: bool = True
    exact: bool = True
    normalized: bool = True
    keep_first: bool = True


class ModelConfig(BaseModel):
    """Parameters forwarded to the existing ``HybridEvaluator`` pipeline.

    ``epochs`` / ``batch_size`` / ``learning_rate`` are accepted for CLI
    parity with neural trainers but the current hybrid pipeline is
    scikit-learn / quantum based, so they are recorded in run metadata and
    not applied to training (see documentation).
    """

    quantum: bool = False
    quantum_shots: int = 128
    quantum_feature_count: int = 5
    quantum_cap: int | None = None
    n_estimators: int = 50
    contamination: float = 0.2
    provider_weights: dict[str, float] | None = None
    epochs: int | None = None
    batch_size: int | None = None
    learning_rate: float | None = None


class EvalConfig(BaseModel):
    """Evaluation settings."""

    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    threshold_sweep: list[float] = Field(
        default_factory=lambda: [round(i / 10, 1) for i in range(1, 10)]
    )


class TrainingPipelineConfig(BaseModel):
    """Top-level configuration for the dataset + training pipeline."""

    datasets: DatasetGroupConfig = Field(default_factory=DatasetGroupConfig)
    caps: dict[str, int | None] = Field(default_factory=lambda: dict(DEFAULT_CAPS))
    seed: int = Field(default=42, description="Deterministic seed for splitting/dedup")
    validation_ratio: float = Field(
        default=0.2, ge=0.0, lt=1.0, description="Stratified validation fraction"
    )
    max_samples_per_class: int | None = Field(
        default=None,
        description="Optional cap on training samples kept per class",
    )
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    eval: EvalConfig = Field(default_factory=EvalConfig)
    output_dir: Path = Field(default=Path("artifacts/training"))
    hf_token: SecretStr | None = Field(
        default=None, description="Hugging Face token (prefer the HF_TOKEN env var)"
    )

    @field_validator("seed")
    @classmethod
    def _seed_in_range(cls, value: int) -> int:
        if value < 0:
            msg = f"seed must be >= 0, got {value}"
            raise ValueError(msg)
        return value

    @classmethod
    def from_file(cls, path: str | Path) -> TrainingPipelineConfig:
        """Load configuration from a JSON file."""
        config_path = Path(path)
        if not config_path.exists():
            msg = f"config file not found: {config_path}"
            raise FileNotFoundError(msg)
        with open(config_path, encoding="utf-8") as f:
            data: Any = json.load(f)
        return cls.model_validate(data)

    def evaluator_kwargs(self) -> dict[str, Any]:
        """Build the kwargs forwarded to ``HybridEvaluator``."""
        return {
            "quantum": self.model.quantum,
            "quantum_shots": self.model.quantum_shots,
            "quantum_feature_count": self.model.quantum_feature_count,
            "quantum_cap": self.model.quantum_cap,
            "n_estimators": self.model.n_estimators,
            "contamination": self.model.contamination,
            "provider_weights": self.model.provider_weights or dict(DEFAULT_PROVIDER_WEIGHTS),
            "random_state": self.seed,
        }

    def as_dict(self) -> dict[str, Any]:
        """Serializable config (used for ``training_config.json`` artifacts)."""
        data = self.model_dump(mode="json")
        if data.get("hf_token"):
            data["hf_token"] = "***"
        return data
