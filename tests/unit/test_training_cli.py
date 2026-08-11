"""Unit tests for the q-guardian command-line interface."""

from __future__ import annotations

from pathlib import Path

import q_guardian.benchmark.download as benchmark_download
import q_guardian.benchmark.validate as benchmark_validate
import q_guardian.cli as cli
from q_guardian.benchmark.registry import DatasetRegistry
from q_guardian.training.config import TrainingPipelineConfig
from q_guardian.training.manifest import DatasetCounts, DatasetManifest


def _parse(argv: list[str]):
    return cli._build_parser().parse_args(argv)


class TestParser:
    def test_dataset_prepare_parser(self) -> None:
        args = _parse(["dataset", "prepare", "--seed", "7", "--datasets", "a", "b"])

        assert args.func is cli._cmd_dataset_prepare
        assert args.seed == 7
        assert args.datasets == ["a", "b"]

    def test_dataset_validate_parser(self) -> None:
        args = _parse(["dataset", "validate"])

        assert args.func is cli._cmd_dataset_validate

    def test_model_train_parser(self) -> None:
        args = _parse(
            [
                "model",
                "train",
                "--epochs",
                "3",
                "--batch-size",
                "16",
                "--learning-rate",
                "0.01",
            ]
        )

        assert args.func is cli._cmd_model_train
        assert args.epochs == 3
        assert args.batch_size == 16
        assert args.learning_rate == 0.01

    def test_model_evaluate_parser(self) -> None:
        args = _parse(["model", "evaluate", "--threshold", "0.7"])

        assert args.func is cli._cmd_model_evaluate
        assert args.threshold == 0.7

    def test_benchmark_parser_defaults(self) -> None:
        args = _parse(["benchmark"])

        assert args.func is cli._cmd_benchmark
        assert args.k == 3
        assert args.no_quantum is False
        assert args.no_ablate is False

    def test_benchmark_parser_flags(self) -> None:
        args = _parse(["benchmark", "--k", "5", "--no-quantum", "--no-ablate"])

        assert args.k == 5
        assert args.no_quantum is True
        assert args.no_ablate is True


class TestLoadConfig:
    def test_defaults_when_no_config(self) -> None:
        args = _parse(["dataset", "prepare"])
        config = cli._load_config(args)

        assert config.seed == 42
        assert isinstance(config, TrainingPipelineConfig)

    def test_overrides_from_cli(self, tmp_path) -> None:
        args = _parse(
            [
                "model",
                "train",
                "--seed",
                "9",
                "--output-dir",
                str(tmp_path / "run"),
                "--max-samples",
                "50",
                "--epochs",
                "3",
                "--batch-size",
                "16",
                "--learning-rate",
                "0.01",
            ]
        )
        config = cli._load_config(args)

        assert config.seed == 9
        assert config.output_dir == tmp_path / "run"
        assert config.max_samples_per_class == 50
        assert config.model.epochs == 3
        assert config.model.batch_size == 16
        assert config.model.learning_rate == 0.01

    def test_loads_from_config_file(self, tmp_path) -> None:
        config_file = tmp_path / "training.json"
        config_file.write_text('{"seed": 5, "model": {"n_estimators": 25}}', encoding="utf-8")
        args = _parse(["benchmark", "--config", str(config_file)])

        config = cli._load_config(args)
        assert config.seed == 5
        assert config.model.n_estimators == 25


class TestResolveToken:
    def test_env_var_preferred(self, monkeypatch) -> None:
        monkeypatch.setenv("HF_TOKEN", "env-token")
        config = TrainingPipelineConfig(hf_token="config-token")

        assert cli._resolve_token(config) == "env-token"

    def test_config_token_used_when_no_env(self, monkeypatch) -> None:
        monkeypatch.delenv("HF_TOKEN", raising=False)
        config = TrainingPipelineConfig(hf_token="config-token")

        assert cli._resolve_token(config) == "config-token"

    def test_none_when_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("HF_TOKEN", raising=False)

        assert cli._resolve_token(TrainingPipelineConfig()) is None


class _FakePrepared:
    def __init__(self) -> None:
        self.output_dir = Path("out")
        counts = {"local-ds": DatasetCounts(source="local-ds", requested=10, loaded=8, final=6)}
        self.manifest = DatasetManifest(
            seed=42,
            generated_at="now",
            groups={"train": ["local-ds"], "validation": [], "test": [], "external_eval": []},
            datasets=counts,
            pools={"train": {"samples": 6, "benign": 3, "malicious": 3}},
        )
        self.leakage_report = _FakeLeakage()
        self.train = ["a", "b", "c"]
        self.validation = []


class _FakeLeakage:
    total_leaked = 0


class TestCommandDatasetPrepare:
    def test_prepare_writes_counts(self, tmp_path, monkeypatch) -> None:
        calls: dict = {}

        class _FakePipeline:
            def __init__(self, *, downloader) -> None:
                calls["downloader"] = downloader

            def prepare(self, config, output_dir, include_only=None) -> _FakePrepared:
                calls["output_dir"] = output_dir
                calls["include_only"] = include_only
                return _FakePrepared()

        class _FakeDownloader:
            def __init__(self, *, token) -> None:
                calls["token"] = token

        monkeypatch.setattr(cli, "DatasetPreparationPipeline", _FakePipeline)
        monkeypatch.setattr(benchmark_download, "DatasetDownloader", _FakeDownloader)
        args = _parse(["dataset", "prepare", "--output-dir", str(tmp_path / "run")])

        assert cli._cmd_dataset_prepare(args) == 0
        assert calls["output_dir"] == tmp_path / "run"
        assert calls["include_only"] is None
        assert calls["token"] is None


class TestCommandDatasetValidate:
    def test_validate_returns_zero_on_success(self, tmp_path, monkeypatch) -> None:
        class _FakeDownloader:
            def __init__(self, *, token) -> None:
                pass

            def download(self, spec):
                return {}

        class _FakeValidator:
            def validate(self, spec, split_paths):
                return _FakeValidation()

        class _FakeValidation:
            def __init__(self) -> None:
                self.total = 0
                self.valid_rows = 0
                self.labels: dict = {}
                self.issues: list = []

        monkeypatch.setattr(benchmark_download, "DatasetDownloader", _FakeDownloader)
        monkeypatch.setattr(benchmark_validate, "DatasetValidator", _FakeValidator)
        monkeypatch.setattr(
            cli.DatasetRecordPreprocessor, "preprocess", lambda self, spec, split_paths: ([], 0)
        )
        args = _parse(["dataset", "validate"])

        assert cli._cmd_dataset_validate(args) == 0


class TestCommandModelTrain:
    def test_train_prepares_when_splits_missing(self, tmp_path, monkeypatch) -> None:
        prepared_calls: dict = {}
        train_calls: dict = {}

        class _FakePipeline:
            def __init__(self, *, downloader) -> None:
                pass

            def prepare(self, config, output_dir, include_only=None) -> _FakePrepared:
                prepared_calls["output_dir"] = output_dir
                return _FakePrepared()

        class _FakeTrainer:
            def train(self, config, prepared, *, max_samples_per_class=None) -> _FakeRun:
                train_calls["max_samples_per_class"] = max_samples_per_class
                return _FakeRun(config.output_dir)

        class _FakeRun:
            def __init__(self, output_dir: Path) -> None:
                self.elapsed_seconds = 1.5
                self.checkpoint_dir = output_dir / "model"
                self.output_dir = output_dir
                self.training_log_path = output_dir / "training_log.txt"

        class _FakeDownloader:
            def __init__(self, *, token) -> None:
                pass

        monkeypatch.setattr(cli, "DatasetPreparationPipeline", _FakePipeline)
        monkeypatch.setattr(cli, "TrainingPipeline", _FakeTrainer)
        monkeypatch.setattr(benchmark_download, "DatasetDownloader", _FakeDownloader)
        args = _parse(["model", "train", "--output-dir", str(tmp_path / "run")])

        assert cli._cmd_model_train(args) == 0
        assert prepared_calls["output_dir"] == tmp_path / "run"
        assert train_calls["max_samples_per_class"] is None

    def test_train_reuses_existing_splits(self, tmp_path, monkeypatch) -> None:
        run_dir = tmp_path / "run"
        (run_dir / "splits").mkdir(parents=True)
        (run_dir / "splits" / "train.jsonl").write_text(
            '{"text": "a", "label": 0, "source": "x"}\n', encoding="utf-8"
        )
        prepare_called = {"value": False}

        class _FakePipeline:
            def __init__(self, *, downloader) -> None:
                pass

            def prepare(self, config, output_dir, include_only=None) -> _FakePrepared:
                prepare_called["value"] = True
                return _FakePrepared()

        class _FakeTrainer:
            def train(self, config, prepared, *, max_samples_per_class=None) -> _FakeRun:
                assert len(prepared.train) == 1
                return _FakeRun(config.output_dir)

        class _FakeRun:
            def __init__(self, output_dir: Path) -> None:
                self.elapsed_seconds = 1.0
                self.checkpoint_dir = output_dir / "model"
                self.output_dir = output_dir
                self.training_log_path = output_dir / "training_log.txt"

        monkeypatch.setattr(cli, "DatasetPreparationPipeline", _FakePipeline)
        monkeypatch.setattr(cli, "TrainingPipeline", _FakeTrainer)
        args = _parse(["model", "train", "--output-dir", str(run_dir)])

        assert cli._cmd_model_train(args) == 0
        assert prepare_called["value"] is False


class TestCommandModelEvaluate:
    def test_no_checkpoint_returns_nonzero(self, tmp_path) -> None:
        args = _parse(["model", "evaluate", "--output-dir", str(tmp_path / "missing")])

        assert cli._cmd_model_evaluate(args) == 1


class TestCommandBenchmark:
    def test_benchmark_writes_reports(self, tmp_path, monkeypatch) -> None:
        class _FakeReport:
            def as_dict(self) -> dict:
                return {"benchmark": {}}

            def provider_metrics(self) -> dict:
                return {"fusion": {"roc_auc": {"mean": 0.85}}}

        class _FakeRunner:
            def __init__(self, *, registry, downloader, benchmark_kwargs) -> None:
                self.benchmark_kwargs = benchmark_kwargs

            def run_all(self, dataset_ids, k, seed, threshold, ablate, progress) -> dict:
                return {"local-ds": _FakeReport()}

        monkeypatch.setattr(cli, "BenchmarkRunner", _FakeRunner)
        out_dir = tmp_path / "out"
        args = _parse(["benchmark", "--datasets", "local-ds", "--k", "4", "--output", str(out_dir)])

        assert cli._cmd_benchmark(args) == 0
        assert (out_dir / "local-ds.json").exists()
        assert (out_dir / "local-ds.md").exists()

    def test_benchmark_defaults_to_all_public(self, tmp_path, monkeypatch) -> None:
        seen: dict = {}

        class _FakeReport:
            def as_dict(self) -> dict:
                return {"benchmark": {}}

            def provider_metrics(self) -> dict:
                return {"fusion": {"roc_auc": {"mean": 0.5}}}

        class _FakeRunner:
            def __init__(self, *, registry, downloader, benchmark_kwargs) -> None:
                seen["registry"] = registry
                seen["quantum"] = benchmark_kwargs["quantum"]

            def run_all(self, dataset_ids, k, seed, threshold, ablate, progress) -> dict:
                seen["dataset_ids"] = dataset_ids
                return {}

        monkeypatch.setattr(cli, "BenchmarkRunner", _FakeRunner)
        args = _parse(["benchmark", "--output", str(tmp_path / "out")])

        assert cli._cmd_benchmark(args) == 0
        assert seen["dataset_ids"] == DatasetRegistry.builtin().public_ids()
        assert seen["quantum"] is True

    def test_benchmark_no_quantum_flag(self, tmp_path, monkeypatch) -> None:
        seen: dict = {}

        class _FakeRunner:
            def __init__(self, *, registry, downloader, benchmark_kwargs) -> None:
                seen["quantum"] = benchmark_kwargs["quantum"]

            def run_all(self, dataset_ids, k, seed, threshold, ablate, progress) -> dict:
                return {}

        monkeypatch.setattr(cli, "BenchmarkRunner", _FakeRunner)
        args = _parse(["benchmark", "--no-quantum", "--output", str(tmp_path / "out")])

        assert cli._cmd_benchmark(args) == 0
        assert seen["quantum"] is False
