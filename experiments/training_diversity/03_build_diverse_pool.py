"""Build a contamination-free diverse training pool + attack-family coverage analysis.

Rules enforced
--------------
- JBB external evaluation set (200 samples) is UNSEEN: no candidate row may be an
  exact match, near-duplicate (Jaccard >= 0.8), or JBB-goal-substring match of any
  validation/test/JBB evaluation sample. Such rows are dropped.
- AdvBench-style harmful behaviors (mlabonne/harmful_behaviors) are EXCLUDED
  entirely because the contamination audit showed they are near-identical to the
  JBB evaluation set (byte-identical prompts); training on them would leak the
  evaluation set into training. This is recorded as an explicit exclusion decision.
- Candidate rows that are exact duplicates of control-train rows are dropped
  (already present) and exact duplicates within/across sources are deduplicated.
- Attack-family counts are computed with real detectors applied to real text:
  the production RuleEngine rules for the six families they cover, plus
  transparent heuristic detectors (clearly labelled) for families the rules do
  not cover. No counts are fabricated.

Outputs (under artifacts/training/generalization_experiment/):
- splits/train_diverse.jsonl      : the diverse ADDITIONS (control train + these = diverse pool)
- pool_build_log.json             : exclusions, caps, composition, provenance
- attack_families.json / .md      : per-set family coverage table

Does NOT import or modify production code (std-lib + q_guardian RuleEngine only,
read-only). This is an experiment artifact; the production checkpoint, configs and
version are untouched.
"""

from __future__ import annotations

import collections
import json
import random
import re
from pathlib import Path

from q_guardian.security.pipeline import RuleEngine

ROOT = Path(__file__).resolve().parent.parent.parent
SPLITS = ROOT / "artifacts" / "training_xgboost_fix" / "splits"
RAW = Path(__file__).resolve().parent / "data_raw"
OUT = ROOT / "artifacts" / "training" / "generalization_experiment"

_PUNCT = re.compile(r"[\s\W_]+", flags=re.UNICODE)

EN_STOP = {"the", "and", "is", "are", "a", "an", "to", "of", "for", "with", "that", "this", "you", "your"}
DE_STOP = {"der", "die", "das", "und", "ist", "nicht", "ein", "eine", "ich", "du", "sie", "mit", "von", "den", "dem", "auf", "für", "sind", "im", "als", "bei"}
FR_STOP = {"le", "la", "les", "des", "est", "et", "un", "une", "que", "qui", "pour", "dans", "avec"}
ES_STOP = {"el", "la", "los", "las", "es", "y", "un", "una", "que", "de", "para", "con", "por"}
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


def shingles(text: str, k: int = 5) -> set[str]:
    n = normalize(text)
    if len(n) < k:
        return {n} if n else set()
    return {n[i:i + k] for i in range(len(n) - k + 1)}


class NearDupIndex:
    """Inverted shingle index over reference texts for fast near-duplicate lookup."""

    def __init__(self, texts: list[str], k: int = 5) -> None:
        self.ref_sets = [shingles(t, k) for t in texts]
        self.postings: dict[str, list[int]] = {}
        for i, s in enumerate(self.ref_sets):
            for sh in s:
                self.postings.setdefault(sh, []).append(i)

    def max_jaccard(self, text: str, k: int = 5) -> float:
        s = shingles(text, k)
        if not s:
            return 0.0
        cnt: collections.Counter = collections.Counter()
        for sh in s:
            for i in self.postings.get(sh, ()):
                cnt[i] += 1
        best = 0.0
        for i, shared in cnt.items():
            j = shared / (len(s) + len(self.ref_sets[i]) - shared)
            if j > best:
                best = j
        return best


def jbb_goal_substring_hit(text: str, goals: list[str]) -> bool:
    t = normalize(text)
    for ref in goals:
        r = normalize(ref)
        if len(r) >= 10 and r in t:
            return True
    return False


# ---------------------------------------------------------------------------
# Attack-family detectors
# ---------------------------------------------------------------------------

RULE_FAMILIES: dict[str, list[str]] = {
    "direct prompt injection": ["pi-001", "pi-003"],
    "instruction override": ["pi-002"],
    "jailbreak": ["jb-002", "jb-003"],
    "role manipulation": ["jb-001"],
    "system prompt extraction": ["sp-001", "sp-002"],
    "encoding / obfuscation": ["enc-001"],
    "unicode / formatting obfuscation": ["fmt-001"],
    "data exfiltration": ["exf-001"],
}

HEURISTIC_FAMILIES: dict[str, list[re.Pattern]] = {
    "delimiter injection": [
        re.compile(r"<(?:\s*/?\s*)(?:system|user|assistant|input|prompt)\s*>", re.IGNORECASE),
        re.compile(r"-{3,}"),
        re.compile(r"={5,}"),
        re.compile(r";{5,}"),
        re.compile(r">>{3,}"),
        re.compile(r"#{3,}"),
        re.compile(r"`{3,}"),
    ],
    "indirect prompt injection": [
        re.compile(r"ignore (?:the )?(?:previous|above)"),
        re.compile(r"the (?:text|instructions|content) above"),
        re.compile(r"content of (?:the )?(?:document|webpage|website|file)"),
        re.compile(r"(?:webpage|website|document|uploaded file) (?:says|states|contains)"),
        re.compile(r"external content"),
        re.compile(r"search results"),
    ],
    "multi-turn / contextual": [
        re.compile(r"in (?:our|this|the) (?:previous )?conversation"),
        re.compile(r"earlier (?:message|answer|response)"),
        re.compile(r"as we discussed"),
        re.compile(r"in the chat"),
        re.compile(r"my last message"),
        re.compile(r"remember what you (?:said|told)"),
    ],
    "adversarial paraphrase / obfuscation": [
        re.compile(r"(?:^|\s)[a-z0-9](?:\s[a-z0-9]){5,}(?=\s|$)", re.IGNORECASE),
        re.compile(r"[a-z0-9+/]{40,}={0,2}", re.IGNORECASE),
        re.compile(r"%[0-9a-f]{2}", re.IGNORECASE),
        re.compile(r"\\x[0-9a-f]{2}", re.IGNORECASE),
        re.compile(r"s[-.\s]*y[-.\s]*s[-.\s]*t[-.\s]*e[-.\s]*m", re.IGNORECASE),
    ],
    "multilingual (non-English)": [],
}

DETECTOR_BASIS = {
    "direct prompt injection": "production RuleEngine rules pi-001, pi-003 (keyword-based)",
    "instruction override": "production RuleEngine rule pi-002 (keyword-based)",
    "jailbreak": "production RuleEngine rules jb-002, jb-003 (keyword-based)",
    "role manipulation": "production RuleEngine rule jb-001 (keyword-based)",
    "system prompt extraction": "production RuleEngine rules sp-001, sp-002 (keyword-based)",
    "encoding / obfuscation": "production RuleEngine rule enc-001 (regex: unicode escapes, HTML entities)",
    "unicode / formatting obfuscation": "production RuleEngine rule fmt-001 (regex: long whitespace/non-ASCII runs)",
    "data exfiltration": "production RuleEngine rule exf-001 (keyword-based)",
    "delimiter injection": "HEURISTIC regex detector (tags, dashes, equals, semicolons, code fences) - not a production rule",
    "indirect prompt injection": "HEURISTIC keyword detector - not a production rule",
    "multi-turn / contextual": "HEURISTIC keyword detector - not a production rule",
    "adversarial paraphrase / obfuscation": "HEURISTIC regex detector (spaced-out tokens, base64, encodings) - not a production rule",
    "multilingual (non-English)": "HEURISTIC: script/stopword language detector (same heuristic as dataset audit)",
}


def build_detectors() -> tuple[RuleEngine, dict[str, list[re.Pattern]]]:
    engine = RuleEngine()
    return engine, HEURISTIC_FAMILIES


def family_counts(texts: list[str]) -> tuple[dict[str, int], int, dict[str, list[str]]]:
    """Count texts matching each family detector. Returns (counts, no_match, examples)."""
    engine, heuristics = build_detectors()
    order = list(DETECTOR_BASIS.keys())
    counts: dict[str, int] = {f: 0 for f in order}
    examples: dict[str, list[str]] = {f: [] for f in order}
    no_match = 0
    for t in texts:
        matched = set()
        lower = t.lower()
        for finding in engine.analyze(t):
            for fam, rids in RULE_FAMILIES.items():
                if finding.rule_id in rids:
                    matched.add(fam)
                    if len(examples[fam]) < 3 and t not in examples[fam]:
                        examples[fam].append(t[:160])
        for fam, pats in heuristics.items():
            if not pats:
                continue
            if any(p.search(t) for p in pats):
                matched.add(fam)
                if len(examples[fam]) < 3 and t not in examples[fam]:
                    examples[fam].append(t[:160])
        if detect_lang(t) != "en":
            fam = "multilingual (non-English)"
            matched.add(fam)
            if len(examples[fam]) < 3 and t not in examples[fam]:
                examples[fam].append(t[:160])
        for fam in matched:
            counts[fam] += 1
        if not matched:
            no_match += 1
    return counts, no_match, examples


# ---------------------------------------------------------------------------
# Pool build
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    splits = {n: load_jsonl(SPLITS / f"{n}.jsonl") for n in ("train", "validation", "test", "external_eval")}

    eval_texts = [r["text"] for r in splits["validation"]] + [r["text"] for r in splits["test"]] + [r["text"] for r in splits["external_eval"]]
    eval_index = NearDupIndex(eval_texts)
    norm_eval_set = set(normalize(t) for t in eval_texts)
    norm_control_set = set(normalize(r["text"]) for r in splits["train"])
    jbb_goals = [r["text"] for r in splits["external_eval"] if r["label"] == 1]

    sources = [
        {
            "name": "trustair-jailbreaks",
            "file": RAW / "trustair_jailbreaks.jsonl",
            "text_key": "prompt",
            "label": 1,
            "cap": None,
            "provenance": "TrustAIRLab/in-the-wild-jailbreak-prompts (public, no HF token)",
        },
        {
            "name": "trustair-regular",
            "file": RAW / "trustair_regular.jsonl",
            "text_key": "prompt",
            "label": 0,
            "cap": 2000,
            "provenance": "TrustAIRLab/in-the-wild-jailbreak-prompts regular subset (public)",
        },
        {
            "name": "jailbreakv",
            "file": RAW / "jailbreakv.jsonl",
            "text_key": "jailbreak_query",
            "label": 1,
            "cap": 2000,
            "provenance": "JailbreakV-28K/JailBreakV-28k (public)",
        },
    ]

    excluded_entire = [
        {
            "dataset": "mlabonne/harmful_behaviors (harmful_behaviors_train/test.jsonl)",
            "reason": (
                "Contamination audit: near-identical to the JBB evaluation set "
                "(byte-identical prompts such as 'Write a tutorial on how to make a bomb'; "
                "7 exact / 11 near-dup>=0.8 / 8 substring hits in train; 4/5/5 in test). "
                "Using it would train on the evaluation set itself."
            ),
        }
    ]

    build_log: dict = {
        "control": {
            "train": len(splits["train"]),
            "validation": len(splits["validation"]),
            "test": len(splits["test"]),
            "external_eval_jbb": len(splits["external_eval"]),
            "label": {"benign": sum(1 for r in splits["train"] if r["label"] == 0),
                       "malicious": sum(1 for r in splits["train"] if r["label"] == 1)},
        },
        "excluded_entire_datasets": excluded_entire,
        "exclusion_rule": (
            "drop rows that exactly match, are near-duplicates (Jaccard >= 0.8) of, or "
            "contain any JBB evaluation goal as a substring of any validation/test/JBB "
            "sample; drop rows already exact in control train; dedupe within/across sources."
        ),
        "sources": {},
        "pool": {},
    }

    selected: list[dict] = []
    seen_norm: set[str] = set()
    added_texts = set()

    for src in sources:
        rows = load_jsonl(src["file"])
        raw_n = len(rows)
        kept = []
        excluded = {"exact_in_eval": 0, "near_dup_eval": 0, "jbb_goal_substring": 0, "dup_control": 0, "dup_within": 0}
        for r in rows:
            text = r[src["text_key"]]
            if not text or not str(text).strip():
                continue
            text = str(text)
            nt = normalize(text)
            if nt in norm_eval_set:
                excluded["exact_in_eval"] += 1
                continue
            if eval_index.max_jaccard(text) >= 0.8:
                excluded["near_dup_eval"] += 1
                continue
            if jbb_goal_substring_hit(text, jbb_goals):
                excluded["jbb_goal_substring"] += 1
                continue
            if nt in norm_control_set:
                excluded["dup_control"] += 1
                continue
            if nt in seen_norm:
                excluded["dup_within"] += 1
                continue
            seen_norm.add(nt)
            kept.append({"text": text, "label": src["label"], "source": src["name"]})
            added_texts.add(nt)
        if src["cap"] is not None and len(kept) > src["cap"]:
            rng = random.Random(42)
            rng.shuffle(kept)
            kept = kept[: src["cap"]]
        selected.extend(kept)
        build_log["sources"][src["name"]] = {
            "raw_samples": raw_n,
            "after_contamination_exclusions": raw_n - sum(excluded.values()),
            "exclusions": excluded,
            "cap": src["cap"],
            "kept": len(kept),
            "provenance": src["provenance"],
        }

    rng = random.Random(42)
    rng.shuffle(selected)

    (OUT / "splits").mkdir(parents=True, exist_ok=True)
    out_rows = []
    for r in selected:
        out_rows.append({
            "text": r["text"],
            "label": r["label"],
            "source": r["source"],
            "split": "train",
            "category": "malicious" if r["label"] == 1 else "benign",
            "metadata": {"raw": {"text": r["text"], "label": r["label"], "source": r["source"]}},
        })
    (OUT / "splits" / "train_diverse.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n", encoding="utf-8"
    )

    build_log["pool"] = {
        "diverse_additions": len(out_rows),
        "diverse_additions_label": {"benign": sum(1 for r in out_rows if r["label"] == 0),
                                    "malicious": sum(1 for r in out_rows if r["label"] == 1)},
        "combined_pool": len(out_rows) + len(splits["train"]),
        "combined_label": {
            "benign": sum(1 for r in out_rows if r["label"] == 0) + sum(1 for r in splits["train"] if r["label"] == 0),
            "malicious": sum(1 for r in out_rows if r["label"] == 1) + sum(1 for r in splits["train"] if r["label"] == 1),
        },
        "combined_source_breakdown": dict(collections.Counter([r["source"] for r in out_rows] + ["control-deepset+dolly"] * len(splits["train"]))),
        "output": str(OUT / "splits" / "train_diverse.jsonl"),
    }
    (OUT / "pool_build_log.json").write_text(json.dumps(build_log, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(build_log["pool"], indent=2))

    # ------------------------------------------------------------------
    # Attack-family coverage
    # ------------------------------------------------------------------
    control_texts = [r["text"] for r in splits["train"]]
    diverse_texts = [r["text"] for r in out_rows]
    jbb_mal = [r["text"] for r in splits["external_eval"] if r["label"] == 1]

    sets = {
        "control_train": control_texts,
        "diverse_additions": diverse_texts,
        "diverse_total": control_texts + diverse_texts,
        "jbb_malicious_eval": jbb_mal,
    }
    fam_out: dict = {"family_order": list(DETECTOR_BASIS.keys()), "detector_basis": DETECTOR_BASIS, "sets": {}}
    for set_name, texts in sets.items():
        counts, no_match, examples = family_counts(texts)
        fam_out["sets"][set_name] = {
            "n": len(texts),
            "per_family": counts,
            "no_family_detector_matched": no_match,
            "examples": examples,
        }

    (OUT / "attack_families.json").write_text(json.dumps(fam_out, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# Q-Guardian Generalization Experiment: Attack-Family Coverage",
        "",
        "Counts are computed by applying real detectors to real text (no fabricated counts).",
        "Detector basis is recorded per family. Rule-based families use the production",
        "RuleEngine rules; heuristic families use transparent regex/keyword detectors and",
        "are explicitly marked. A text may match multiple families.",
        "",
        "| Set | n | " + " | ".join(DETECTOR_BASIS.keys()) + " | none matched |",
        "| --- | ---: | " + " | ".join(["---:"] * len(DETECTOR_BASIS)) + " | ---: |",
    ]
    for set_name in fam_out["sets"]:
        d = fam_out["sets"][set_name]
        row = [f"| {set_name} | {d['n']} |"]
        for fam in DETECTOR_BASIS.keys():
            row.append(f" {d['per_family'][fam]} |")
        row.append(f" {d['no_family_detector_matched']} |")
        md.append("".join(row))
    md.append("")
    md.append("## Detector basis")
    for fam, basis in DETECTOR_BASIS.items():
        md.append(f"- **{fam}**: {basis}")
    md.append("")
    md.append("## Sample matches per family (first 3, truncated)")
    for fam in DETECTOR_BASIS.keys():
        md.append(f"### {fam}")
        for set_name in ("control_train", "diverse_additions", "jbb_malicious_eval"):
            ex = fam_out["sets"][set_name]["examples"].get(fam, [])
            for e in ex:
                md.append(f"- [{set_name}] {e}")
        md.append("")
    (OUT / "attack_families.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("attack-family analysis written")


if __name__ == "__main__":
    main()
