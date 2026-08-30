"""Dataset composition + contamination audit for the training-diversity experiment.

Loads the control splits and every candidate public dataset, and reports:
- composition (counts, mal/ben, language heuristic, source/domain, category)
- exact/near-duplicate contamination vs control train/val/test and held-out JBB
- substring containment of JBB behavior goals inside candidate prompts

Outputs: artifacts/experiments/training_diversity/dataset_composition.json
         artifacts/experiments/training_diversity/dataset_composition.md
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
RAW = Path(__file__).resolve().parent / "data_raw"
OUT = ROOT / "artifacts" / "experiments" / "training_diversity"
OUT.mkdir(parents=True, exist_ok=True)

_PUNCT = re.compile(r"[\s\W_]+", flags=re.UNICODE)

EN_STOP = {
    "the",
    "and",
    "is",
    "are",
    "a",
    "an",
    "to",
    "of",
    "for",
    "with",
    "that",
    "this",
    "you",
    "your",
}
DE_STOP = {
    "der",
    "die",
    "das",
    "und",
    "ist",
    "nicht",
    "ein",
    "eine",
    "ich",
    "du",
    "sie",
    "mit",
    "von",
    "den",
    "dem",
    "auf",
    "für",
    "sind",
    "im",
    "als",
    "bei",
}
FR_STOP = {"le", "la", "les", "des", "est", "et", "un", "une", "que", "qui", "pour", "dans", "avec"}
ES_STOP = {"el", "la", "los", "las", "es", "y", "un", "una", "que", "de", "para", "con", "por"}

NON_LATIN = re.compile(
    r"[^\u0000-\u024F\u0370-\u1FFF]"
)  # not basic latin / latin-ext / greek / cyrillic

_CYR = re.compile(r"[\u0400-\u04FF]")
_CJK = re.compile(r"[\u3000-\u9FFF\uAC00-\uD7AF\u3040-\u30FF]")
_ARABIC = re.compile(r"[\u0600-\u06FF]")


def normalize(text: str) -> str:
    t = text.lower().strip()
    t = _PUNCT.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def detect_lang(text: str) -> str:
    if not text or not text.strip():
        return "empty"
    low = text.lower()
    if _CYR.search(low):
        return "cyrillic"
    if _CJK.search(low):
        return "cjk"
    if _ARABIC.search(low):
        return "arabic"
    words = set(re.findall(r"[a-zäöüßéèêàç]+", low))
    if not words:
        return "other"
    scores = {
        "de": len(words & DE_STOP),
        "en": len(words & EN_STOP),
        "fr": len(words & FR_STOP),
        "es": len(words & ES_STOP),
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "latin-other"
    return best


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def shingles(text: str, k: int = 5) -> set[str]:
    n = normalize(text)
    if len(n) < k:
        return {n} if n else set()
    return {n[i : i + k] for i in range(len(n) - k + 1)}


class NearDupIndex:
    """Inverted shingle index over reference texts for fast near-duplicate lookup."""

    def __init__(self, texts: list[str], k: int = 5) -> None:
        self.ref_sets = [shingles(t, k) for t in texts]
        self.postings: dict[str, list[int]] = {}
        for i, s in enumerate(self.ref_sets):
            for sh in s:
                self.postings.setdefault(sh, []).append(i)

    def max_jaccard(self, text: str, k: int = 5) -> tuple[float, int]:
        s = shingles(text, k)
        if not s:
            return 0.0, -1
        cnt: collections.Counter = collections.Counter()
        for sh in s:
            for i in self.postings.get(sh, ()):
                cnt[i] += 1
        best, best_i = 0.0, -1
        for i, shared in cnt.items():
            j = shared / (len(s) + len(self.ref_sets[i]) - shared)
            if j > best:
                best, best_i = j, i
        return best, best_i


def substring_hit(text: str, refs: list[str]) -> tuple[bool, str]:
    """Check if any normalized reference text (>=10 chars) is a substring of text."""
    t = normalize(text)
    for ref in refs:
        r = normalize(ref)
        if len(r) >= 10 and r in t:
            return True, ref
    return False, ""


def main() -> None:
    splits = {}
    for name in ("train", "validation", "test", "external_eval"):
        splits[name] = load_jsonl(SPLITS / f"{name}.jsonl")

    eval_texts = (
        [r["text"] for r in splits["train"]]
        + [r["text"] for r in splits["validation"]]
        + [r["text"] for r in splits["test"]]
        + [r["text"] for r in splits["external_eval"]]
    )
    train_texts = [r["text"] for r in splits["train"]]
    jbb_goals = [r["text"] for r in splits["external_eval"] if r["label"] == 1]

    ref_sets = {
        "train": NearDupIndex([r["text"] for r in splits["train"]]),
        "validation": NearDupIndex([r["text"] for r in splits["validation"]]),
        "test": NearDupIndex([r["text"] for r in splits["test"]]),
        "jbb_eval": NearDupIndex([r["text"] for r in splits["external_eval"]]),
    }

    norm_eval = [normalize(t) for t in eval_texts]
    norm_eval_set = set(norm_eval)
    norm_train_set = set(normalize(t) for t in train_texts)

    datasets = {
        "deepset-prompt-injections": RAW
        / "prompt_injections.jsonl",  # note: this is data/prompt_injections.jsonl copy
        "trustair-jailbreaks": RAW / "trustair_jailbreaks.jsonl",
        "trustair-regular": RAW / "trustair_regular.jsonl",
        "jailbreakv": RAW / "jailbreakv.jsonl",
        "harmful-behaviors": RAW / "harmful_behaviors_train.jsonl",
        "harmful-behaviors-test": RAW / "harmful_behaviors_test.jsonl",
    }

    out: dict = {"control": {}, "datasets": {}, "contamination": {}}
    out["control"]["train"] = {
        "samples": len(splits["train"]),
        "benign": collections.Counter(r["label"] for r in splits["train"])[0],
        "malicious": collections.Counter(r["label"] for r in splits["train"])[1],
    }
    out["control"]["validation"] = {
        "samples": len(splits["validation"]),
        "benign": collections.Counter(r["label"] for r in splits["validation"])[0],
        "malicious": collections.Counter(r["label"] for r in splits["validation"])[1],
    }
    out["control"]["test"] = {
        "samples": len(splits["test"]),
        "benign": collections.Counter(r["label"] for r in splits["test"])[0],
        "malicious": collections.Counter(r["label"] for r in splits["test"])[1],
    }
    out["control"]["external_eval_jbb"] = {
        "samples": len(splits["external_eval"]),
        "benign": collections.Counter(r["label"] for r in splits["external_eval"])[0],
        "malicious": collections.Counter(r["label"] for r in splits["external_eval"])[1],
    }

    # deepset snapshot used as control component lives in data/prompt_injections.jsonl
    deepset_rows = load_jsonl(ROOT / "data" / "prompt_injections.jsonl")

    def audit(
        name: str, rows: list[dict], text_key: str, label_key: str | None, domain: str
    ) -> None:
        texts = [r[text_key] for r in rows]
        labels: list[int] = []
        if label_key is not None:
            for r in rows:
                v = r.get(label_key)
                labels.append(int(bool(v)))
        else:
            labels = [1] * len(rows)
        lang = collections.Counter(detect_lang(t) for t in texts)
        exact_in_eval = sum(1 for t in texts if normalize(t) in norm_eval_set)
        exact_in_train = sum(1 for t in texts if normalize(t) in norm_train_set)
        exact_within = 0
        seen = set()
        for t in texts:
            nt = normalize(t)
            if nt in seen:
                exact_within += 1
            seen.add(nt)
        near = {}
        for pool, idx in ref_sets.items():
            hits = 0
            worst = 0.0
            for t in texts:
                j, _ = idx.max_jaccard(t)
                worst = max(worst, j)
                if j >= 0.8:
                    hits += 1
            near[pool] = {"jaccard_ge_08": hits, "max_jaccard": round(worst, 3)}
        sub_hits = 0
        sub_examples: list[str] = []
        for t in texts:
            hit, ref = substring_hit(t, jbb_goals)
            if hit:
                sub_hits += 1
                if len(sub_examples) < 5:
                    sub_examples.append({"prompt": t[:120], "jbb_goal": ref[:120]})
        cat = collections.Counter()
        src = collections.Counter()
        for r in rows:
            if "source" in r:
                src[r["source"] or "unknown"] += 1
            if "category" in r:
                cat[r["category"] or "unknown"] += 1
            if "format" in r:
                cat[r["format"] or "unknown"] += 1
            if r.get("policy"):
                cat[r["policy"] + " (policy)"] += 1
        if not cat:
            cat["harmful-behavior"] = len(rows)
        if not src:
            src["unknown"] = len(rows)
        d = {
            "samples": len(rows),
            "malicious": int(sum(labels)),
            "benign": int(len(labels) - sum(labels)),
            "language_distribution": dict(lang.most_common()),
            "domain": domain,
            "top_sources": dict(src.most_common(5)),
            "categories": dict(cat.most_common(5)),
            "is_new_vs_baseline": True,
            "overlap": {
                "exact_match_in_any_eval_split": exact_in_eval,
                "exact_match_in_control_train": exact_in_train,
                "exact_duplicates_within": exact_within,
                "near_duplicates": near,
                "jbb_goal_substring_hits": sub_hits,
                "jbb_substring_examples": sub_examples[:3],
            },
        }
        out["datasets"][name] = d
        print(
            f"audited {name}: {len(rows)} samples, jbb-substr={sub_hits}, near-jbb={near['jbb_eval']['jaccard_ge_08']}"
        )

    audit("deepset-prompt-injections", deepset_rows, "text", "label", "prompt-injection (control)")
    audit(
        "trustair-jailbreaks",
        load_jsonl(datasets["trustair-jailbreaks"]),
        "prompt",
        "jailbreak",
        "in-the-wild jailbreak prompts",
    )
    audit(
        "trustair-regular",
        load_jsonl(datasets["trustair-regular"]),
        "prompt",
        "jailbreak",
        "in-the-wild regular prompts (benign)",
    )
    audit(
        "jailbreakv",
        load_jsonl(datasets["jailbreakv"]),
        "jailbreak_query",
        None,
        "JailbreakV-28K jailbreak prompts",
    )
    audit(
        "harmful-behaviors",
        load_jsonl(datasets["harmful-behaviors"]),
        "text",
        None,
        "harmful behavior requests (AdvBench-style)",
    )
    audit(
        "harmful-behaviors-test",
        load_jsonl(datasets["harmful-behaviors-test"]),
        "text",
        None,
        "harmful behavior requests (AdvBench-style)",
    )

    (OUT / "dataset_composition.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md = ["# Q-Guardian Training-Diversity: Dataset Composition & Contamination Audit", ""]
    md.append(
        "| Dataset | Samples | Malicious | Benign | Domain | Languages | New | Exact-in-eval | Near-dup>=0.8 (jbb) | JBB-substr |"
    )
    md.append("| --- | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: |")
    for name, d in out["datasets"].items():
        lang = ",".join(f"{k}:{v}" for k, v in list(d["language_distribution"].items())[:3])
        ov = d["overlap"]
        md.append(
            f"| {name} | {d['samples']} | {d['malicious']} | {d['benign']} | {d['domain']} | {lang} | "
            f"{'yes' if d['is_new_vs_baseline'] else 'no'} | {ov['exact_match_in_any_eval_split']} | "
            f"{ov['near_duplicates']['jbb_eval']['jaccard_ge_08']} | {ov['jbb_goal_substring_hits']} |"
        )
    md.append("")
    md.append("## Contamination details")
    for name, d in out["datasets"].items():
        ov = d["overlap"]
        md.append(
            f"- **{name}**: exact-in-eval={ov['exact_match_in_any_eval_split']}, exact-in-control-train={ov['exact_match_in_control_train']}, within={ov['exact_duplicates_within']}; near-dup (>=0.8): "
            + ", ".join(f"{p}={v['jaccard_ge_08']}" for p, v in ov["near_duplicates"].items())
            + f"; JBB substring hits={ov['jbb_goal_substring_hits']}"
        )
        for ex in ov["jbb_substring_examples"]:
            md.append(f"  - prompt: `{ex['prompt']}`")
            md.append(f"    goal: `{ex['jbb_goal']}`")
    (OUT / "dataset_composition.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("audit written")


if __name__ == "__main__":
    main()
