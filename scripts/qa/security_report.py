"""Generate the security evaluation report (JSON + Markdown).

Runs the full security corpus through the real detection pipeline and writes:
- docs/qa/security_metrics.json  (machine-readable)
- docs/qa/security_metrics.md    (human-readable)

Usage:
    python -m scripts.qa.security_report
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.security.conftest import SecurityPipeline  # noqa: E402
from tests.security.corpus import (  # noqa: E402
    ALL_SAMPLES,
    BENIGN_SAMPLES,
    CorpusCategory,
    RecordStatus,
    SecuritySample,
)

from q_guardian.security.decision import SecurityDecisionEngine  # noqa: E402
from q_guardian.security.pipeline import (  # noqa: E402
    PromptFeatureExtractor,
    PromptNormalizer,
    PromptValidator,
    RuleEngine,
)

DOCS_QA = ROOT / "docs" / "qa"


def _git_commit() -> str:
    import shutil

    git = shutil.which("git") or r"C:\Program Files\Git\bin\git.exe"
    if not Path(git).exists():
        return "unknown"
    try:
        return subprocess.run(
            [git, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _scan(pipeline: SecurityPipeline, sample: SecuritySample) -> dict[str, object]:
    analysis = pipeline.scan(sample.text)
    return {
        "text": sample.text,
        "category": sample.category.value,
        "subcategory": sample.subcategory,
        "expected_flagged": sample.expect_flagged,
        "status": sample.status.value,
        "actual_decision": analysis.decision.value,
        "flagged": analysis.decision.value != "allow",
        "risk_score": analysis.risk_score,
        "rule_ids": [f.rule_id for f in analysis.findings],
    }


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def compute_metrics() -> dict[str, object]:
    """Run the corpus and compute all security metrics."""
    pipeline = SecurityPipeline(
        PromptNormalizer(),
        PromptValidator(),
        PromptFeatureExtractor(),
        RuleEngine(),
        SecurityDecisionEngine(),
    )

    results = [_scan(pipeline, s) for s in ALL_SAMPLES]

    tp = sum(1 for r in results if r["expected_flagged"] and r["flagged"])
    fn = sum(1 for r in results if r["expected_flagged"] and not r["flagged"])
    tn = sum(1 for r in results if not r["expected_flagged"] and not r["flagged"])
    fp = sum(1 for r in results if not r["expected_flagged"] and r["flagged"])

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    accuracy = _safe_div(tp + tn, tp + tn + fp + fn)

    per_category: dict[str, dict[str, float | int]] = {}
    for category in CorpusCategory:
        subset = [r for r in results if r["category"] == category.value]
        detected = sum(1 for r in subset if r["flagged"])
        required = [r for r in subset if r["status"] == RecordStatus.REQUIRED.value]
        req_detected = sum(1 for r in required if r["flagged"])
        per_category[category.value] = {
            "total": len(subset),
            "detected": detected,
            "detection_rate": round(_safe_div(detected, len(subset)), 4),
            "required_total": len(required),
            "required_detected": req_detected,
            "required_detection_rate": round(_safe_div(req_detected, len(required)), 4),
        }

    benign_accepted = sum(1 for r in results if r["category"] == "benign" and not r["flagged"])

    known_gaps = [
        {"subcategory": r["subcategory"], "text": r["text"]}
        for r in results
        if r["status"] == RecordStatus.KNOWN_GAP.value and not r["flagged"]
    ]
    false_positives = [
        {"subcategory": r["subcategory"], "text": r["text"], "decision": r["actual_decision"]}
        for r in results
        if not r["expected_flagged"] and r["flagged"]
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "version": _package_version(),
        "python": sys.version.split()[0],
        "pipeline": "rules-only (production default; no trained models shipped)",
        "corpus_size": len(results),
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(accuracy, 4),
            "benign_acceptance_rate": round(_safe_div(benign_accepted, len(BENIGN_SAMPLES)), 4),
            "false_positive_rate": round(_safe_div(fp, fp + tn), 4),
            "false_negative_rate": round(_safe_div(fn, fn + tp), 4),
        },
        "per_category": per_category,
        "known_gaps": known_gaps,
        "false_positives": false_positives,
        "results": results,
    }


def _package_version() -> str:
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return str(data["project"]["version"])


def write_markdown(report: dict[str, object]) -> Path:
    cm = report["confusion_matrix"]
    m = report["metrics"]

    lines = [
        "# Security Evaluation Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Commit: `{report['commit']}`",
        f"- Version: {report['version']}",
        f"- Python: {report['python']}",
        f"- Pipeline: {report['pipeline']}",
        f"- Corpus size: {report['corpus_size']}",
        "",
        "## Confusion Matrix",
        "",
        "| | Flagged | Allowed |",
        "|---|---|---|",
        f"| **Attack (expect flagged)** | TP={cm['tp']} | FN={cm['fn']} |",
        f"| **Benign (expect allowed)** | FP={cm['fp']} | TN={cm['tn']} |",
        "",
        "## Metrics",
        "",
        f"- Precision: {m['precision']}",
        f"- Recall: {m['recall']}",
        f"- F1: {m['f1']}",
        f"- Accuracy: {m['accuracy']}",
        f"- Benign acceptance rate: {m['benign_acceptance_rate']}",
        f"- False-positive rate: {m['false_positive_rate']}",
        f"- False-negative rate: {m['false_negative_rate']}",
        "",
        "## Per-Category Detection",
        "",
        "| Category | Total | Detected | Rate | Required | Required detected |",
        "|---|---|---|---|---|---|",
    ]
    for cat, stats in report["per_category"].items():  # type: ignore[union-attr]
        lines.append(
            f"| {cat} | {stats['total']} | {stats['detected']} | "
            f"{stats['detection_rate']} | {stats['required_total']} | "
            f"{stats['required_detected']} |"
        )

    lines += ["", "## Known Gaps (documented limitations)", ""]
    gaps = report["known_gaps"]
    if gaps:
        for gap in gaps:  # type: ignore[union-attr]
            lines.append(f"- `{gap['subcategory']}`: {gap['text']!r}")
    else:
        lines.append("- None")

    lines += ["", "## False Positives (benign flagged)", ""]
    fps = report["false_positives"]
    if fps:
        for fp in fps:  # type: ignore[union-attr]
            lines.append(f"- `{fp['subcategory']}` ({fp['decision']}): {fp['text']!r}")
    else:
        lines.append("- None")

    out = DOCS_QA / "security_metrics.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    DOCS_QA.mkdir(parents=True, exist_ok=True)
    report = compute_metrics()

    json_path = DOCS_QA / "security_metrics.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path = write_markdown(report)

    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
