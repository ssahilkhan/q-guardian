"""Dataset integrity and leakage check for external generalization study.

Checks for:
- Exact duplicate prompts
- Near-duplicate prompts (n-gram overlap)
- Train/test overlap
- Label leakage
- Cross-dataset contamination
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# Files to check
DATASETS = {
    "jbb_harmful": ROOT / "C:/Users/hp/.qguardian/benchmark/jbb-behaviors__harmful.jsonl",
    "jbb_benign": ROOT / "C:/Users/hp/.qguardian/benchmark/jbb-behaviors__benign.jsonl",
    "deepset_train": ROOT / "C:/Users/hp/.qguardian/benchmark/deepset-prompt-injections__train.jsonl",
    "deepset_test": ROOT / "C:/Users/hp/.qguardian/benchmark/deepset-prompt-injections__test.jsonl",
    "dolly": ROOT / "C:/Users/hp/.qguardian/benchmark/dolly-benign__train.jsonl",
    "trustair_jailbreaks": ROOT / "experiments/training_diversity/data_raw/trustair_jailbreaks.jsonl",
    "trustair_regular": ROOT / "experiments/training_diversity/data_raw/trustair_regular.jsonl",
    "jailbreakv": ROOT / "experiments/training_diversity/data_raw/jailbreakv.jsonl",
    "harmful_train": ROOT / "experiments/training_diversity/data_raw/harmful_behaviors_train.jsonl",
    "harmful_test": ROOT / "experiments/training_diversity/data_raw/harmful_behaviors_test.jsonl",
    "arm_a": ROOT / "experiments/training_diversity/train_sets/arm_a.jsonl",
    "arm_b": ROOT / "experiments/training_diversity/train_sets/arm_b.jsonl",
    "arm_c": ROOT / "experiments/training_diversity/train_sets/arm_c.jsonl",
    "arm_d": ROOT / "experiments/training_diversity/train_sets/arm_d.jsonl",
    "control": ROOT / "experiments/training_diversity/train_sets/control.jsonl",
    "split_train": ROOT / "artifacts/training_xgboost_fix/splits/train.jsonl",
    "split_validation": ROOT / "artifacts/training_xgboost_fix/splits/validation.jsonl",
    "split_test": ROOT / "artifacts/training_xgboost_fix/splits/test.jsonl",
    "split_external_eval": ROOT / "artifacts/training_xgboost_fix/splits/external_eval.jsonl",
}


def load_prompts(path: Path, text_keys=("Goal", "text", "instruction", "prompt", "adversarial", "vanilla")) -> list[dict[str, Any]]:
    """Load prompts from JSONL file with flexible text field detection."""
    prompts = []
    if not path.exists():
        return prompts
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = None
                for key in text_keys:
                    if key in rec and isinstance(rec[key], str):
                        text = rec[key]
                        break
                if not text or not text.strip():
                    continue
                prompts.append({
                    "index": i,
                    "text": text.strip(),
                    "raw": rec,
                    "hash": hashlib.sha256(text.strip().encode()).hexdigest()[:16],
                })
    except Exception as e:
        print(f"Error loading {path}: {e}")
    return prompts


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    return " ".join(text.lower().split())


def check_exact_duplicates(datasets: dict[str, list[dict]]) -> dict[str, Any]:
    """Check for exact duplicate prompts within and across datasets."""
    all_prompts = []
    for name, prompts in datasets.items():
        for p in prompts:
            all_prompts.append((p["hash"], p["text"][:100], name, p["index"]))

    hash_to_entries = {}
    for h, text, name, idx in all_prompts:
        hash_to_entries.setdefault(h, []).append((name, idx, text))

    duplicates = {h: entries for h, entries in hash_to_entries.items() if len(entries) > 1}
    cross_dataset = {h: entries for h, entries in duplicates.items() if len({e[0] for e in entries}) > 1}

    return {
        "total_prompts": len(all_prompts),
        "unique_hashes": len(hash_to_entries),
        "duplicate_hashes": len(duplicates),
        "cross_dataset_duplicates": len(cross_dataset),
        "cross_dataset_details": [
            {"hash": h, "entries": [{"dataset": n, "index": i, "text": t[:200]} for n, i, t in entries]}
            for h, entries in cross_dataset.items()
        ],
    }


def check_ngram_overlap(datasets: dict[str, list[dict]], n: int = 8, threshold: float = 0.8) -> list[dict]:
    """Check for near-duplicates using n-gram Jaccard similarity (sampled)."""
    import random
    random.seed(42)

    # Sample up to 500 prompts per dataset for comparison
    sampled = {}
    for name, prompts in datasets.items():
        if len(prompts) > 500:
            sampled[name] = random.sample(prompts, 500)
        else:
            sampled[name] = prompts

    overlaps = []
    names = list(sampled.keys())

    for i, name1 in enumerate(names):
        for name2 in names[i:]:
            if name1 == name2:
                continue
            prompts1 = sampled[name1]
            prompts2 = sampled[name2]

            # Compare a subset
            for p1 in prompts1[:100]:
                text1 = normalize_text(p1["text"])
                ngrams1 = set(text1[j:j+n] for j in range(len(text1) - n + 1))
                if not ngrams1:
                    continue

                for p2 in prompts2[:100]:
                    text2 = normalize_text(p2["text"])
                    ngrams2 = set(text2[j:j+n] for j in range(len(text2) - n + 1))
                    if not ngrams2:
                        continue

                    intersection = len(ngrams1 & ngrams2)
                    union = len(ngrams1 | ngrams2)
                    jaccard = intersection / union if union > 0 else 0

                    if jaccard >= threshold:
                        overlaps.append({
                            "dataset1": name1,
                            "index1": p1["index"],
                            "text1": p1["text"][:200],
                            "dataset2": name2,
                            "index2": p2["index"],
                            "text2": p2["text"][:200],
                            "jaccard": round(jaccard, 4),
                        })

    return overlaps


def check_label_leakage(datasets: dict[str, list[dict]]) -> dict[str, Any]:
    """Check for label leakage - same prompt with different labels."""
    text_to_labels = {}

    for name, prompts in datasets.items():
        for p in prompts:
            text = normalize_text(p["text"])
            label = None
            raw = p.get("raw", {})
            for key in ("label", "jailbreak", "malicious"):
                if key in raw:
                    val = raw[key]
                    if isinstance(val, (int, bool)):
                        label = int(val)
                        break
            if label is None and "default_label" in str(raw):
                # Check if default_label was used
                pass

            if label is not None:
                text_to_labels.setdefault(text, []).append((name, label))

    leakage = {text: entries for text, entries in text_to_labels.items()
               if len(set(l for _, l in entries)) > 1}

    return {
        "total_labeled_texts": len(text_to_labels),
        "label_conflicts": len(leakage),
        "conflicts": [
            {"text": text[:200], "labels": [{"dataset": n, "label": l} for n, l in entries]}
            for text, entries in leakage.items()
        ][:50],  # Limit to 50
    }


def check_train_test_overlap() -> dict[str, Any]:
    """Check overlap between internal splits and external eval."""
    # Load internal splits
    splits = {}
    for name in ["split_train", "split_validation", "split_test", "split_external_eval"]:
        path = DATASETS.get(name)
        if path and path.exists():
            splits[name] = load_prompts(path)

    if not splits:
        return {"error": "No split files found"}

    train_texts = {normalize_text(p["text"]) for p in splits.get("split_train", [])}
    val_texts = {normalize_text(p["text"]) for p in splits.get("split_validation", [])}
    test_texts = {normalize_text(p["text"]) for p in splits.get("split_test", [])}
    external_texts = {normalize_text(p["text"]) for p in splits.get("split_external_eval", [])}

    return {
        "train_vs_external": len(train_texts & external_texts),
        "val_vs_external": len(val_texts & external_texts),
        "test_vs_external": len(test_texts & external_texts),
        "train_vs_val": len(train_texts & val_texts),
        "train_vs_test": len(train_texts & test_texts),
        "val_vs_test": len(val_texts & test_texts),
    }


def check_training_data_vs_external() -> dict[str, Any]:
    """Check overlap between training diversity data and external eval (JBB)."""
    # Load JBB external eval
    jbb_path = DATASETS.get("jbb_harmful")
    jbb_benign_path = DATASETS.get("jbb_benign")

    jbb_texts = set()
    if jbb_path and jbb_path.exists():
        for p in load_prompts(jbb_path):
            jbb_texts.add(normalize_text(p["text"]))
    if jbb_benign_path and jbb_benign_path.exists():
        for p in load_prompts(jbb_benign_path):
            jbb_texts.add(normalize_text(p["text"]))

    # Training data files
    training_files = {
        "trustair_jailbreaks": DATASETS.get("trustair_jailbreaks"),
        "trustair_regular": DATASETS.get("trustair_regular"),
        "jailbreakv": DATASETS.get("jailbreakv"),
        "harmful_train": DATASETS.get("harmful_train"),
        "harmful_test": DATASETS.get("harmful_test"),
    }

    results = {}
    for name, path in training_files.items():
        if not path or not path.exists():
            results[name] = {"error": "file not found"}
            continue
        prompts = load_prompts(path)
        train_texts = {normalize_text(p["text"]) for p in prompts}
        overlap = len(train_texts & jbb_texts)
        results[name] = {
            "samples": len(prompts),
            "jbb_overlap": overlap,
            "overlap_pct": round(overlap / len(prompts) * 100, 2) if prompts else 0,
        }

    return results


def main() -> int:
    print("Loading datasets...")
    datasets = {}
    for name, path in DATASETS.items():
        if path and path.exists():
            prompts = load_prompts(path)
            if prompts:
                datasets[name] = prompts
                print(f"  {name}: {len(prompts)} prompts")
            else:
                print(f"  {name}: 0 prompts (empty or error)")
        else:
            print(f"  {name}: NOT FOUND at {path}")

    print(f"\nLoaded {len(datasets)} datasets with {sum(len(p) for p in datasets.values())} total prompts")

    print("\n1. Checking exact duplicates...")
    dup_results = check_exact_duplicates(datasets)
    print(f"   Total prompts: {dup_results['total_prompts']}")
    print(f"   Unique hashes: {dup_results['unique_hashes']}")
    print(f"   Duplicate hashes: {dup_results['duplicate_hashes']}")
    print(f"   Cross-dataset duplicates: {dup_results['cross_dataset_duplicates']}")

    print("\n2. Checking n-gram overlaps (n=8, threshold=0.8)...")
    overlaps = check_ngram_overlap(datasets)
    print(f"   Near-duplicate pairs found: {len(overlaps)}")
    if overlaps:
        for o in overlaps[:5]:
            print(f"   {o['dataset1']}[{o['index1']}] ~ {o['dataset2']}[{o['index2']}] (J={o['jaccard']})")

    print("\n3. Checking label leakage...")
    leak_results = check_label_leakage(datasets)
    print(f"   Total labeled texts: {leak_results['total_labeled_texts']}")
    print(f"   Label conflicts: {leak_results['label_conflicts']}")

    print("\n4. Checking internal train/test/external overlaps...")
    split_results = check_train_test_overlap()
    if "error" not in split_results:
        print(f"   Train vs External: {split_results['train_vs_external']}")
        print(f"   Val vs External: {split_results['val_vs_external']}")
        print(f"   Test vs External: {split_results['test_vs_external']}")
        print(f"   Train vs Val: {split_results['train_vs_val']}")
        print(f"   Train vs Test: {split_results['train_vs_test']}")
        print(f"   Val vs Test: {split_results['val_vs_test']}")

    print("\n5. Checking training diversity data vs JBB external eval...")
    train_vs_jbb = check_training_data_vs_external()
    for name, res in train_vs_jbb.items():
        if "error" in res:
            print(f"   {name}: {res['error']}")
        else:
            print(f"   {name}: {res['jbb_overlap']}/{res['samples']} ({res['overlap_pct']}%) overlap with JBB")

    # Compile report
    report = {
        "exact_duplicates": dup_results,
        "ngram_overlaps": overlaps[:100],  # Limit for JSON size
        "label_leakage": leak_results,
        "split_overlaps": split_results,
        "training_vs_jbb": train_vs_jbb,
    }

    out_dir = ROOT / "reports" / "ml_external_study"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "leakage_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to {out_dir / 'leakage_report.json'}")

    # Summary
    print("\n" + "="*60)
    print("LEAKAGE CHECK SUMMARY")
    print("="*60)
    print(f"Cross-dataset exact duplicates: {dup_results['cross_dataset_duplicates']}")
    print(f"Near-duplicate pairs (Jaccard >= 0.8): {len(overlaps)}")
    print(f"Label conflicts: {leak_results['label_conflicts']}")
    print(f"Train vs JBB external overlaps: {sum(r.get('jbb_overlap', 0) for r in train_vs_jbb.values())} total")
    for name, res in train_vs_jbb.items():
        if "jbb_overlap" in res and res["jbb_overlap"] > 0:
            print(f"  WARNING: {name} has {res['jbb_overlap']} overlaps with JBB!")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
