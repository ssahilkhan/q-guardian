"""Fusion analysis experiment (root-cause research, Phase 8).

The baseline fusion is a weighted soft-vote over provider threat
probabilities:  fused = (0.15*rule + 0.15*isolation_forest + 0.55*random_forest)
/ 0.85  (verified against the cached per-sample scores to <5e-7).

This phase tests whether the fusion recipe itself explains the JBB failure:

* Weight schemes (weights selected on VALIDATION ONLY, then applied frozen):
    - production      (0.15 / 0.15 / 0.55)
    - equal           (1/3 each)
    - rule_only, if_only, rf_only
    - validation_grid  argmax validation F1 over a coarse 4x4x4 weight grid
* Score calibration:
    - min-max normalization of each provider on VALIDATION (mapping to a
      comparable 0..1 scale) before equal-weight fusion. Scales computed on
      validation are applied to test/JBB unchanged.

JBB is measured only and never used to select anything.

Usage:
    python experiments/fusion_analysis.py
"""

from __future__ import annotations

import itertools
import json

import numpy as np
from _common import ROOT, score_provider_pools, silence_logging

from q_guardian.evaluation.metrics import detection_metrics

OUTPUT = ROOT / "artifacts/experiments/fusion_analysis"
THRESHOLD = 0.5


def main() -> None:
    silence_logging()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    pools = score_provider_pools()
    labels = {name: [r["label"] for r in rows] for name, rows in pools.items()}
    providers = ("rule-engine", "isolation-forest", "random-forest")
    scores = {
        name: np.array([[r[p] for p in providers] for r in rows], dtype=np.float64)
        for name, rows in pools.items()
    }

    schemes: list[tuple[str, tuple[float, float, float]]] = [
        ("production", (0.15, 0.15, 0.55)),
        ("equal", (1.0, 1.0, 1.0)),
        ("rule_only", (1.0, 0.0, 0.0)),
        ("if_only", (0.0, 1.0, 0.0)),
        ("rf_only", (0.0, 0.0, 1.0)),
    ]

    grid = itertools.product((0.0, 0.25, 0.5, 1.0), repeat=3)
    grid = (w for w in grid if sum(w) > 0)
    best = max(
        ((w, _f1(_fuse(scores["validation"], w), labels["validation"])) for w in grid),
        key=lambda x: (x[1], _grid_index(x[0])),
    )
    schemes.append((f"validation_grid({_fmt(best[0])})", best[0]))

    report: dict = {"threshold": THRESHOLD, "schemes": {}}
    for name, weights in schemes:
        fused = {
            pool: _fuse(mat, weights) for pool, mat in scores.items()
        }
        entry: dict = {"weights": list(weights), "pools": {}}
        for pool in ("validation", "test", "external_jbb"):
            m = detection_metrics(labels[pool], fused[pool].tolist(), threshold=THRESHOLD)
            entry["pools"][pool] = _metrics(m)
        report["schemes"][name] = entry
        print(f"{name}: val {entry['pools']['validation']['f1']:.3f} / "
              f"test {entry['pools']['test']['f1']:.3f} / "
              f"jbb {entry['pools']['external_jbb']['f1']:.3f}")

    _calibration_notes(report, scores, labels)
    _minmax_schemes(report, scores, labels)

    (OUTPUT / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUTPUT / "fusion_analysis_report.md").write_text(render(report), encoding="utf-8")
    print("done")


def _fuse(mat: np.ndarray, weights: tuple[float, float, float]) -> np.ndarray:
    total = sum(weights)
    return (mat @ np.array(weights, dtype=np.float64)) / total


def _f1(scores: np.ndarray, labels: list[int]) -> float:
    return float(detection_metrics(labels, scores.tolist(), threshold=THRESHOLD)["f1_score"])


def _grid_index(w: tuple[float, float, float]) -> tuple[int, int, int]:
    options = (0.0, 0.25, 0.5, 1.0)
    return tuple(options.index(v) for v in w)  # type: ignore[return-value]


def _fmt(w: tuple[float, float, float]) -> str:
    return "_".join(str(v) for v in w)


def _metrics(m: dict) -> dict[str, float]:
    return {
        "f1": m["f1_score"],
        "precision": m["precision"],
        "recall": m["recall"],
        "fpr": m["false_positive_rate"],
        "roc_auc": m["roc_auc"],
        "mcc": m["matthews_corrcoef"],
    }


def _calibration_notes(report: dict, scores: dict[str, np.ndarray], labels: dict) -> None:
    """Record raw provider scale differences (informational only)."""
    report["raw_provider_ranges"] = {}
    for pool, mat in scores.items():
        report["raw_provider_ranges"][pool] = {
            p: {"min": float(mat[:, i].min()), "max": float(mat[:, i].max())}
            for i, p in enumerate(("rule-engine", "isolation-forest", "random-forest"))
        }


def _minmax_schemes(
    report: dict,
    scores: dict[str, np.ndarray],
    labels: dict,
) -> None:
    """Equal-weight fusion after min-max rescaling fit on VALIDATION only."""
    v = scores["validation"]
    lo = v.min(axis=0)
    hi = v.max(axis=0)
    span = np.where(hi - lo > 0, hi - lo, 1.0)

    def _norm(mat: np.ndarray) -> np.ndarray:
        return (mat - lo) / span

    fused = {pool: _norm(mat).mean(axis=1) for pool, mat in scores.items()}
    entry = {"weights": [1 / 3] * 3, "normalized": "minmax_fit_on_validation", "pools": {}}
    for pool in ("validation", "test", "external_jbb"):
        m = detection_metrics(labels[pool], fused[pool].tolist(), threshold=THRESHOLD)
        entry["pools"][pool] = _metrics(m)
    report["schemes"]["minmax_equal"] = entry
    print(f"minmax_equal: val {entry['pools']['validation']['f1']:.3f} / "
          f"test {entry['pools']['test']['f1']:.3f} / "
          f"jbb {entry['pools']['external_jbb']['f1']:.3f}")


def render(report: dict) -> str:
    lines = [
        "# Fusion Analysis (frozen JBB measurement only)",
        "",
        "Weight schemes selected on VALIDATION only; test and JBB measured frozen. "
        "JBB never influences selection.",
        "",
        "| Scheme | val F1 | test F1 | JBB F1 | JBB AUC | JBB recall |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, s in report["schemes"].items():
        v, t, j = s["pools"]["validation"], s["pools"]["test"], s["pools"]["external_jbb"]
        lines.append(
            f"| {name} | {v['f1']:.4f} | {t['f1']:.4f} | {j['f1']:.4f} "
            f"| {j['roc_auc']:.4f} | {j['recall']:.4f} |"
        )
    lines.append("")
    lines.append("## Raw provider score ranges (calibration check)")
    lines.append("| Pool | rule | isolation-forest | random-forest |")
    lines.append("| --- | --- | --- | --- |")
    for pool, ranges in report["raw_provider_ranges"].items():
        cells = []
        for p in ("rule-engine", "isolation-forest", "random-forest"):
            r = ranges[p]
            cells.append(f"[{r['min']:.3f}, {r['max']:.3f}]")
        lines.append(f"| {pool} | {cells[0]} | {cells[1]} | {cells[2]} |")
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
