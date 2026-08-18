"""Shared experiment helpers (root-cause research).

Loads the frozen baseline checkpoint and prepared splits, scores every pool
exactly once, and caches the continuous threat scores so that later phases
reuse identical numbers instead of re-scoring.

Scoring is deterministic (frozen checkpoint), so the cache is safe to reuse.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import structlog

from q_guardian.evaluation.dataset import PromptBenchmarkDataset
from q_guardian.evaluation.pipeline import HybridEvaluator

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT = ROOT / "artifacts/training/model"
SPLITS = ROOT / "artifacts/training/splits"
SCORE_DIR = ROOT / "artifacts/experiments/_scores"

PROVIDER_IDS = ("rule-engine", "isolation-forest", "random-forest", "fusion")


def silence_logging() -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
    )


def load_pools() -> dict[str, PromptBenchmarkDataset]:
    return {
        "validation": PromptBenchmarkDataset.from_jsonl(SPLITS / "validation.jsonl"),
        "test": PromptBenchmarkDataset.from_jsonl(SPLITS / "test.jsonl"),
        "external_jbb": PromptBenchmarkDataset.from_jsonl(SPLITS / "external_eval.jsonl"),
    }


def score_pools() -> dict[str, list[dict]]:
    """Score every pool once with the frozen checkpoint and cache results."""
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    evaluator = HybridEvaluator.load_state(CHECKPOINT)
    pools = load_pools()
    cached: dict[str, list[dict]] = {}
    for name, ds in pools.items():
        cache_path = SCORE_DIR / f"fusion_{name}.json"
        if cache_path.exists():
            cached[name] = json.loads(cache_path.read_text(encoding="utf-8"))
            continue
        texts = ds.texts()
        labels = ds.labels()
        categories = ds.categories()
        scores = evaluator.score_texts(texts)
        cached[name] = [
            {"text": t, "label": l, "category": c, "score": s}
            for t, l, c, s in zip(texts, labels, categories, scores, strict=True)
        ]
        cache_path.write_text(
            json.dumps(cached[name], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return cached


def score_provider_pools() -> dict[str, list[dict]]:
    """Score every pool once with all providers exposed per sample.

    One ``evaluate()`` call per pool yields per-provider risk scores plus the
    fused score for every sample (deterministic, frozen checkpoint). Cached so
    model-ablation / error-analysis / fusion phases reuse identical numbers.
    """
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    evaluator = HybridEvaluator.load_state(CHECKPOINT)
    pools = load_pools()
    cached: dict[str, list[dict]] = {}
    for name, ds in pools.items():
        cache_path = SCORE_DIR / f"providers_{name}.json"
        if cache_path.exists():
            cached[name] = json.loads(cache_path.read_text(encoding="utf-8"))
            continue
        result = evaluator.evaluate(ds, threshold=0.5)
        rows = []
        for row in result["scores"]:
            entry = {"text": row["text"], "label": row["label"]}
            for pid in PROVIDER_IDS:
                entry[pid] = row.get(pid, 0.0)
            rows.append(entry)
        cached[name] = rows
        cache_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return cached


def provider_scores(pool: str) -> tuple[list[float], ...]:
    """Return (rule, if, rf, fusion) score lists for a pool from the cache."""
    rows = score_provider_pools()[pool]
    return tuple(
        [float(r[pid]) for r in rows] for pid in ("rule-engine", "isolation-forest", "random-forest", "fusion")
    )
