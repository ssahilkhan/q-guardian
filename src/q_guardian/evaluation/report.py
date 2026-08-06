"""Serialization and Markdown rendering for evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from q_guardian.evaluation.pipeline import ALL_PROVIDERS

_METRIC_LABELS = {
    "accuracy": "Accuracy",
    "precision": "Precision",
    "recall": "Recall",
    "f1_score": "F1",
    "roc_auc": "ROC-AUC",
    "pr_auc": "PR-AUC",
    "expected_calibration_error": "ECE",
    "brier_score": "Brier",
    "matthews_corrcoef": "MCC",
}

_PROVIDER_LABELS = {
    "fusion": "Hybrid Fusion",
    "rule-engine": "Rule Engine",
    "isolation-forest": "Isolation Forest",
    "random-forest": "Random Forest",
    "qsvm": "Quantum QSVM",
}


def write_json(report: dict[str, Any], path: str | Path) -> None:
    """Write a benchmark report to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def to_markdown(report: dict[str, Any]) -> str:
    """Render a benchmark report as Markdown for humans/CI."""

    def _fmt(value: Any) -> str:
        if isinstance(value, dict):
            mean = value.get("mean", 0.0)
            return f"{float(mean):.4f}"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    lines: list[str] = []
    lines.append("# Q-Guardian Detection Benchmark Report")
    lines.append("")

    config = report.get("config", {})
    dataset = report.get("dataset", {})
    lines.append("## Configuration")
    lines.append("")
    lines.append("| Setting | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| K-fold | {config.get('k')} |")
    lines.append(f"| Seed | {config.get('seed')} |")
    lines.append(f"| Threshold | {config.get('threshold')} |")
    for key, value in config.get("evaluator", {}).items():
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append("## Dataset")
    lines.append("")
    lines.append(f"- Total samples: {dataset.get('total')}")
    lines.append(f"- Threats: {dataset.get('threats')}")
    lines.append(f"- Benign: {dataset.get('benign')}")
    lines.append(f"- Threat ratio: {dataset.get('threat_ratio')}")
    categories = dataset.get("categories", {})
    if categories:
        lines.append(
            "- Categories: "
            + ", ".join(f"{cat} ({count})" for cat, count in sorted(categories.items()))
        )
    lines.append("")

    cv = report.get("cross_validation", {})
    lines.append("## Cross-Validation Results")
    lines.append("")
    fold_rows = cv.get("folds", [])
    if fold_rows:
        lines.append("| Fold | Train | Test | ROC-AUC | F1 | Accuracy |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in fold_rows:
            lines.append(
                f"| {row['fold']} | {row['train_size']} | {row['test_size']} "
                f"| {row['fusion_roc_auc']:.4f} | {row['fusion_f1']:.4f} "
                f"| {row['fusion_accuracy']:.4f} |"
            )
        lines.append("")

    metrics = cv.get("metrics", {})
    if metrics:
        lines.append("### Mean metrics (std)")
        lines.append("")
        header = "| Provider | " + " | ".join(_METRIC_LABELS.values()) + " |"
        lines.append(header)
        lines.append("| --- |" + " --- |" * len(_METRIC_LABELS))
        for provider in ["fusion", *ALL_PROVIDERS]:
            if provider not in metrics:
                continue
            name = _PROVIDER_LABELS.get(provider, provider)
            cells = []
            for key in _METRIC_LABELS:
                metric = metrics[provider].get(key)
                if metric is None:
                    cells.append("-")
                else:
                    cells.append(f"{metric['mean']:.4f}±{metric['std']:.4f}")
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines.append("")

    ranking = cv.get("roc_auc_ranking", [])
    if ranking:
        lines.append("### ROC-AUC ranking")
        lines.append("")
        for i, row in enumerate(ranking, start=1):
            lines.append(
                f"{i}. **{_PROVIDER_LABELS.get(row['provider'], row['provider'])}** "
                f"— {row['mean_roc_auc']:.4f}"
            )
        lines.append("")

    ablation = report.get("ablation", {})
    if ablation:
        lines.append("## Ablation (fusion with one provider removed)")
        lines.append("")
        lines.append("| Removed provider | Fused ROC-AUC | Δ AUC | F1 | Δ F1 |")
        lines.append("| --- | --- | --- | --- | --- |")
        summary = report.get("ablation_summary", {})
        full_auc = summary.get("full_fusion_roc_auc", 0.0)
        full_f1 = summary.get("full_fusion_f1", 0.0)
        for provider in ALL_PROVIDERS:
            if provider not in ablation:
                continue
            entry = ablation[provider]
            auc = entry["fusion_roc_auc"]["mean"]
            f1 = entry["fusion_f1_mean"]
            lines.append(
                f"| {_PROVIDER_LABELS.get(provider, provider)} "
                f"| {auc:.4f} | {full_auc - auc:+.4f} "
                f"| {f1:.4f} | {full_f1 - f1:+.4f} |"
            )
        lines.append("")
        redundant = summary.get("redundant_providers", [])
        if redundant:
            lines.append(
                "Redundant providers (removal lowers neither AUC nor F1): "
                + ", ".join(_PROVIDER_LABELS.get(p, p) for p in redundant)
            )
            lines.append("")
        recommendation = summary.get("recommendation", "")
        if recommendation:
            lines.append("### Recommendation")
            lines.append("")
            lines.append(recommendation)
            lines.append("")

    return "\n".join(lines) + "\n"


def write_markdown(report: dict[str, Any], path: str | Path) -> None:
    """Render and write a benchmark report to a Markdown file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_markdown(report), encoding="utf-8")
