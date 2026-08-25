"""Build the FIXED representation (43 handcrafted + 384 all-MiniLM-L6-v2) for all
train arms and eval pools.

Reuses the previous semantic experiment's cached control/eval features
(artifacts/experiments/semantic_features/cache/features.npz) and encodes only
new texts. All transformations are per-text; the StandardScaler is fitted
separately at training time on the training fold only (see 05_run_experiment).

Outputs: artifacts/experiments/training_diversity/cache/{control,arm_a,...}.npz
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").CRITICAL)
)

from q_guardian.ml.feature_pipeline import MLFeatureProvider
from q_guardian.security.pipeline import PromptFeatureExtractor, PromptNormalizer

ROOT = Path(__file__).resolve().parent.parent.parent
TRAIN_SETS = Path(__file__).resolve().parent / "train_sets"
CACHE = ROOT / "artifacts" / "experiments" / "training_diversity" / "cache"
PREV_CACHE = ROOT / "artifacts" / "experiments" / "semantic_features" / "cache" / "features.npz"
CACHE.mkdir(parents=True, exist_ok=True)

ARMS = ["control", "arm_a", "arm_b", "arm_c", "arm_d"]
EVAL_POOLS = ["validation", "test", "jbb"]

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    prev = np.load(PREV_CACHE, allow_pickle=True)

    known: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for pool, arr43, arrEmb in (
        ("train", prev["train_x43"], prev["train_xemb"]),
        ("validation", prev["validation_x43"], prev["validation_xemb"]),
        ("test", prev["test_x43"], prev["test_xemb"]),
        ("jbb", prev["jbb_x43"], prev["jbb_xemb"]),
    ):
        texts = [str(t) for t in prev[f"{pool}_texts"].tolist()]
        for i, t in enumerate(texts):
            known[t] = (arr43[i].astype(np.float64), arrEmb[i].astype(np.float64))

    need: dict[str, list[str]] = {}
    eval_texts: dict[str, list[str]] = {}
    for arm in ARMS:
        need[arm] = [r["text"] for r in load_jsonl(TRAIN_SETS / f"{arm}.jsonl")]
    for pool in EVAL_POOLS:
        if pool == "validation":
            texts = [str(t) for t in prev["validation_texts"].tolist()]
        elif pool == "test":
            texts = [str(t) for t in prev["test_texts"].tolist()]
        else:
            texts = [str(t) for t in prev["jbb_texts"].tolist()]
        eval_texts[pool] = texts

    all_texts = set()
    for t in eval_texts.values():
        all_texts.update(t)
    for lst in need.values():
        all_texts.update(lst)

    to_encode = [t for t in sorted(all_texts) if t not in known]
    print(f"[features] {len(all_texts)} unique texts, {len(to_encode)} new to encode")

    if to_encode:
        print("[features] loading embedding model ...")
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(EMBEDDING_MODEL_NAME)

        print("[features] computing handcrafted 43-vectors ...")
        normalizer = PromptNormalizer()
        extractor = PromptFeatureExtractor()
        ml_features = MLFeatureProvider()
        x43s: list[np.ndarray] = []
        for i, t in enumerate(to_encode):
            norm = normalizer.normalize(t)
            base = extractor.extract(norm)
            vec = ml_features.extract_vector(norm, base).features
            x43s.append(np.asarray(vec, dtype=np.float64))
        x43_all = np.vstack(x43s)
        print("[features] encoding embeddings ...")
        emb_all = model.encode(
            to_encode, normalize_embeddings=True, batch_size=64, show_progress_bar=False
        )
        emb_all = np.asarray(emb_all, dtype=np.float64)
        for i, t in enumerate(to_encode):
            known[t] = (x43_all[i], emb_all[i])
        print("[features] encoded", len(to_encode))

    for arm in ARMS:
        texts = need[arm]
        x43 = np.vstack([known[t][0] for t in texts])
        xemb = np.vstack([known[t][1] for t in texts])
        np.savez_compressed(
            CACHE / f"{arm}.npz",
            texts=np.array(texts, dtype=object),
            x43=x43,
            xemb=xemb,
        )
        print(f"[features] cached {arm}: {len(texts)} rows x {x43.shape[1]}+{xemb.shape[1]}")

    for pool in EVAL_POOLS:
        texts = eval_texts[pool]
        x43 = np.vstack([known[t][0] for t in texts])
        xemb = np.vstack([known[t][1] for t in texts])
        np.savez_compressed(
            CACHE / f"{pool}.npz",
            texts=np.array(texts, dtype=object),
            x43=x43,
            xemb=xemb,
        )
        print(f"[features] cached {pool}: {len(texts)} rows")


if __name__ == "__main__":
    main()
