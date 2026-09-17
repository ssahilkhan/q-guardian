"""Artifact-root resolution for the product workflow.

The product workflow (datasets, training runs, security scans, reports) is
disk-backed: every run persists a directory of real artifacts under a root
that honours the same ``QGUARDIAN_ARTIFACTS_DIR`` override used by the
research reader, falling back to the project root (repository CWD or package
source tree). No MongoDB is required for these features.
"""

from __future__ import annotations

import os
from pathlib import Path

ARTIFACTS_ENV = "QGUARDIAN_ARTIFACTS_DIR"
TRAINING_SUBDIR = "artifacts/training"
DATASETS_SUBDIR = "artifacts/datasets"
SCANS_SUBDIR = "artifacts/scans"
REPORTS_SUBDIR = "reports"
CACHE_DIR = "~/.qguardian/benchmark"


def artifacts_root() -> Path:
    """Return the directory that owns all product artifacts.

    Prefers ``QGUARDIAN_ARTIFACTS_DIR`` (so tests and deployments can isolate
    artifacts), then the process working directory when it looks like the
    project root, then the source-tree location of the package.
    """
    override = os.environ.get(ARTIFACTS_ENV)
    if override:
        return Path(override).expanduser().resolve()
    cwd = Path.cwd().resolve()
    if (cwd / "src" / "q_guardian").is_dir():
        return cwd
    return Path(__file__).resolve().parents[4]


def training_root() -> Path:
    """Return the training-run root directory."""
    return artifacts_root() / TRAINING_SUBDIR


def datasets_root() -> Path:
    """Return the dataset-preparation root directory."""
    return artifacts_root() / DATASETS_SUBDIR


def scans_root() -> Path:
    """Return the security-scan root directory."""
    return artifacts_root() / SCANS_SUBDIR


def reports_root() -> Path:
    """Return the generated-reports root directory."""
    return artifacts_root() / REPORTS_SUBDIR
