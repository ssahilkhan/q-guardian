"""Integration tests for the product-workflow API.

Covers dataset catalog/access, training-run inventory, security scans (real
CV job end to end), analytics and report generation. All artifacts are
isolated under a ``QGUARDIAN_ARTIFACTS_DIR`` temp root, so nothing touches the
real repository state and no external service is required. Synthetic artifacts
are used where a real job would need network access; the metric numbers are
asserted to be *present* and internally consistent, never fabricated by tests.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from q_guardian.evaluation.dataset import DEFAULT_SAMPLES
from q_guardian.training.artifacts import write_json, write_splits
from q_guardian.training.schema import DatasetRecord

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import AsyncClient

_ARTIFACTS_ENV = "QGUARDIAN_ARTIFACTS_DIR"
_SECRET_SENTINEL = "hf_TEST_SECRET_LEAK_CHECK_12345"


@pytest.fixture
def artifacts_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate product artifacts for the test and export the root path."""
    root = tmp_path / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(_ARTIFACTS_ENV, str(root))
    return root


def path(artifacts_root: Path, *parts: str) -> Path:
    return artifacts_root.joinpath(*parts)


def training_root(artifacts_root: Path) -> Path:
    return path(artifacts_root, "artifacts", "training")


def datasets_root(artifacts_root: Path) -> Path:
    return path(artifacts_root, "artifacts", "datasets")


def scans_root(artifacts_root: Path) -> Path:
    return path(artifacts_root, "artifacts", "scans")


def reports_root(artifacts_root: Path) -> Path:
    return path(artifacts_root, "reports")


def _record(text: str, label: int, category: str) -> DatasetRecord:
    return DatasetRecord(
        text=text,
        label=label,
        source="synthetic",
        split="default",
        category=category,
    )


def _synth_dataset_root(artifacts_root: Path, dataset_id: str = "syn-ds") -> Path:
    """Create a small balanced prepared dataset directory for a scan target."""
    benign = [sample for sample in DEFAULT_SAMPLES if sample.label == 0]
    malicious = [sample for sample in DEFAULT_SAMPLES if sample.label == 1]
    test = [_record(s.text, s.label, s.category) for s in (benign[:12] + malicious[:12])]
    external = [_record(s.text, s.label, s.category) for s in (benign[12:16] + malicious[12:16])]
    directory = datasets_root(artifacts_root) / dataset_id
    write_splits(directory, {"test": test, "external_eval": external})
    write_json(
        directory / "dataset_manifest.json",
        {
            "dataset_id": dataset_id,
            "dataset_name": "Synthetic Test Dataset",
            "pools": {
                "test": {"samples": len(test), "benign": 12, "malicious": 12},
                "external_eval": {"samples": len(external), "benign": 4, "malicious": 4},
            },
            "groups": {"test": [dataset_id], "external_eval": [dataset_id]},
        },
    )
    return directory


def _write_run(artifacts_root: Path, name: str, *, model: bool, evaluation: bool) -> Path:
    run_dir = training_root(artifacts_root) / name
    write_json(
        run_dir / "training_config.json",
        {
            "datasets": {
                "train": ["deepset-prompt-injections"],
                "validation": [],
                "test": [],
                "external_eval": [],
            },
            "model": {"quantum": False, "n_estimators": 50, "contamination": 0.2},
            "eval": {"threshold": 0.5},
        },
    )
    write_json(
        run_dir / "metrics.json",
        {"train_samples": 100, "validation_samples": 20, "elapsed_seconds": 3.2},
    )
    if model:
        (run_dir / "model").mkdir(parents=True, exist_ok=True)
    if evaluation:
        write_json(
            run_dir / "evaluation.json",
            {
                "matrix": [
                    {
                        "pool": "test",
                        "dataset": "deepset-prompt-injections",
                        "samples": 20,
                        "malicious": 10,
                        "benign": 10,
                        "available": True,
                        "accuracy": 0.95,
                        "detection_rate": 0.9,
                        "benign_rejection_rate": 1.0,
                        "f1": 0.92,
                        "roc_auc": 0.96,
                    }
                ],
                "summary": {"pools_evaluated": 1},
            },
        )
        (run_dir / "evaluation.md").write_text("# Evaluation\n", encoding="utf-8")
    return run_dir


def _benchmark_json(dataset_id: str, seed: int, roc_auc: float) -> dict[str, Any]:
    """A real-format benchmark inner report the analytics normalizer accepts."""
    return {
        "config": {
            "dataset": dataset_id,
            "seed": seed,
            "threshold": 0.5,
            "samples": 100,
            "fold_count": 3,
            "evaluator": {"quantum": False, "n_estimators": 50, "contamination": 0.2},
        },
        "cross_validation": {
            "fold_count": 3,
            "metrics": {
                "fusion": {
                    "roc_auc": {"mean": roc_auc, "std": 0.01},
                    "f1_score": {"mean": 0.85, "std": 0.02},
                    "recall": {"mean": 0.9, "std": 0.03},
                }
            },
        },
    }


def _write_scan_record(artifacts_root: Path, scan_id: str) -> dict[str, Any]:
    """Persist a finished synthetic scan record plus its summary artifacts."""
    result = {
        "target": "syn-ds",
        "kind": "cv",
        "dataset": {
            "total": 24,
            "threats": 12,
            "benign": 12,
            "threat_ratio": 0.5,
            "categories": {},
        },
        "metrics": {
            "fusion": {
                "recall": {"mean": 0.9167, "std": 0.05},
                "f1_score": {"mean": 0.9, "std": 0.04},
                "roc_auc": {"mean": 0.95, "std": 0.03},
            }
        },
        "scores_summary": {"samples": 24, "positives": 12, "negatives": 12},
        "verdict": {"level": "low_risk", "code": "low"},
        "verdict_reason": "Detection rate 0.917 meets the 80% threshold.",
        "note": "Verdict is derived from the measured fusion detection rate.",
    }
    write_json(
        scans_root(artifacts_root) / f"{scan_id}.job.json",
        {
            "job_id": scan_id,
            "kind": "scan.run",
            "label": "cv scan of syn-ds",
            "status": "succeeded",
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": "2026-01-01T00:00:01+00:00",
            "finished_at": "2026-01-01T00:00:30+00:00",
            "progress": ["loading evaluation pools", "scan complete"],
            "output_dir": str(scans_root(artifacts_root)),
            "result": result,
            "error": None,
        },
    )
    write_json(scans_root(artifacts_root) / f"{scan_id}.summary.json", result)
    (scans_root(artifacts_root) / f"{scan_id}.summary.md").write_text(
        "# Q-Guardian Security Scan\n", encoding="utf-8"
    )
    return result


async def _wait_for_job(
    client: AsyncClient, job_id: str, *, timeout: float = 180.0
) -> dict[str, Any]:
    """Poll a scan/training job until it reaches a terminal state."""
    elapsed = 0.0
    while elapsed < timeout:
        response = await client.get(f"/api/v1/scans/{job_id}")
        assert response.status_code == 200, response.text
        record = response.json()["data"]
        if record["status"] in {"succeeded", "failed"}:
            return record
        await asyncio.sleep(2.0)
        elapsed += 2.0
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDatasetEndpoints:
    async def test_catalog_lists_with_access(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.get("/api/v1/datasets")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) > 0
        assert any(entry["dataset_id"] == "deepset-prompt-injections" for entry in data)
        for entry in data:
            assert "access" in entry
            assert "access_type" in entry["access"]
            assert "requires_token" in entry["access"]

    async def test_auth_status_reports_config(
        self, artifacts_root: Path, monkeypatch: pytest.MonkeyPatch, authorized_client: AsyncClient
    ) -> None:
        monkeypatch.delenv("HF_TOKEN", raising=False)
        response = await authorized_client.get("/api/v1/datasets/auth-status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["provider"] == "huggingface"
        assert data["token_env_var"] == "HF_TOKEN"
        assert data["token_configured"] is False
        assert _SECRET_SENTINEL not in response.text

    async def test_auth_status_never_leaks_token(
        self, artifacts_root: Path, monkeypatch: pytest.MonkeyPatch, authorized_client: AsyncClient
    ) -> None:
        monkeypatch.setenv("HF_TOKEN", _SECRET_SENTINEL)
        response = await authorized_client.get("/api/v1/datasets/auth-status")
        assert response.status_code == 200
        assert response.json()["data"]["token_configured"] is True
        assert _SECRET_SENTINEL not in response.text
        assert "hf_TEST_SECRET" not in response.text

    async def test_dataset_detail(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.get("/api/v1/datasets/deepset-prompt-injections")
        assert response.status_code == 200
        entry = response.json()["data"]
        assert entry["dataset_id"] == "deepset-prompt-injections"
        assert "train" in entry["groups"]
        assert isinstance(entry["access"]["access_type"], str)

    async def test_dataset_access_status(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.get("/api/v1/datasets/deepset-prompt-injections/access")
        assert response.status_code == 200
        info = response.json()["data"]
        assert info["dataset_id"] == "deepset-prompt-injections"
        assert info["access_type"] in {"public", "gated"}

    async def test_unknown_dataset_404(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        detail = await authorized_client.get("/api/v1/datasets/does-not-exist")
        assert detail.status_code == 404
        access = await authorized_client.get("/api/v1/datasets/does-not-exist/access")
        assert access.status_code == 404

    async def test_prepared_empty_without_artifacts(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.get("/api/v1/datasets/prepared")
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_prepare_unknown_dataset_404(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.post("/api/v1/datasets/does-not-exist/prepare")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTrainingEndpoints:
    async def test_runs_list_and_detail(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        _write_run(artifacts_root, "run-one", model=True, evaluation=True)
        _write_run(artifacts_root, "run-mini", model=False, evaluation=False)

        listing = await authorized_client.get("/api/v1/training")
        assert listing.status_code == 200
        names = {run["name"] for run in listing.json()["data"]}
        assert {"run-one", "run-mini"} <= names
        trained = next(run for run in listing.json()["data"] if run["name"] == "run-one")
        assert trained["model"]["exists"] is True
        assert trained["evaluation_exists"] is True

        detail = await authorized_client.get("/api/v1/training/run-one")
        assert detail.status_code == 200
        run = detail.json()["data"]
        assert run["config"]["datasets"]["train"] == ["deepset-prompt-injections"]
        assert run["evaluation"]["matrix"][0]["detection_rate"] == 0.9

    async def test_create_with_unknown_dataset_rejected(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.post(
            "/api/v1/training", json={"dataset_ids": ["not-a-real-dataset"]}
        )
        assert response.status_code == 400
        assert "unknown dataset" in response.json()["detail"]

    async def test_evaluate_without_model_rejected(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        _write_run(artifacts_root, "run-mini", model=False, evaluation=False)
        response = await authorized_client.post("/api/v1/training/run-mini/evaluate")
        assert response.status_code == 400
        assert "has no saved model" in response.json()["detail"]

    async def test_unknown_run_404(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        listing = await authorized_client.get("/api/v1/training/does-not-exist")
        assert listing.status_code == 404
        evaluate = await authorized_client.post("/api/v1/training/does-not-exist/evaluate")
        assert evaluate.status_code == 404

    async def test_schema_validation(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.post(
            "/api/v1/training", json={"quantum_shots": -5}
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestScanEndpoints:
    async def test_rejects_unknown_target(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.post(
            "/api/v1/scans", json={"type": "cv", "target": "missing-target"}
        )
        assert response.status_code == 400
        assert "unknown scan target" in response.json()["detail"]

    async def test_schema_validation(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        assert (
            await authorized_client.post("/api/v1/scans", json={})
        ).status_code == 422
        assert (
            await authorized_client.post(
                "/api/v1/scans", json={"type": "cv", "target": "syn-ds", "k": 1}
            )
        ).status_code == 422

    async def test_history_recovers_disk_records(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        _write_scan_record(artifacts_root, "scan-rec-0001")
        response = await authorized_client.get("/api/v1/scans")
        assert response.status_code == 200
        history = response.json()["data"]
        assert any(scan["scan_id"] == "scan-rec-0001" for scan in history)
        record = next(scan for scan in history if scan["scan_id"] == "scan-rec-0001")
        assert record["verdict"]["level"] == "low_risk"
        assert record["metrics"]["fusion"]["recall"]["mean"] == 0.9167

    async def test_unknown_scan_404(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.get("/api/v1/scans/no-such-scan")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAnalyticsEndpoints:
    async def test_summary_over_persisted_artifacts(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        _write_run(artifacts_root, "run-one", model=True, evaluation=True)
        _write_run(artifacts_root, "run-mini", model=False, evaluation=False)
        _write_scan_record(artifacts_root, "scan-analytics-01")

        response = await authorized_client.get("/api/v1/analytics/summary")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["datasets"]["catalog"] > 0
        assert data["training"]["runs"] == 2
        assert data["training"]["trained_models"] == 1
        assert data["scans"]["total"] >= 1
        assert data["scans"]["by_verdict"]["low_risk"] >= 1
        assert data["scans"]["avg_detection_rate"] is not None
        assert len(data["timeline"]) == 14
        assert data["timeline"][-1]["date"] == date.today().isoformat()

    async def test_cross_analytics_over_report_files(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        write_json(
            training_root(artifacts_root) / "run-a" / "benchmark.json",
            _benchmark_json("dset-a", seed=1, roc_auc=0.96),
        )
        write_json(
            training_root(artifacts_root) / "run-b" / "benchmark.json",
            _benchmark_json("dset-b", seed=2, roc_auc=0.92),
        )
        response = await authorized_client.post(
            "/api/v1/analytics/cross",
            json={
                "files": [
                    "artifacts/training/run-a/benchmark.json",
                    "artifacts/training/run-b/benchmark.json",
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["report_type"] == "cross-dataset-analytics"
        assert len(data["inputs"]) == 2

    async def test_cross_analytics_rejects_escaped_paths(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.post(
            "/api/v1/analytics/cross", json={"files": ["../../secret.json"]}
        )
        assert response.status_code == 400

    async def test_cross_analytics_rejects_missing_files(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.post(
            "/api/v1/analytics/cross", json={"files": ["training/nope.json"]}
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReportEndpoints:
    async def test_generate_and_download_scan_report(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        _write_scan_record(artifacts_root, "scan-report-0001")

        generated = await authorized_client.post(
            "/api/v1/reports", json={"kind": "scan", "report_id": "scan:scan-report-0001"}
        )
        assert generated.status_code == 200, generated.text
        result = generated.json()["data"]
        formats = {entry["format"] for entry in result["entries"]}
        assert {"md", "json"} <= formats

        download = await authorized_client.get(
            "/api/v1/reports/scan:scan-report-0001/download?format=md"
        )
        assert download.status_code == 200
        assert "Q-Guardian Security Scan" in download.text

        raw = await authorized_client.get(
            "/api/v1/reports/scan:scan-report-0001/download?format=json"
        )
        assert raw.status_code == 200
        assert json.loads(raw.text)["target"] == "syn-ds"

    async def test_generate_analytics_report_excludes_unrelated_json(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        write_json(
            training_root(artifacts_root) / "run-a" / "benchmark.json",
            _benchmark_json("dset-a", seed=1, roc_auc=0.96),
        )
        write_json(
            training_root(artifacts_root) / "run-b" / "benchmark.json",
            _benchmark_json("dset-b", seed=2, roc_auc=0.92),
        )
        write_json(scans_root(artifacts_root) / "scratch.json", {"hello": "world"})
        write_json(scans_root(artifacts_root) / "bad-pools.json", {"pools": 5})
        write_json(
            training_root(artifacts_root) / "junk-dir" / "notes.json",
            {"unrelated": True, "note": "clearly not a report artifact"},
        )
        write_json(
            scans_root(artifacts_root) / "decoy.job.json",
            {"job_id": "decoy", "status": "succeeded", "result": {"anything": 1}},
        )

        generated = await authorized_client.post(
            "/api/v1/reports", json={"kind": "analytics", "report_id": "analytics:gen-one"}
        )
        assert generated.status_code == 200, generated.text
        result = generated.json()["data"]
        formats = {entry["format"] for entry in result["entries"]}
        assert {"json", "md", "csv"} <= formats

        report_path = reports_root(artifacts_root) / "analytics" / "gen-one" / "report.json"
        assert report_path.is_file()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        input_ids = {entry["dataset_id"] for entry in report["inputs"]}
        # Only the two real benchmark artifacts; unrelated JSON never entered.
        assert input_ids == {"dset-a", "dset-b"}

    async def test_generate_training_report_requires_evaluation(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        _write_run(artifacts_root, "run-mini", model=False, evaluation=False)
        response = await authorized_client.post(
            "/api/v1/reports", json={"kind": "training", "report_id": "training:run-mini"}
        )
        assert response.status_code == 400

    async def test_unknown_report_404_and_invalid_kind(
        self, artifacts_root: Path, authorized_client: AsyncClient
    ) -> None:
        download = await authorized_client.get("/api/v1/reports/scan:missing/download?format=md")
        assert download.status_code == 404
        invalid = await authorized_client.post(
            "/api/v1/reports", json={"kind": "bogus", "report_id": "x"}
        )
        assert invalid.status_code == 422


# ---------------------------------------------------------------------------
# Full offline workflow (real jobs where no network is involved)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProductWorkflowSmoke:
    """Runs the dataset → scan → status → analytics → report flow with real
    computation for the parts that do not need network access."""

    async def test_end_to_end_flow(
        self,
        artifacts_root: Path,
        monkeypatch: pytest.MonkeyPatch,
        authorized_client: AsyncClient,
    ) -> None:
        directory = _synth_dataset_root(artifacts_root)
        assert (directory / "dataset_manifest.json").is_file()

        catalog = await authorized_client.get("/api/v1/datasets")
        assert catalog.status_code == 200 and len(catalog.json()["data"]) > 0

        prepared = await authorized_client.get("/api/v1/datasets/prepared")
        assert prepared.status_code == 200
        assert any(entry["id"] == "syn-ds" for entry in prepared.json()["data"])

        response = await authorized_client.post(
            "/api/v1/scans", json={"type": "cv", "target": "syn-ds", "k": 2}
        )
        assert response.status_code == 200, response.text
        job = response.json()["data"]
        job_id = job["job_id"]
        assert job_id
        assert job["status"] in {"queued", "running", "succeeded"}

        record = await _wait_for_job(authorized_client, job_id)
        assert record["status"] == "succeeded", record.get("error")
        assert record["scan_id"] == job_id
        assert record["verdict"]["level"] in {"low_risk", "review", "high_risk", "unknown"}
        assert record["metrics"]["fusion"]["recall"]["mean"] > 0
        assert record["scores_summary"]["samples"] >= 1

        output_dir = scans_root(artifacts_root)
        assert (output_dir / f"{job_id}.job.json").is_file()
        persisted = json.loads((output_dir / f"{job_id}.job.json").read_text(encoding="utf-8"))
        assert persisted["job_id"] == job_id
        assert persisted["status"] == "succeeded"
        assert (output_dir / f"{job_id}.summary.json").is_file()
        assert (output_dir / f"{job_id}.summary.md").is_file()

        history = await authorized_client.get("/api/v1/scans")
        assert any(scan["scan_id"] == job_id for scan in history.json()["data"])

        summary = await authorized_client.get("/api/v1/analytics/summary")
        assert summary.status_code == 200
        assert summary.json()["data"]["scans"]["total"] >= 1

        generated = await authorized_client.post(
            "/api/v1/reports", json={"kind": "scan", "report_id": f"scan:{job_id}"}
        )
        assert generated.status_code == 200, generated.text
        downloaded = await authorized_client.get(
            f"/api/v1/reports/scan:{job_id}/download?format=md"
        )
        assert downloaded.status_code == 200
        assert _SECRET_SENTINEL not in downloaded.text
        assert f"`{job_id}`" in downloaded.text

        # Setting a token must never surface anywhere in the flow.
        monkeypatch.setenv("HF_TOKEN", _SECRET_SENTINEL)
        for probe in (
            await authorized_client.get("/api/v1/datasets/auth-status"),
            await authorized_client.get("/api/v1/analytics/summary"),
            await authorized_client.get("/api/v1/scans"),
            await authorized_client.post(
                "/api/v1/reports", json={"kind": "scan", "report_id": f"scan:{job_id}"}
            ),
        ):
            assert _SECRET_SENTINEL not in probe.text
