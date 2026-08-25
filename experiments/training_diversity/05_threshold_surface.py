"""Threshold decision-surface analysis for the generalization experiment.

Reads results.json (scores are stored per condition/model/pool), sweeps the
JBB threshold grid, and records:
- the F1-optimal operating point (what the experiment reported)
- the Youden-J optimal operating point
- the FPR<=0.05 operating point (production-safe constraint): highest detection
  achievable while keeping benign FPR at or below 5%

Appends `threshold_surface` to results.json and prints a compact table.
Does not retrain anything; no production code is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from q_guardian.evaluation.metrics import detection_metrics

OUT = (
    Path(__file__).resolve().parent.parent.parent
    / "artifacts"
    / "training"
    / "generalization_experiment"
)
RESULTS = OUT / "results.json"

GRID = [round(t, 2) for t in np.arange(0.01, 1.0, 0.01)]

CONFIGS = ("baseline_43", "exp1_diverse_43", "exp2_semantic_427", "exp3_diverse_427")


def operating_points(scores: list[float], y: list[int]) -> dict:
    rows = []
    for t in GRID:
        m = detection_metrics(y, scores, threshold=t)
        rows.append(
            {
                "threshold": t,
                "detection": round(m["recall"], 4),
                "fpr": round(m["false_positive_rate"], 4),
                "precision": round(m["precision"], 4),
                "f1": round(m["f1_score"], 4),
                "youden": round(m["recall"] - m["false_positive_rate"], 4),
            }
        )
    f1_opt = max(rows, key=lambda r: r["f1"])
    youden_opt = max(rows, key=lambda r: r["youden"])
    fpr05 = max((r for r in rows if r["fpr"] <= 0.05), key=lambda r: r["detection"])
    return {
        "f1_optimal": f1_opt,
        "youden_optimal": youden_opt,
        "fpr05_max_detection": fpr05,
    }


def main() -> None:
    r = json.loads(RESULTS.read_text(encoding="utf-8"))

    # Labels are not stored in results.json; reload them from the split files.
    RUN = (
        Path(__file__).resolve().parent.parent.parent
        / "artifacts"
        / "training_xgboost_fix"
        / "splits"
    )

    def load_labels(name: str) -> list[int]:
        rows = []
        with open(RUN / name, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return [row["label"] for row in rows]

    jbb_y = load_labels("external_eval.jsonl")
    test_y = load_labels("test.jsonl")

    surface: dict = {}
    for cfg in CONFIGS:
        surface[cfg] = {}
        for model in ("rf", "xgb"):
            entry = r["conditions"][cfg]["models"][model]
            surface[cfg][model] = {
                "jbb": operating_points(entry["scores"]["jbb"], jbb_y),
                "test": operating_points(entry["scores"]["test"], test_y),
            }

    r["threshold_surface"] = surface
    RESULTS.write_text(json.dumps(r, indent=2), encoding="utf-8")

    for model in ("rf", "xgb"):
        print(f"\n== {model.upper()} JBB operating points ==")
        print(
            f"{'config':<16} {'f1-opt t':<9} {'det':>6} {'fpr':>6} | {'youden t':<9} {'det':>6} {'fpr':>6} | {'fpr<=5% t':<9} {'det':>6} {'fpr':>6} {'prec':>6}"
        )
        for cfg in CONFIGS:
            s = surface[cfg][model]["jbb"]
            f1, yj, f5 = s["f1_optimal"], s["youden_optimal"], s["fpr05_max_detection"]
            print(
                f"{cfg:<16} {f1['threshold']:<9} {f1['detection']:>6.3f} {f1['fpr']:>6.3f} | "
                f"{yj['threshold']:<9} {yj['detection']:>6.3f} {yj['fpr']:>6.3f} | "
                f"{f5['threshold']:<9} {f5['detection']:>6.3f} {f5['fpr']:>6.3f} {f5['precision']:>6.3f}"
            )


if __name__ == "__main__":
    main()
