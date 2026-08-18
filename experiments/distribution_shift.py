"""Cross-dataset distribution-shift analysis (root-cause research, Phase 7).

Compares the feature/distribution landscape of the training pools
(deepset-prompt-injections + dolly-benign) against the frozen external JBB
pool, using the exact feature extractors the production pipeline consumes
(normalizer -> feature extractor -> ML 43-vector, plus rule activation).

Statistics:
- basic text stats per pool
- positive (malicious) rate per pool
- rule activation rate per pool (any finding; plus per-rule)
- per-feature mean/std and standardized difference (Cohen's d) between
  training data and JBB

JBB is never used for training/tuning; this is measurement only.

Usage:
    python experiments/distribution_shift.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from _common import ROOT, SPLITS, silence_logging

from q_guardian.ml.feature_pipeline import MLFeatureProvider
from q_guardian.security.pipeline import PromptFeatureExtractor, PromptNormalizer, RuleEngine

OUTPUT = ROOT / "artifacts/experiments/distribution_shift"


def main() -> None:
    silence_logging()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    pools = {
        "train": _load(SPLITS / "train.jsonl"),
        "validation": _load(SPLITS / "validation.jsonl"),
        "test": _load(SPLITS / "test.jsonl"),
        "external_jbb": _load(SPLITS / "external_eval.jsonl"),
    }

    normalizer = PromptNormalizer()
    extractor = PromptFeatureExtractor()
    ml_features = MLFeatureProvider()
    rule_engine = RuleEngine()

    stats: dict[str, dict] = {}
    for name, rows in pools.items():
        lengths, words, tokens, entropies, up_ratio, dig_ratio, kws = [], [], [], [], [], [], []
        rule_activated = 0
        rule_counts: dict[str, int] = {}
        vectors: list[list[float]] = []
        pos = 0
        for row in rows:
            norm = normalizer.normalize(row["text"])
            base = extractor.extract(norm)
            vec = ml_features.extract_vector(norm, base).features
            vectors.append(vec)
            lengths.append(base.length)
            words.append(base.word_count)
            tokens.append(base.token_estimate)
            entropies.append(base.entropy)
            up_ratio.append(base.uppercase_ratio)
            dig_ratio.append(base.digit_ratio)
            kws.append(len(base.suspicious_keywords))
            findings = rule_engine.analyze(norm)
            if findings:
                rule_activated += 1
                for f in findings:
                    rule_counts[f.rule_id] = rule_counts.get(f.rule_id, 0) + 1
            if row["label"] == 1:
                pos += 1
        n = len(rows)
        stats[name] = {
            "samples": n,
            "positive_rate": pos / n if n else 0.0,
            "length": _dist(lengths),
            "word_count": _dist(words),
            "token_estimate": _dist(tokens),
            "entropy": _dist(entropies),
            "uppercase_ratio": _dist(up_ratio),
            "digit_ratio": _dist(dig_ratio),
            "suspicious_keyword_count": _dist(kws),
            "rule_activation_rate": rule_activated / n if n else 0.0,
            "rule_counts": dict(sorted(rule_counts.items(), key=lambda kv: -kv[1])),
        }

    # Feature-level standardized differences (train vs JBB).
    feature_names = ml_features.feature_names
    train_vecs = stats["train"] and pools["train"]
    train_vectors = [
        ml_features.extract_vector(
            normalizer.normalize(r["text"]), extractor.extract(normalizer.normalize(r["text"]))
        ).features
        for r in train_vecs
    ]
    jbb_vectors = stats["external_jbb"] and pools["external_jbb"]
    jbb_vectors = [
        ml_features.extract_vector(
            normalizer.normalize(r["text"]), extractor.extract(normalizer.normalize(r["text"]))
        ).features
        for r in jbb_vectors
    ]
    cohens_d = []
    for i, name in enumerate(feature_names):
        a = [v[i] for v in train_vectors]
        b = [v[i] for v in jbb_vectors]
        cohens_d.append(
            {
                "feature": name,
                "train_mean": round(_mean(a), 4),
                "jbb_mean": round(_mean(b), 4),
                "cohens_d": round(_cohens_d(a, b), 4),
            }
        )
    cohens_d.sort(key=lambda r: -abs(r["cohens_d"]))

    report = {
        "pool_stats": stats,
        "feature_count": len(feature_names),
        "feature_shift_train_vs_jbb": cohens_d,
        "largest_shifts": cohens_d[:15],
    }

    (OUTPUT / "distribution_statistics.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (OUTPUT / "distribution_shift.md").write_text(render(report), encoding="utf-8")
    print("done")


def _load(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _dist(values: list[float]) -> dict[str, float]:
    s = sorted(values)
    n = len(s)

    def pct(p: int) -> float:
        idx = min(n - 1, max(0, int(n * p / 100))) if n else 0
        return round(s[idx], 4) if s else 0.0

    return {
        "mean": round(_mean(values), 4),
        "min": round(s[0], 4) if s else 0.0,
        "p25": pct(25),
        "median": pct(50),
        "p75": pct(75),
        "p90": pct(90),
        "max": round(s[-1], 4) if s else 0.0,
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _cohens_d(a: list[float], b: list[float]) -> float:
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return 0.0
    ma, mb = _mean(a), _mean(b)
    sa, sb = _stdev(a), _stdev(b)
    sp = math.sqrt(((na - 1) * sa**2 + (nb - 1) * sb**2) / (na + nb - 2))
    if sp == 0:
        return 0.0
    return (ma - mb) / sp


def render(report: dict) -> str:
    lines = [
        "# Cross-Dataset Distribution Shift (train vs JBB)",
        "",
        "Compares training-distribution pools (deepset + dolly) against the "
        "frozen external JBB pool using the exact production feature extractors.",
        "",
        "## Pool summary",
        "",
        "| Pool | Samples | Positive rate | Rule activation | Length (med) | Tokens (med) | Entropy (med) | S-KW (med) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, s in report["pool_stats"].items():
        lines.append(
            f"| {name} | {s['samples']} | {s['positive_rate']:.3f} | "
            f"{s['rule_activation_rate']:.3f} | {s['length']['median']} | "
            f"{s['token_estimate']['median']} | {s['entropy']['median']} | "
            f"{s['suspicious_keyword_count']['median']} |"
        )
    lines.append("")
    lines.append("## Rule activation rate")
    lines.append("")
    lines.append("| Pool | Any finding | Rule | Count |")
    lines.append("| --- | --- | --- | --- |")
    for name, s in report["pool_stats"].items():
        if not s["rule_counts"]:
            lines.append(f"| {name} | {s['rule_activation_rate']:.3f} | - | 0 |")
        for rid, count in list(s["rule_counts"].items())[:4]:
            lines.append(f"| {name} | {s['rule_activation_rate']:.3f} | {rid} | {count} |")
    lines.append("")
    lines.append("## Largest feature shifts (train vs JBB, |Cohen's d|)")
    lines.append("")
    lines.append("| Feature | Train mean | JBB mean | Cohen's d |")
    lines.append("| --- | --- | --- | --- |")
    for r in report["largest_shifts"]:
        lines.append(f"| {r['feature']} | {r['train_mean']} | {r['jbb_mean']} | {r['cohens_d']} |")
    lines.append("")
    lines.append("> Cohen's d: standardized mean difference. |d|>=0.8 is a large shift.")
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
