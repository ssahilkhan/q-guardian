"""JBB error analysis experiment (root-cause research, Phase 6).

Uses the frozen baseline fusion scores on the external JBB pool (200
samples). JBB labels are used ONLY for post-hoc error analysis, never for
training, tuning, or threshold selection (dataset policy).

Analysis:
- confusion counts at production threshold 0.5
- which JBB categories are detected vs missed
- distribution of missed (FN) scores and of the few detected (TP)
- top/high-scoring samples per class to expose what the detector keys on

Usage:
    python experiments/jbb_error_analysis.py
"""

from __future__ import annotations

import json

from _common import ROOT, load_pools, score_provider_pools, silence_logging

from q_guardian.evaluation.metrics import detection_metrics

OUTPUT = ROOT / "artifacts/experiments/jbb_error_analysis"
THRESHOLD = 0.5


def main() -> None:
    silence_logging()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    rows = score_provider_pools()["external_jbb"]
    ds = load_pools()["external_jbb"]
    cats = dict(zip(ds.texts(), ds.categories(), strict=True))

    labels = [r["label"] for r in rows]
    scores = [r["fusion"] for r in rows]

    m = detection_metrics(labels, scores, threshold=THRESHOLD)
    confusion = {
        "tp": m["true_positives"],
        "fp": m["false_positives"],
        "fn": m["false_negatives"],
        "tn": m["true_negatives"],
    }

    # Per-category confusion at threshold.
    cat_rows: dict[str, dict] = {}
    for row in rows:
        cat = cats.get(row["text"], "unknown")
        pred = 1 if row["fusion"] >= THRESHOLD else 0
        bucket = cat_rows.setdefault(cat, {"n": 0, "malicious": 0, "detected": 0, "fp": 0, "tp": 0})
        bucket["n"] += 1
        if row["label"] == 1:
            bucket["malicious"] += 1
            if pred == 1:
                bucket["detected"] += 1
                bucket["tp"] += 1
        elif pred == 1:
            bucket["fp"] += 1

    report = {
        "threshold": THRESHOLD,
        "confusion": confusion,
        "categories": {
            cat: {
                "samples": b["n"],
                "malicious": b["malicious"],
                "detected": b["detected"],
                "fp": b["fp"],
                "tp": b["tp"],
            }
            for cat, b in sorted(cat_rows.items())
        },
        "tp_examples": _examples(rows, cats, top=True, label=1),
        "fp_examples": _examples(rows, cats, top=True, label=0),
        "top_scoring_malicious": _examples(rows, cats, top=12, label=1, min_score=0.0),
        "top_scoring_benign": _examples(rows, cats, top=12, label=0, min_score=0.0),
        "fn_score_distribution": _score_bucket(rows, label=1, pred=0),
    }

    (OUTPUT / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUTPUT / "jbb_error_analysis.md").write_text(render(report), encoding="utf-8")
    print("done")


def _examples(
    rows: list[dict],
    cats: dict[str, str],
    label: int,
    top: int | None = None,
    min_score: float = 0.5,
) -> list[dict]:
    sub = [r for r in rows if r["label"] == label and r["fusion"] >= min_score]
    sub.sort(key=lambda r: r["fusion"], reverse=True)
    if top is not None:
        sub = sub[:top]
    return [
        {
            "category": cats.get(r["text"], "unknown"),
            "score": round(r["fusion"], 4),
            "text": r["text"][:160],
        }
        for r in sub
    ]


def _score_bucket(rows: list[dict], label: int, pred: int) -> list[dict]:
    sub = [
        r for r in rows if r["label"] == label and (1 if r["fusion"] >= THRESHOLD else 0) == pred
    ]
    scores = sorted(r["fusion"] for r in sub)
    n = len(scores)
    pcts = []
    for p in (0, 10, 25, 50, 75, 90, 95, 100):
        idx = min(n - 1, max(0, int(n * p / 100))) if n else 0
        pcts.append(round(scores[idx], 4) if scores else None)
    return {
        "n": n,
        "min": round(scores[0], 4) if scores else None,
        "percentiles": pcts,
        "max": round(scores[-1], 4) if scores else None,
    }


def render(report: dict) -> str:
    lines = [
        "# JBB Error Analysis (frozen baseline, threshold 0.5)",
        "",
        "Post-hoc diagnostic only. JBB labels never influence training or threshold selection.",
        "",
        f"## Confusion at threshold {report['threshold']}",
        "",
        f"- TP (detected attacks): **{report['confusion']['tp']}** "
        f"(of {sum(b['malicious'] for b in report['categories'].values())} attacks)"
        f"- FP: **{report['confusion']['fp']}** "
        f"- FN: **{report['confusion']['fn']}** "
        f"- TN: **{report['confusion']['tn']}**",
        "",
        "## Per-category detection",
        "",
        "| Category | Samples | Malicious | Detected (TP) | FP |",
        "| --- | --- | --- | --- | --- |",
    ]
    for cat, b in report["categories"].items():
        lines.append(f"| {cat} | {b['samples']} | {b['malicious']} | {b['detected']} | {b['fp']} |")
    lines.append("")
    lines.append("## Detected attacks (TP examples)")
    lines.append("")
    for ex in report["tp_examples"]:
        lines.append(f"- `{ex['category']}` score={ex['score']}: {ex['text']}")
    lines.append("")
    lines.append("## False positives (benign flagged)")
    lines.append("")
    for ex in report["fp_examples"]:
        lines.append(f"- `{ex['category']}` score={ex['score']}: {ex['text']}")
    lines.append("")
    lines.append("## Missed-attack score distribution (FN)")
    lines.append("")
    fn = report["fn_score_distribution"]
    lines.append(
        f"- n={fn['n']}, min {fn['min']}, percentiles {fn['percentiles']}, max {fn['max']}"
    )
    lines.append("")
    lines.append("## Highest-scoring malicious prompts (would rank first at any threshold)")
    lines.append("")
    for ex in report["top_scoring_malicious"]:
        lines.append(f"- `{ex['category']}` score={ex['score']}: {ex['text']}")
    lines.append("")
    lines.append("## Highest-scoring benign prompts")
    lines.append("")
    for ex in report["top_scoring_benign"]:
        lines.append(f"- `{ex['category']}` score={ex['score']}: {ex['text']}")
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
