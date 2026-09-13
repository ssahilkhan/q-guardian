"""Unit tests for the q-guardian analytics CLI subcommand."""

from __future__ import annotations

import json

import q_guardian.cli as cli


def _parse(argv: list[str]):
    return cli._build_parser().parse_args(argv)


class TestAnalyticsParser:
    def test_defaults(self) -> None:
        args = _parse(["analytics", "--reports", "r.json"])

        assert args.func is cli._cmd_analytics
        assert args.aggregation == "macro"
        assert args.no_strict is False
        assert args.output_dir == "reports/analytics"

    def test_flags(self) -> None:
        args = _parse(
            [
                "analytics",
                "--reports",
                "a.json",
                "b.json",
                "--aggregation",
                "weighted",
                "--no-strict",
                "--output-dir",
                "out",
            ]
        )

        assert args.reports == ["a.json", "b.json"]
        assert args.aggregation == "weighted"
        assert args.no_strict is True
        assert args.output_dir == "out"

    def test_invalid_aggregation_rejected(self) -> None:
        import pytest

        with pytest.raises(SystemExit):
            _parse(["analytics", "--reports", "a.json", "--aggregation", "banana"])


class TestCommandAnalytics:
    def test_missing_path_returns_nonzero(self, tmp_path) -> None:

        args = _parse(["analytics", "--reports", str(tmp_path / "nope.json")])

        assert cli._cmd_analytics(args) == 2

    def test_expands_directory_and_writes_reports(self, tmp_path, capsys) -> None:
        (tmp_path / "reports").mkdir()
        (tmp_path / "reports" / "a.json").write_text(
            json.dumps(
                {
                    "dataset": {"id": "ds-a", "name": "ds-a"},
                    "benchmark": {
                        "config": {"seed": 1, "threshold": 0.5},
                        "dataset": {"total": 100},
                        "cross_validation": {
                            "fold_count": 3,
                            "metrics": {"fusion": {"roc_auc": {"mean": 0.85}}},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        out_dir = tmp_path / "analytics"
        args = _parse(
            [
                "analytics",
                "--reports",
                str(tmp_path / "reports"),
                "--output-dir",
                str(out_dir),
            ]
        )

        assert cli._cmd_analytics(args) == 0
        assert (out_dir / "report.json").exists()
        assert (out_dir / "report.md").exists()
        assert (out_dir / "report.csv").exists()

    def test_incompatible_input_returns_nonzero_in_strict_mode(self, tmp_path, capsys) -> None:
        dup = tmp_path / "dup"
        dup.mkdir()
        payload = {
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
        (dup / "one.json").write_text(json.dumps(payload), encoding="utf-8")
        (dup / "two.json").write_text(json.dumps(payload), encoding="utf-8")

        args = _parse(["analytics", "--reports", str(dup)])

        assert cli._cmd_analytics(args) == 1
