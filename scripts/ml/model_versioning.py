"""Model versioning and metadata for arm_d checkpoint.

Creates a standardized model card and version manifest for the arm_d
HybridEvaluator checkpoint, including:
- Semantic version
- Training data provenance
- Feature contract
- Hyperparameters
- Evaluation results summary
- Reproducibility info (git commit, env)
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARM_D_DIR = ROOT / "artifacts" / "training_arm_d"
OUT_DIR = ROOT / "artifacts" / "models" / "arm_d_v1"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get_git_info() -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        short = commit[:8]
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
        return {
            "commit": commit,
            "short_commit": short,
            "branch": branch,
            "working_tree_clean": not dirty,
        }
    except Exception:
        return {"commit": "unknown", "short_commit": "unknown", "branch": "unknown"}


def get_python_env() -> dict:
    return {
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
    }


def main() -> int:
    # Load existing params
    params_path = ARM_D_DIR / "params.json"
    with open(params_path) as f:
        params = json.load(f)

    git_info = get_git_info()

    # Build model card
    model_card = {
        "model_name": "qguardian-arm-d-hybrid-evaluator",
        "version": "1.0.0",
        "version_date": datetime.now(UTC).isoformat(),
        "description": (
            "Hybrid quantum-classical threat evaluator trained on arm_d "
            "diverse training set (6269 samples: 4006 malicious / 2263 benign). "
            "Combines rule engine, Isolation Forest, Random Forest, and XGBoost "
            "with weighted fusion. Uses 43-dim handcrafted features + 384-dim "
            "sentence embeddings (427 total)."
        ),
        "training": {
            "dataset": "arm_d",
            "dataset_composition": {
                "control": 2425,
                "trustair_jailbreaks": 1405,
                "jailbreakv": 2000,
                "harmful_behaviors_filtered": 439,
            },
            "total_samples": 6269,
            "malicious": 4006,
            "benign": 2263,
            "feature_contract": "extended-427",
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "hyperparameters": params,
        },
        "evaluation": {
            "internal_test": {
                "samples": 116,
                "fusion_roc_auc": 0.931,
                "fusion_f1_at_0.50": 0.740,
                "fusion_f1_at_0.20": 0.879,
            },
            "jbb_external": {
                "samples": 200,
                "fusion_roc_auc": 0.783,
                "fusion_f1_at_0.50": 0.721,
                "fusion_f1_at_0.20": 0.680,
            },
            "calibration": {
                "validation_optimal_threshold": 0.15,
                "transfers_to_jbb": False,
                "jbb_fpr_at_val_optimal": 0.700,
            },
            "adversarial_robustness": {
                "auc_drop_on_perturbations": 0.21,
            },
        },
        "providers": {
            "rule-engine": {"weight": 0.15, "type": "rule-based"},
            "isolation-forest": {"weight": 0.10, "type": "anomaly"},
            "random-forest": {"weight": 0.35, "type": "classifier"},
            "xgboost": {"weight": 0.25, "type": "classifier"},
            "qsvm": {"weight": 0.15, "type": "quantum", "enabled": False},
        },
        "reproducibility": {
            "git": git_info,
            "python_env": get_python_env(),
            "checkpoint_path": str(ARM_D_DIR / "hybrid_evaluator.joblib"),
            "params_path": str(params_path),
        },
        "license": "Proprietary - Q-Guardian internal use only",
        "contact": "ml-team@qguardian.internal",
    }

    # Write model card
    (OUT_DIR / "model_card.json").write_text(json.dumps(model_card, indent=2))

    # Write simplified version manifest (for automated tooling)
    manifest = {
        "model": "qguardian-arm-d-hybrid-evaluator",
        "version": "1.0.0",
        "git_commit": git_info.get("short_commit"),
        "feature_contract": "extended-427",
        "training_samples": 6269,
        "checkpoint_sha256": None,  # could compute if needed
    }
    (OUT_DIR / "version_manifest.json").write_text(json.dumps(manifest, indent=2))

    # Copy checkpoint files to versioned directory
    import shutil

    shutil.copy2(ARM_D_DIR / "hybrid_evaluator.joblib", OUT_DIR / "hybrid_evaluator.joblib")
    shutil.copy2(ARM_D_DIR / "params.json", OUT_DIR / "params.json")

    print(f"Model versioned at {OUT_DIR}")
    print(f"  Version: {model_card['version']}")
    print(f"  Git: {git_info.get('short_commit')}")
    print(f"  Feature contract: {model_card['training']['feature_contract']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
