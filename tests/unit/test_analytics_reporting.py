"""Unit tests for report generation (JSON/CSV/Markdown)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from q_guardian.analytics.aggregator import aggregate_results
from q_guardian.analytics.comparison import compare_classical_quantum
from q_guardian.analytics.compatibility import CompatibilityReport
from q_guardian.analytics.generalization import analyze_generalization
from q_guardian.analytics.models import MetricStats, NormalizedResult
from q_guardian.analytics.reporting import (
    CrossDatasetReport,
    build_leaderboards,
    generate_report,
)


def _result(
    dataset_id: str,
    *,
    roc: float = 0.85,
    scope: str = "internal",
    source: str = "benchmark",
    samples: int = 100,
) -> NormalizedResult:
    return NormalizedResult(
        dataset_id=dataset_id,
        name=dataset_id,
        source=source,
        scope=scope,
        samples=samples,
        fold_count=3,
        threshold=0.5,
        metrics={"fusion": {"roc_auc": MetricStats.from_scalar(roc)}},
    )


def _report() -> CrossDatasetReport:
    results = [
        _result("ds-a", roc=0.85),
        _result("ds-b", roc=0.93, scope="external"),
    ]
    aggregation = aggregate_results(results, mode="macro")
    leaderboards = build_leaderboards(results)
    comparison = compare_classical_quantum(results)
    generalization = analyze_generalization(results)
    return generate_report(
        results=results,
        mode="macro",
        compatibility=CompatibilityReport(),
        aggregation=aggregation,
        leaderboards=leaderboards,
        comparison=comparison,
        generalization=generalization,
    )


class TestReportDocument:
    def test_as_dict_contains_all_sections(self) -> None:
        data = _report().as_dict()

        assert data["report_type"] == "cross-dataset-analytics"
        assert "generated_at" in data
        assert "inputs" in data
        assert data["compatibility"]["compatible"] is True
        assert data["aggregation"]["mode"] == "macro"
        assert "roc_auc" in data["leaderboards"]
        assert data["comparison"] is not None
        assert data["generalization"] is not None

    def test_to_markdown_renders_tables(self) -> None:
        md = _report().to_markdown()

        assert "# Q-Guardian Cross-Dataset Analytics Report" in md
        assert "## Cross-dataset aggregates" in md
        assert "## Classical vs quantum" in md
        assert "## Generalization" in md
        assert "## Cross-dataset ranking" in md

    def test_to_csv_has_metric_rows(self) -> None:
        csv_lines = _report().to_csv().splitlines()

        assert csv_lines[0].startswith("report_type,dataset_id")
        assert any("aggregate" in line and "roc_auc" in line for line in csv_lines)


class TestWrite:
    def test_writes_three_formats(self, tmp_path) -> None:
        report = _report()

        report.write_json(tmp_path / "r.json")
        report.write_markdown(tmp_path / "r.md")
        report.write_csv(tmp_path / "r.csv")

        assert (tmp_path / "r.json").exists()
        assert (tmp_path / "r.md").exists()
        assert (tmp_path / "r.csv").exists()
        json_doc = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
        assert json_doc["report_type"] == "cross-dataset-analytics"


class TestService:
    def test_analyze_pipeline_end_to_end(self) -> None:
        from q_guardian.analytics import CrossDatasetAnalytics

        service = CrossDatasetAnalytics(aggregation_mode="macro")
        report = service.analyze(
            [
                {
                    "dataset": {"id": "ds-a"},
                    "benchmark": {
                        "config": {"seed": 1, "threshold": 0.5},
                        "dataset": {"total": 100},
                        "cross_validation": {
                            "fold_count": 3,
                            "metrics": {
                                "fusion": {"roc_auc": {"mean": 0.85, "std": 0.05}},
                                "isolation-forest": {"roc_auc": {"mean": 0.7}},
                            },
                        },
                    },
                },
                {
                    "config": {"samples": 90, "seed": 1, "threshold": 0.5},
                    "cross_validation": {
                        "fold_count": 3,
                        "metrics": {
                            "fusion": {"roc_auc": {"mean": 0.9, "std": 0.02}},
                            "qsvm": {"roc_auc": {"mean": 0.8}},
                        },
                    },
                },
            ]
        )

        assert report.aggregation is not None
        assert report.aggregation.provider_ids == ["fusion", "isolation-forest", "qsvm"]
        assert report.compatibility.compatible is True

    def test_strict_mode_raises_on_incompatible(self) -> None:
        from q_guardian.analytics import CrossDatasetAnalytics

        service = CrossDatasetAnalytics(strict=True)
        try:
            service.analyze([])
        except ValueError as exc:
            assert "No results" in str(exc)
        else:
            raise AssertionError("expected an error for empty input")

    def test_save_and_load_round_trip(self, tmp_path) -> None:
        from q_guardian.analytics import CrossDatasetAnalytics

        service = CrossDatasetAnalytics()
        report = service.analyze(
            [
                {
                    "dataset": {"id": "ds-a"},
                    "benchmark": {
                        "config": {"seed": 1, "threshold": 0.5},
                        "dataset": {"total": 100},
                        "cross_validation": {
                            "fold_count": 3,
                            "metrics": {"fusion": {"roc_auc": {"mean": 0.85}}},
                        },
                    },
                }
            ]
        )
        out_dir: Path = tmp_path / "analytics"
        paths = service.save(report, out_dir)
        loaded = service.load_report(paths["json"])

        assert loaded["report_type"] == "cross-dataset-analytics"
        assert loaded["aggregation"]["providers"]["fusion"]["metrics"]["roc_auc"]["mean"] == 0.85

    def test_invalid_aggregation_mode_raises(self) -> None:
        from q_guardian.analytics import CrossDatasetAnalytics

        try:
            CrossDatasetAnalytics(aggregation_mode="banana")
        except ValueError:
            pass
        else:
            raise AssertionError("expected a ValueError for unsupported mode")
