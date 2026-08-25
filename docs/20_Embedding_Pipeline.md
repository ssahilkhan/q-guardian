# 20 - Embedding Pipeline (V2.0 M3)

> Companion doc for the Q-Guardrail documentation set. Documents the semantic
> embedding subsystem under `src/q_guardian/embeddings/`: provider interface,
> caching manager, feature-mode fusion, explainability, dependency-injected
> trainer adapters, and mode-comparison benchmarking.

---

## 1. Overview

The embeddings subsystem **extends** the handcrafted 43-feature detection
pipeline (see `19_Benchmark_Platform_Documentation.md`) with semantic
embeddings — it never modifies the completed pipeline. It adds a third,
selectable feature family alongside the handcrafted features:

| Mode (`FeatureMode`) | Feature set | Vector size |
|---|---|---|
| `handcrafted_only` | original 43 rule/statistical features | 43 |
| `embedding_only` | semantic embedding vector | 16 |
| `hybrid` | 43 handcrafted + 16 semantic features | 59 |

A single `EmbeddingManager` orchestrates providers: lazy loading, an in-memory
LRU cache with a JSON disk cache behind it, batching/chunking, and automatic
fallback to a secondary provider when the primary fails. Every embedding
call records explainability metadata (`EmbeddingMeta`) and trace latency stats
(`EmbeddingTrace`). Trainers reach the pipeline through DI adapters that accept
any model trainer, so the fused features can be trained without touching the
completed `ml/` and `quantum/` packages.

All modules live in `src/q_guardian/embeddings/` (12 modules, 226 tests).

## 2. Module Map

| Module | Responsibility |
|---|---|
| `base.py` | `EmbeddingProvider` ABC — load/unload lifecycle, `embed`/`embed_batch`, dimension, health, metadata, rolling latency window, load-guard on every embed |
| `errors.py` | Exception hierarchy: `EmbeddingError` -> `EmbeddingNotLoadedError`, `EmbeddingNotAvailableError`, `EmbeddingProviderError` |
| `providers/hasher.py` | `hash_vector` + `HashEmbeddingProvider` — dependency-free, deterministic, L2-normalized hash embedding (default offline provider) |
| `providers/sentence_transformers.py` | `MiniLMProvider`, `BGEProvider`, `E5Provider` — lazy-imported `sentence-transformers`, injectable `model_factory` for testing; missing library raises `EmbeddingNotAvailableError` |
| `providers/cloud.py` | `OpenAIEmbeddingProvider`, `AzureOpenAIEmbeddingProvider`, `VoyageAIEmbeddingProvider`, `CohereEmbeddingProvider` — placeholders with `implemented=False`; real calls raise `EmbeddingNotAvailableError` |
| `manager.py` | `EmbeddingManager` (registration, default/fallback, LRU + disk cache, batching), `EmbeddingCache` (JSON disk cache), `build_manager` factory |
| `explain.py` | `EmbeddingMeta` (frozen record), `EmbeddingTrace` (latency stats, unique providers/models, serialization) |
| `fusion.py` | `FeatureMode` (StrEnum), `ModeFeatureExtractor` (43/16/59-dim vectors + feature names, handcrafted parity with `HybridEvaluator`), `EmbeddingFeatureProvider` (per-mode `FeatureProvider`), `ModeHybridEvaluator` |
| `integration.py` | `ModeTrainingAdapter`, `ModeQuantumAdapter` — feed fused mode features into any `ModelTrainer` / `QuantumTrainer` |
| `benchmark.py` | `ModeDetectionBenchmark`, `ModeComparisonReport`, `ModeComparisonRunner`, `benchmark_handcrafted_vs_embeddings`, `run_all` |

## 3. Errors (`errors.py`)

```
EmbeddingError
├── EmbeddingNotLoadedError   provider not loaded (call load() first)
├── EmbeddingNotAvailableError  provider/lib unimplemented (cloud placeholders, missing package)
└── EmbeddingProviderError    provider-internal failures
```

All subclasses are catchable as `EmbeddingError`, and the hierarchy is
exercised by `tests/unit/test_embeddings_errors.py`.

## 4. Providers (`base.py`, `providers/`)

### 4.1 `EmbeddingProvider` ABC

```python
class EmbeddingProvider(ABC):
    def __init__(self, *, latency_window: int = 64) -> None: ...
    @property name / model_id / backend / requires_token / is_loaded
    def load(self) -> None: ...
    def unload(self) -> None: ...
    def dimension(self) -> int: ...
    def health(self) -> bool: ...
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
    def metadata(self) -> dict[str, Any]: ...
    def average_latency_ms(self) -> float: ...
```

- `embed`/`embed_batch` are final public entry points: they run the load-guard
  (`_require_loaded` raises `EmbeddingNotLoadedError` when not loaded), time the
  call, feed the rolling latency window, and delegate to the protected
  `_embed_impl`/`_embed_batch_impl`. Subclasses implement the `_impl` methods.
- `load()`/`unload()` are idempotent; loading is lazy via the manager.

### 4.2 `HashEmbeddingProvider` (default, no dependencies)

`hash_vector(text, dimension, seed=42)` produces a deterministic, L2-normalized
vector from a seeded hash of the text. `HashEmbeddingProvider` exposes it behind
the ABC with `backend = "hash"`, dimension 16 by default. Used as the built-in
default when no provider is configured, so the pipeline runs out of the box.

### 4.3 Sentence-transformers providers

`MiniLMProvider`, `BGEProvider`, `E5Provider` (`model_id` e.g.
`all-MiniLM-L6-v2`, `BAAI/bge-base-en-v1.5`, `intfloat/e5-base-v2`) lazily import
`sentence_transformers` inside `load()`. If the package is missing, `load()`
raises `EmbeddingNotAvailableError`. The model is built via `_build_model()` —
injectable `model_factory` in the constructor for unit tests (see
`test_embeddings_providers.py`, which uses a fake sentence model).

### 4.4 Cloud placeholders

`CloudEmbeddingProvider` subclasses (`OpenAI`, `Azure OpenAI`, `VoyageAI`,
`Cohere`) declare their model/backend/env var and `load()` accepts an `api_key`,
but `_embed_impl`/`_embed_batch_impl` raise `EmbeddingNotAvailableError` —
`metadata()["implemented"] == False`. They are a safe integration seam for
later API backends; tests confirm the load-guard fires before the
not-available error.

## 5. Manager & Caching (`manager.py`)

### 5.1 `EmbeddingManager`

```python
mgr = EmbeddingManager(cache_size=..., batch_size=32, cache_dir=Path|None)
mgr.register(provider)            # pid = provider.name; duplicates -> EmbeddingError
mgr.register_all([...])           # aliases allowed
mgr.unregister(provider_id)       # re-selects default from remaining providers
mgr.select(provider_id)           # set default
mgr.set_fallback(provider_id)     # fallback provider for failures
mgr.provider_ids(); mgr.default_provider_id; mgr.default_provider
mgr.embed(text, provider_id=None)
mgr.embed_with_meta(text, provider_id=None) -> (vector, EmbeddingMeta)
mgr.embed_batch(texts, provider_id=None, batch_size=None)
mgr.embed_batch_with_meta(texts, ...) -> (vectors, list[EmbeddingMeta])
mgr.dimension(provider_id=None); mgr.metadata(provider_id=None)
mgr.health(); mgr.stats(); mgr.cached_count(); mgr.cache_stats()
mgr.fallback_events(); mgr.fallback_count(); mgr.clear_cache(); mgr.unload_all()
```

- **Lazy loading**: a provider is loaded on first embed and stays loaded.
- **Cache**: per-provider, text-keyed. In-memory LRU (`cache_size` entries);
  disk persistence via `EmbeddingCache` (JSON files under `cache_dir`). The
  read-through `_retrieve` checks memory first, then promotes a disk hit into
  memory, so `cached_count()` reflects the working set and disk cache persists
  across manager instances.
- **Batching**: batches are chunked by `batch_size` and cache writes are
  batched; batch hits are detected via the cache (later duplicates in one batch
  are cached hits).
- **Fallback**: if the default (or requested) provider raises on an embed, the
  manager falls back to the fallback provider and records the event
  (`fallback_events()`, `fallback_count()`). In batch mode the whole chunk
  retries on the fallback.

### 5.2 `build_manager` factory

```python
manager = build_manager(
    default_provider=...,  # e.g. SentenceTransformersProvider(model_factory=...)
    fallback_provider=...,  # e.g. HashEmbeddingProvider()
    providers=[...],  # extra providers
    cache_dir=...,  # optional disk cache
)
```

Guarantees at least one provider (a `HashEmbeddingProvider` when none is
supplied), selects `default_provider` (or the first) as default, and wires the
fallback.

## 6. Explainability (`explain.py`)

`EmbeddingMeta` (frozen dataclass) captures one embed: `text`, `provider_id`,
`model_id`, `backend`, `dimension`, `latency_ms`, `cached`, `timestamp`, plus
`to_dict()`/`from_dict()` (round-trip safe) and `is_cache_hit`.

`EmbeddingTrace` accumulates metas and computes latency stats, ignoring cached
hits: `count`, `providers()`, `models()`, `latency_stats()` (min/mean/max/p95
in ms), `to_dict()`, `clear()`. The p95 quantile is 0.9 by default.

## 7. Fusion (`fusion.py`)

`FeatureMode(StrEnum)`: `handcrafted_only`, `embedding_only`, `hybrid`;
strings are coerced automatically (`_coerce`).

`ModeFeatureExtractor`:
- `handcrafted_vector(text)` / `handcrafted_names()` — delegates to the
  completed `HybridEvaluator` pipeline, so embedding features are provably
  identical to the handcrafted path (43 dims).
- `embedding_vector(text)` / `embedding_dim()` — through the `EmbeddingManager`
  (16 dims).
- `vector(text, mode=None)` / `vectors(texts, mode=None)` / `feature_names(mode=None)`
  — mode-resolved feature assembly (43/16/59).
- `embedding_metadata()` — provider/model/dimension info for provenance.

`EmbeddingFeatureProvider(FeatureProvider)` adapts the extractor to the
completed feature-provider contract for a fixed mode. `ModeHybridEvaluator`
(extends `HybridEvaluator`) lets a single evaluator serve any mode via
`vector(text)`.

## 8. Trainer Adapters (`integration.py`)

- `ModeTrainingAdapter` — takes a `ModeFeatureExtractor` and any `ModelTrainer`;
  `extract()` builds the training matrix + feature names from `ModeFeatureExtractor`
  and `train(...)` forwards them to the trainer (anomaly-detection path uses the
  raw matrix). `trainer`/`extractor` are exposed for tests.
- `ModeQuantumAdapter` — same shape for `QuantumTrainer`, forwarding the
  mode-fused vectors (with optional labels) to the quantum training loop.

Neither adapter imports or modifies `ml/` or `quantum/` internals beyond their
public trainer contracts; tests inject `_FakeModelTrainer` / `_FakeQuantumTrainer`
to verify matrix/names/kwargs forwarding.

## 9. Benchmarking & Mode Comparison (`benchmark.py`)

`ModeDetectionBenchmark` (extends the evaluation `DetectionBenchmark`) runs
K-fold CV with a `ModeHybridEvaluator` for a given mode, producing per-fold
metrics, out-of-fold scores, and optional ablation. Raw metric aggregations
use `_fmean_or_zero` / `_stdev_or_zero` to stay NaN-safe.

`ModeComparisonReport`:
- `winner` — the mode with the best mean ROC AUC (hand-tuned tie-break to
  prefer fewer features);
- `as_dict()` — `{comparison, dataset, modes, recommendation, validation}`;
- `as_benchmark_reports()` — individual `DetectionBenchmarkReport`s per mode;
- `recommendation` — a human-readable sentence naming the winner and its edge.

`ModeComparisonRunner` reuses the **completed** benchmark package's ingestion
components (registry/downloader/validator/preprocessor) via dependency
injection, then runs `ModeDetectionBenchmark` per mode on identical folds:

```python
report = ModeComparisonRunner().run(
    "dataset_id",
    modes=["handcrafted_only", "embedding_only", "hybrid"],
    k=5,
    seed=42,
    threshold=0.5,
    ablate=False,
)
```

Also exposed: `benchmark_handcrafted_vs_embeddings(dataset_id, k, seed)` and
`run_all(dataset_ids=None, ...)`.

### Reference run (local fixture dataset, 8 benign + 8 jailbreak prompts)

| Mode | Mean ROC AUC |
|---|---|
| handcrafted | 0.95 |
| hybrid | 0.9208 |
| embedding | 0.8104 |

Winner: `handcrafted` (hybrid wins when embedding features add measurable AUC).

## 10. Quick Start

```python
from q_guardian.embeddings import build_manager
from q_guardian.embeddings.providers import HashEmbeddingProvider

manager = build_manager(default_provider=HashEmbeddingProvider())
vector, meta = manager.embed_with_meta("prompt under inspection")
assert meta.cached is False
vector2, meta2 = manager.embed_with_meta("prompt under inspection")
assert meta2.cached is True  # LRU hit
assert manager.cache_stats()["hits"] == 1
```

For a provider-backed run use
`sentence_transformers` (`MiniLMProvider`) as default with
`HashEmbeddingProvider` as fallback, and point `cache_dir` at a persistent
directory to keep vectors across restarts.

## 11. Tests (`tests/unit/test_embeddings_*.py`, 10 files, 226 tests)

| File | Subject | Count |
|---|---|---|
| `test_embeddings_errors.py` | exception hierarchy | 7 |
| `test_embeddings_hasher.py` | `hash_vector` + `HashEmbeddingProvider` | 22 |
| `test_embeddings_base.py` | `EmbeddingProvider` ABC + stub | 18 |
| `test_embeddings_providers.py` | sentence-transformers (fake model factory) + cloud placeholders | 27 |
| `test_embeddings_cache.py` | `EmbeddingCache` disk round-trip/corruption | 12 |
| `test_embeddings_manager.py` | registration, LRU + disk cache, batching, fallback | 52 |
| `test_embeddings_explain.py` | `EmbeddingMeta` / `EmbeddingTrace` | 16 |
| `test_embeddings_fusion.py` | `FeatureMode`, extractors, `ModeHybridEvaluator` parity | 35 |
| `test_embeddings_integration.py` | trainer/quantum adapters | 9 |
| `test_embeddings_benchmark.py` | benchmark + comparison + runner end-to-end | 28 |

All unit tests pass in ~11 s; `pytest tests` (whole suite) reports
**2,650 passed** with no failures. `ruff check` and `mypy` (strict) are clean.

## 12. Known Limits & Next Steps

- Cloud providers (OpenAI/Azure/Voyage/Cohere) are `implemented=False`
  placeholders — real HTTP clients are future work.
- `SentenceTransformersProvider` requires the optional `sentence-transformers`
  dependency at runtime; missing it degrades to `EmbeddingNotAvailableError`
  (hasher keeps the pipeline functional).
- No module under `embeddings/` modifies the completed `ml/`, `quantum/`,
  `evaluation/`, or `benchmark/` packages; the interface was extended by
  subclassing and dependency injection only.
