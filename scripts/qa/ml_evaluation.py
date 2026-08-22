"""ML model QA evaluation using real repository datasets.

Protocol (no production artifacts exist; this is a QA validation run):
1. Training pool : data/prompt_injections.jsonl (662 samples, binary label)
2. External test : data/benchmark_prompts.jsonl (62 samples, categorized)
3. Features      : production pipeline (normalize -> PromptFeatureExtractor
                   -> MLFeatureProvider, 43-dim vector)
4. Models        : RandomForest + XGBoost (seeded, stratified 80/20 split)
                   and IsolationForest trained on benign training split only.
5. Metrics       : confusion matrix, accuracy, precision/recall/F1,
                   FPR/FNR — reported separately for held-out validation
                   and the external set.

Usage:
    python -m scripts.qa.ml_evaluation

Outputs:
    docs/qa/ml_model_qa_report.json
    docs/qa/ml_model_qa_report.md
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from q_guardian.ml.config import MLConfig  # noqa: E402
from q_guardian.ml.feature_pipeline import MLFeatureProvider  # noqa: E402
from q_guardian.ml.models.anomaly import IsolationForestDetector  # noqa: E402
from q_guardian.ml.models.classifier import RandomForestThreatClassifier  # noqa: E402
from q_guardian.security.pipeline import PromptFeatureExtractor, PromptNormalizer  # noqa: E402

SEED = 42
POOL_PATH = ROOT / "data" / "prompt_injections.jsonl"
EXTERNAL_PATH = ROOT / "data" / "benchmark_prompts.jsonl"
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


def _package_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return str(tomllib.load(f)["project"]["version"])


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "text" in rec and "label" in rec:
                records.append(rec)
    return records


class FeatureCache:
    """Extracts and caches the 43-dim ML feature vector per prompt."""

    def __init__(self) -> None:
        self._normalizer = PromptNormalizer()
        self._base_extractor = PromptFeatureExtractor()
        self._provider = MLFeatureProvider(config=MLConfig(random_state=SEED))

    def vector(self, text: str) -> list[float]:
        normalized = self._normalizer.normalize(text)
        base = self._base_extractor.extract(normalized)
        feats = asyncio.run(self._provider.extract_features(normalized, base))
        return [float(v) for v in feats["feature_vector"]]


def build_dataset(
    records: list[dict[str, Any]], cache: FeatureCache
) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([cache.vector(rec["text"]) for rec in records], dtype=np.float64)
    y = np.array([int(rec["label"]) for rec in records], dtype=np.int32)
    return x, y


def stratified_split(
    x: np.ndarray, y: np.ndarray, test_ratio: float = 0.2
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(SEED)
    train_idx: list[int] = []
    val_idx: list[int] = []

    for cls in np.unique(y):
        cls_indices = np.where(y == cls)[0]
        shuffled = rng.permutation(cls_indices)
        n_val = max(1, int(len(shuffled) * test_ratio))
        val_idx.extend(shuffled[:n_val].tolist())
        train_idx.extend(shuffled[n_val:].tolist())

    train_idx_arr = np.array(train_idx)
    rng.shuffle(train_idx_arr)

    return (
        x[train_idx_arr],
        y[train_idx_arr],
        x[np.array(val_idx)],
        y[np.array(val_idx)],
    )


def confusion(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, int]:
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def metrics_from(cm: dict[str, int]) -> dict[str, float]:
    def div(n: float, d: float) -> float:
        return round(n / d, 4) if d else 0.0

    precision = div(cm["tp"], cm["tp"] + cm["fp"])
    recall = div(cm["tp"], cm["tp"] + cm["fn"])
    f1 = div(2 * precision * recall, precision + recall) if precision + recall else 0.0
    total = cm["tp"] + cm["tn"] + cm["fp"] + cm["fn"]
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": div(cm["tp"] + cm["tn"], total),
        "false_positive_rate": div(cm["fp"], cm["fp"] + cm["tn"]),
        "false_negative_rate": div(cm["fn"], cm["fn"] + cm["tp"]),
    }


async def evaluate_classifier(
    name: str,
    clf: Any,
    x_val: np.ndarray,
    y_val: np.ndarray,
    x_ext: np.ndarray,
    y_ext: np.ndarray,
) -> dict[str, Any]:
    async def predict_all(x: np.ndarray) -> np.ndarray:
        """Map classifier output to binary labels: benign->0, anything else->1."""
        preds = []
        for row in x:
            result = await clf.predict(row.tolist())
            label = result["predicted_class"]
            preds.append(0 if label == "benign" else 1)
        return np.array(preds, dtype=np.int32)

    val_pred = await predict_all(x_val)
    ext_pred = await predict_all(x_ext)

    return {
        "model": name,
        "trained_samples": int(clf.metadata.training_samples),
        "validation": {
            "confusion_matrix": confusion(y_val, val_pred),
            **metrics_from(confusion(y_val, val_pred)),
        },
        "external": {
            "confusion_matrix": confusion(y_ext, ext_pred),
            **metrics_from(confusion(y_ext, ext_pred)),
        },
    }


def evaluate_anomaly(
    detector: IsolationForestDetector, x: np.ndarray, y: np.ndarray
) -> dict[str, Any]:
    scores = detector.model.decision_function(x)
    # Threshold at 0 (sklearn convention): score < 0 => anomaly => predicted threat.
    preds = (scores < 0).astype(np.int32)
    cm = confusion(y, preds)
    return {"model": "isolation-forest", **{"confusion_matrix": cm}, **metrics_from(cm)}


def main() -> int:
    DOCS_QA.mkdir(parents=True, exist_ok=True)
    cache = FeatureCache()

    pool_records = load_jsonl(POOL_PATH)
    external_records = load_jsonl(EXTERNAL_PATH)

    print(f"Pool samples: {len(pool_records)}")
    print(f"External samples: {len(external_records)}")

    x_pool, y_pool = build_dataset(pool_records, cache)
    x_ext, y_ext = build_dataset(external_records, cache)

    x_train, y_train, x_val, y_val = stratified_split(x_pool, y_pool)

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "version": _package_version(),
        "python": sys.version.split()[0],
        "seed": SEED,
        "datasets": {
            "training_pool": {
                "path": "data/prompt_injections.jsonl",
                "samples": len(pool_records),
                "benign": int(np.sum(y_pool == 0)),
                "malicious": int(np.sum(y_pool == 1)),
                "split": {"train": len(x_train), "validation": len(x_val)},
            },
            "external_test": {
                "path": "data/benchmark_prompts.jsonl",
                "samples": len(external_records),
                "benign": int(np.sum(y_ext == 0)),
                "malicious": int(np.sum(y_ext == 1)),
                "note": "held-out set; different distribution/curation than pool",
            },
        },
        "feature_pipeline": (
            "PromptNormalizer -> PromptFeatureExtractor -> MLFeatureProvider (43-dim)"
        ),
        "classifiers": [],
        "anomaly_detection": None,
        "limitations": [
            "No production model artifacts ship with the framework; these models "
            "were trained inside this QA run.",
            "Results are QA validation of the ML code path, NOT production claims.",
            "External set is small (62 samples); treat external metrics as indicative.",
            "Binary labels: pool uses 0=benign/1=malicious; classifier maps indices.",
        ],
    }

    config = MLConfig(random_state=SEED)

    rf = RandomForestThreatClassifier(config=config, n_estimators=200)
    rf.train(x_train.tolist(), y_train.tolist())
    rf_result = asyncio.run(evaluate_classifier("random-forest", rf, x_val, y_val, x_ext, y_ext))
    report["classifiers"].append(rf_result)
    print(f"RF done: val_f1={rf_result['validation']['f1']} ext_f1={rf_result['external']['f1']}")

    try:
        import xgboost  # noqa: F401

        from q_guardian.ml.models.classifier import XGBoostThreatClassifier

        xgb = XGBoostThreatClassifier(config=config, n_estimators=200, max_depth=6)
        xgb.train(x_train.tolist(), y_train.tolist())
        xgb_result = asyncio.run(evaluate_classifier("xgboost", xgb, x_val, y_val, x_ext, y_ext))
        report["classifiers"].append(xgb_result)
        print(
            f"XGB done: val_f1={xgb_result['validation']['f1']}"
            f" ext_f1={xgb_result['external']['f1']}"
        )
    except ImportError:
        report.setdefault("limitations", []).append(
            "XGBoost not installed; XGBoost evaluation skipped."
        )

    benign_train = x_train[y_train == 0]
    iso = IsolationForestDetector(config=config, contamination=0.2, n_estimators=200)
    iso.train(benign_train.tolist())

    iso_val = evaluate_anomaly(iso, x_val, y_val)
    iso_ext = evaluate_anomaly(iso, x_ext, y_ext)
    report["anomaly_detection"] = {
        "trained_on": "benign training split only (unsupervised)",
        "validation": iso_val,
        "external": iso_ext,
    }
    print(f"IF done: val_acc={iso_val['accuracy']} ext_acc={iso_ext['accuracy']}")

    json_path = DOCS_QA / "ml_model_qa_report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(f"JSON report: {json_path}")
    return 0


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# ML Model QA Evaluation Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Commit: `{report['commit']}`",
        f"- Version: {report['version']}",
        f"- Python: {report['python']}",
        f"- Seed: {report['seed']} (deterministic)",
        f"- Features: {report['feature_pipeline']}",
        "",
        "## Datasets",
        "",
        "| Dataset | Samples | Benign | Malicious | Role |",
        "|---|---|---|---|---|",
        f"| prompt_injections.jsonl | {report['datasets']['training_pool']['samples']} "
        f"| {report['datasets']['training_pool']['benign']} "
        f"| {report['datasets']['training_pool']['malicious']} | train/validation pool |",
        f"| benchmark_prompts.jsonl | {report['datasets']['external_test']['samples']} "
        f"| {report['datasets']['external_test']['benign']} "
        f"| {report['datasets']['external_test']['malicious']} | external held-out test |",
        "",
        "> **Status: EXPERIMENTAL/QA VALIDATION.** No production model artifacts ship with",
        "> the framework. These numbers validate the ML code path, not a shipped model.",
        "",
        "## Classifier Results",
        "",
    ]

    for clf_res in report["classifiers"]:
        lines += [
            f"### {clf_res['model']} ({clf_res['trained_samples']} training samples)",
            "",
            "| Split | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | FPR | FNR |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for split in ("validation", "external"):
            s = clf_res[split]
            cm = s["confusion_matrix"]
            lines.append(
                f"| {split} | {cm['tp']} | {cm['tn']} | {cm['fp']} | {cm['fn']} "
                f"| {s['accuracy']} | {s['precision']} | {s['recall']} | {s['f1']} "
                f"| {s['false_positive_rate']} | {s['false_negative_rate']} |"
            )
        lines.append("")

    ad = report.get("anomaly_detection")
    if ad:
        lines += [
            "## Anomaly Detection (Isolation Forest)",
            "",
            f"Trained on: {ad['trained_on']}",
            "",
            "| Split | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | FPR | FNR |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for split in ("validation", "external"):
            s = ad[split]
            cm = s["confusion_matrix"]
            lines.append(
                f"| {split} | {cm['tp']} | {cm['tn']} | {cm['fp']} | {cm['fn']} "
                f"| {s['accuracy']} | {s['precision']} | {s['recall']} | {s['f1']} "
                f"| {s['false_positive_rate']} | {s['false_negative_rate']} |"
            )
        lines.append("")

    lines += ["## Limitations", ""]
    for lim in report["limitations"]:
        lines.append(f"- {lim}")

    out = DOCS_QA / "ml_model_qa_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
