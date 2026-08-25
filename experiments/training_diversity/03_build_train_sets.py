"""Build CONTROL and DIVERSE training sets for the training-diversity experiment.

CONTROL  : deepset-prompt-injections + dolly-benign  (artifacts/training_xgboost_fix/splits/train.jsonl)
DIVERSE A: CONTROL + TrustAIR in-the-wild jailbreak prompts
DIVERSE B: CONTROL + JailbreakV-28K subset (2000, seed 42)
DIVERSE C: CONTROL + mlabonne/harmful_behaviors
DIVERSE D: CONTROL + A + B + C

All added malicious samples are filtered against eval contamination:
- exact normalized match against any eval split (train/val/test/jbb)
- near-duplicate (5-gram Jaccard >= 0.8) against val/test/jbb/control-train
- JBB behavior goal contained as substring

Outputs:
- experiments/training_diversity/train_sets/{control,arm_a,arm_b,arm_c,arm_d}.jsonl
- artifacts/experiments/training_diversity/train_sets_summary.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from _audit_utils import NearDupIndex, normalize

ROOT = Path(__file__).resolve().parent.parent.parent
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
RAW = Path(__file__).resolve().parent / "data_raw"
TRAIN_SETS = Path(__file__).resolve().parent / "train_sets"
OUT = ROOT / "artifacts" / "experiments" / "training_diversity"
OUT.mkdir(parents=True, exist_ok=True)
TRAIN_SETS.mkdir(parents=True, exist_ok=True)

JBBV_SUBSET = 2000
JBBV_SEED = 42


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def save_jsonl(rows: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class EvalFilter:
    """Excludes samples that overlap with any eval split (train/val/test/jbb)."""

    def __init__(self) -> None:
        self.ref_texts: dict[str, list[str]] = {}
        for name in ("train", "validation", "test", "external_eval"):
            rows = load_jsonl(SPLITS / f"{name}.jsonl")
            self.ref_texts[name] = [r["text"] for r in rows]
        self.norm_sets = {k: set(normalize(t) for t in v) for k, v in self.ref_texts.items()}
        self.indexes = {
            "train": NearDupIndex(self.ref_texts["train"]),
            "validation": NearDupIndex(self.ref_texts["validation"]),
            "test": NearDupIndex(self.ref_texts["test"]),
            "jbb": NearDupIndex(self.ref_texts["external_eval"]),
        }
        self.jbb_goals = [
            r["text"] for r in load_jsonl(SPLITS / "external_eval.jsonl") if r["label"] == 1
        ]

    def check(self, text: str) -> tuple[bool, str]:
        nt = normalize(text)
        for name, s in self.norm_sets.items():
            if nt in s:
                return True, f"exact-{name}"
        t = normalize(text)
        for goal in self.jbb_goals:
            rg = normalize(goal)
            if len(rg) >= 10 and rg in t:
                return True, "jbb-substring"
        for name, idx in self.indexes.items():
            j, _ = idx.max_jaccard(text)
            if j >= 0.8:
                return True, f"near-{name}"
        return False, ""


def clean(
    rows: list[dict],
    text_key: str,
    source: str,
    category_key: str | None = None,
    label: int = 1,
) -> tuple[list[dict], list[tuple[str, str]]]:
    filt = EvalFilter()
    kept: list[dict] = []
    dropped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for r in rows:
        text = r[text_key]
        if text in seen:
            dropped.append((text[:80], "within-dup"))
            continue
        seen.add(text)
        bad, reason = filt.check(text)
        if bad:
            dropped.append((text[:80], reason))
            continue
        cat = r.get(category_key) if category_key else None
        if isinstance(cat, dict):
            cat = json.dumps(cat, ensure_ascii=False)[:120]
        kept.append({"text": text, "label": label, "source": source, "category": cat or "unknown"})
    return kept, dropped


def main() -> None:
    control = load_jsonl(SPLITS / "train.jsonl")

    trustair = load_jsonl(RAW / "trustair_jailbreaks.jsonl")
    jailbreakv = load_jsonl(RAW / "jailbreakv.jsonl")
    harmful = load_jsonl(RAW / "harmful_behaviors_train.jsonl") + load_jsonl(
        RAW / "harmful_behaviors_test.jsonl"
    )

    trustair_clean, trustair_drop = clean(
        trustair, "prompt", "trustair-jailbreaks", category_key="source"
    )
    harmful_clean, harmful_drop = clean(harmful, "text", "harmful-behaviors", category_key=None)

    jv_clean, jv_drop = clean(jailbreakv, "jailbreak_query", "jailbreakv", category_key="policy")
    rng = random.Random(JBBV_SEED)
    jailbreakv_sub = rng.sample(jv_clean, min(JBBV_SUBSET, len(jv_clean)))
    jailbreakv_sub.sort(key=lambda r: r["text"])

    arms = {
        "control": [dict(r) for r in control],
        "arm_a": [dict(r) for r in control] + [dict(r) for r in trustair_clean],
        "arm_b": [dict(r) for r in control] + [dict(r) for r in jailbreakv_sub],
        "arm_c": [dict(r) for r in control] + [dict(r) for r in harmful_clean],
        "arm_d": [dict(r) for r in control]
        + [dict(r) for r in trustair_clean]
        + [dict(r) for r in jailbreakv_sub]
        + [dict(r) for r in harmful_clean],
    }

    summary = {
        "control_train_pool": "artifacts/training_xgboost_fix/splits/train.jsonl",
        "new_datasets": {
            "trustair-jailbreaks": {
                "downloaded": len(trustair),
                "kept": len(trustair_clean),
                "dropped": _count_reasons(trustair_drop),
            },
            "jailbreakv": {
                "downloaded": len(jailbreakv),
                "kept_clean": len(jv_clean),
                "dropped": _count_reasons(jv_drop),
                "subset_size": len(jailbreakv_sub),
                "subset_seed": JBBV_SEED,
                "note": "partial download (5900 of 28000, network flaky); random subset seeded",
            },
            "harmful-behaviors": {
                "downloaded": len(harmful),
                "kept": len(harmful_clean),
                "dropped": _count_reasons(harmful_drop),
            },
        },
        "arms": {},
    }

    for name, rows in arms.items():
        n_mal = sum(1 for r in rows if r["label"] == 1)
        n_ben = sum(1 for r in rows if r["label"] == 0)
        summary["arms"][name] = {
            "samples": len(rows),
            "malicious": n_mal,
            "benign": n_ben,
            "malicious_ratio": round(n_mal / len(rows), 4),
        }
        save_jsonl(rows, TRAIN_SETS / f"{name}.jsonl")

    (OUT / "train_sets_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _count_reasons(drops: list[tuple[str, str]]) -> dict[str, int]:
    c: dict[str, int] = {}
    for _, reason in drops:
        c[reason] = c.get(reason, 0) + 1
    return c


if __name__ == "__main__":
    main()
