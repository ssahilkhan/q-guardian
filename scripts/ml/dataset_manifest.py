"""Dataset manifest builder for Q-Guardian ML datasets.

Scans every local dataset used for training/evaluation, records composition
(sample/malicious/benign counts), provenance, purpose, and download status,
and reports which benchmark datasets are available vs require Hugging Face
authentication. No tokens are read from anywhere except the ``HF_TOKEN``
environment variable, and the token value is never recorded.

Usage::

    python -m scripts.ml.dataset_manifest [--out DIR]

Outputs::

    <out>/dataset_manifest.json
    <out>/dataset_manifest.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_OUT = ROOT / "reports" / "ml_baseline"

# label field conventions seen across local datasets
_LABEL_KEYS = ("label", "jailbreak", "malicious")
_TEXT_KEYS = ("text", "prompt", "jailbreak_query", "redteam_query")


def count_jsonl(path: Path, default_label: int | None = None) -> dict[str, Any] | None:
    """Count samples/labels in a JSONL file of {text,label} rows."""
    n = 0
    mal = 0
    ben = 0
    bad = 0
    unlabeled = 0
    implied_mal = 0
    implied_ben = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                text = next(
                    (rec[k] for k in _TEXT_KEYS if isinstance(rec.get(k), str)),
                    None,
                )
                if not isinstance(text, str) or not text.strip():
                    bad += 1
                    continue
                label = None
                for key in _LABEL_KEYS:
                    if key in rec:
                        raw = rec[key]
                        if isinstance(raw, (int, bool)):
                            label = int(raw)
                        break
                if label is None:
                    if default_label is not None:
                        if default_label == 1:
                            implied_mal += 1
                        else:
                            implied_ben += 1
                    else:
                        unlabeled += 1
                    continue
                n += 1
                if label == 1:
                    mal += 1
                else:
                    ben += 1
    except OSError as exc:
        return {"path": str(path), "error": str(exc)}
    return {
        "samples": n + implied_mal + implied_ben + unlabeled,
        "malicious": mal + implied_mal,
        "benign": ben + implied_ben,
        "unlabeled": unlabeled,
        "implied_malicious": implied_mal,
        "implied_benign": implied_ben,
        "skipped_rows": bad,
        "label_ratio": round(mal / n, 4) if n else 0.0,
    }


LOCAL_DATASETS: list[dict[str, Any]] = [
    {
        "name": "prompt_injections",
        "source": "HF deepset/prompt-injections",
        "paths": ["data/prompt_injections.jsonl"],
        "purpose": "control training pool (in-domain prompt injections)",
    },
    {
        "name": "benchmark_prompts",
        "source": "internal curation",
        "paths": ["data/benchmark_prompts.jsonl"],
        "purpose": "small held-out QA smoke set",
    },
    {
        "name": "trustair_jailbreaks",
        "source": "HF TrustAIRLab/in-the-wild-jailbreak-prompts (jailbreak_2023_12_25)",
        "paths": ["experiments/training_diversity/data_raw/trustair_jailbreaks.jsonl"],
        "purpose": "diverse training arm A/D (real-user jailbreaks, label=jailbreak:true)",
        "default_label": 1,
    },
    {
        "name": "trustair_regular",
        "source": "HF TrustAIRLab/in-the-wild-jailbreak-prompts (regular_2023_12_25)",
        "paths": ["experiments/training_diversity/data_raw/trustair_regular.jsonl"],
        "purpose": "diverse benign pool (capped at 2000 when building arms)",
        "default_label": 0,
    },
    {
        "name": "jailbreakv",
        "source": "HF JailbreakV-28K/JailBreakV-28k (partial download, max_rows=5900)",
        "paths": ["experiments/training_diversity/data_raw/jailbreakv.jsonl"],
        "purpose": "diverse training arm B/D (seeded 2000-sample subset, seed=42)",
        "default_label": 1,
    },
    {
        "name": "harmful_behaviors_train",
        "source": "HF mlabonne/harmful_behaviors (train split)",
        "paths": ["experiments/training_diversity/data_raw/harmful_behaviors_train.jsonl"],
        "purpose": "diverse training arm C/D (unlabeled rows; malicious by source, "
        "contamination-filtered at arm build time)",
        "default_label": 1,
    },
    {
        "name": "harmful_behaviors_test",
        "source": "HF mlabonne/harmful_behaviors (test split)",
        "paths": ["experiments/training_diversity/data_raw/harmful_behaviors_test.jsonl"],
        "purpose": "diverse training arm C/D (unlabeled rows; malicious by source, "
        "contamination-filtered at arm build time)",
        "default_label": 1,
    },
    {
        "name": "arm_control",
        "source": "deepset-prompt-injections + dolly-benign",
        "paths": ["experiments/training_diversity/train_sets/control.jsonl"],
        "purpose": "control training arm (2425 samples)",
    },
    {
        "name": "arm_a",
        "source": "control + trustair_jailbreaks",
        "paths": ["experiments/training_diversity/train_sets/arm_a.jsonl"],
        "purpose": "training-diversity experiment arm A",
    },
    {
        "name": "arm_b",
        "source": "control + jailbreakv subset",
        "paths": ["experiments/training_diversity/train_sets/arm_b.jsonl"],
        "purpose": "training-diversity experiment arm B",
    },
    {
        "name": "arm_c",
        "source": "control + harmful_behaviors (filtered)",
        "paths": ["experiments/training_diversity/train_sets/arm_c.jsonl"],
        "purpose": "training-diversity experiment arm C",
    },
    {
        "name": "arm_d",
        "source": "control + trustair + jailbreakv + harmful_behaviors",
        "paths": ["experiments/training_diversity/train_sets/arm_d.jsonl"],
        "purpose": "DIVERSE training arm D (production retrain candidate)",
    },
    {
        "name": "split_train",
        "source": "derived from control pool",
        "paths": ["artifacts/training_xgboost_fix/splits/train.jsonl"],
        "purpose": "frozen internal train split",
    },
    {
        "name": "split_validation",
        "source": "deepset-prompt-injections",
        "paths": ["artifacts/training_xgboost_fix/splits/validation.jsonl"],
        "purpose": "calibration + threshold selection ONLY",
    },
    {
        "name": "split_test",
        "source": "deepset-prompt-injections",
        "paths": ["artifacts/training_xgboost_fix/splits/test.jsonl"],
        "purpose": "internal test (evaluation only, never fitted)",
    },
    {
        "name": "split_external_eval_jbb",
        "source": "HF JailbreakBench/JBB-Behaviors (public splits harmful+benign)",
        "paths": ["artifacts/training_xgboost_fix/splits/external_eval.jsonl"],
        "purpose": "EXTERNAL held-out evaluation (never fitted/selected on)",
    },
]


def benchmark_registry_status() -> list[dict[str, Any]]:
    """Report availability of every registered benchmark dataset."""
    try:
        from q_guardian.benchmark.registry import DatasetRegistry
    except Exception as exc:  # pragma: no cover - defensive
        return [{"error": f"registry unavailable: {exc}"}]

    rows = []
    for spec in DatasetRegistry.builtin().all():
        rows.append(
            {
                "dataset_id": spec.dataset_id,
                "hf_source": spec.source,
                "license": spec.license,
                "requires_token": bool(spec.requires_token),
                "available_without_auth": not spec.requires_token,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    for spec in LOCAL_DATASETS:
        entry: dict[str, Any] = {
            "name": spec["name"],
            "source": spec["source"],
            "purpose": spec["purpose"],
            "files": [],
        }
        total_mal = 0
        total_ben = 0
        found_any = False
        for rel in spec["paths"]:
            path = ROOT / rel
            status: dict[str, Any] = {"path": rel}
            if path.exists():
                default_label = spec.get("default_label")
                stats = count_jsonl(path, default_label)
                if stats and "error" not in stats:
                    found_any = True
                    total_mal += stats["malicious"]
                    total_ben += stats["benign"]
                status.update(stats or {})
                status["download_status"] = "local"
            else:
                status["download_status"] = "missing"
            entry["files"].append(status)
        entry["present"] = found_any
        entry["samples"] = total_mal + total_ben if found_any else 0
        entry["malicious"] = total_mal
        entry["benign"] = total_ben
        entries.append(entry)

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "datasets": entries,
        "benchmark_registry": benchmark_registry_status(),
        "notes": [
            "Gated benchmark datasets (wildjailbreak, harmbench-behaviors, "
            "advbench, hex-phi, pal, agentdojo, cyberseceval-prompt-injections, "
            "jailbreakbench-attacks) require accepting Hub terms and setting "
            "the HF_TOKEN environment variable; they are NOT downloaded here.",
            "No credentials are stored by this tool.",
        ],
    }

    out_json = args.out / "dataset_manifest.json"
    out_json.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    lines = [
        "# Q-Guardian Dataset Manifest",
        "",
        f"Generated: {manifest['generated_at']}",
        "",
        "| Dataset | Present | Samples | Malicious | Benign | Purpose |",
        "|---|---|---:|---:|---:|---|",
    ]
    for e in entries:
        lines.append(
            f"| {e['name']} | {'yes' if e['present'] else 'NO'} "
            f"| {e['samples']} | {e['malicious']} | {e['benign']} | {e['purpose']} |"
        )
    lines += ["", "## Benchmark registry", ""]
    for row in manifest["benchmark_registry"]:
        if "error" in row:
            lines.append(f"- registry error: {row['error']}")
            continue
        auth = "public" if row["available_without_auth"] else "gated (needs HF_TOKEN)"
        lines.append(f"- `{row['dataset_id']}` — {auth}")
    lines += ["", "## Notes", ""]
    for note in manifest["notes"]:
        lines.append(f"- {note}")

    (args.out / "dataset_manifest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_json}")
    print(f"Wrote {args.out / 'dataset_manifest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
