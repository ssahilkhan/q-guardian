"""Tests for the dataset CLI commands with authentication."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from q_guardian.cli import _cmd_dataset_check_access, _cmd_dataset_auth_status, _resolve_token
from q_guardian.benchmark.registry import DatasetRegistry
from q_guardian.training.config import TrainingPipelineConfig


class TestDatasetCheckAccessCLI:
    def test_check_access_public_dataset(self, capsys):
        config = TrainingPipelineConfig()
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
            "dataset_ids": ["deepset-prompt-injections"],
            "offline": True,
        })()
        exit_code = _cmd_dataset_check_access(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "PUBLIC" in captured.out
        assert "deepset-prompt-injections" in captured.out

    def test_check_access_gated_dataset_offline(self, capsys, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        config = TrainingPipelineConfig()
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
            "dataset_ids": ["wildjailbreak"],
            "offline": True,
        })()
        exit_code = _cmd_dataset_check_access(args)
        captured = capsys.readouterr()
        # Should fail because gated dataset without token
        assert exit_code == 1
        assert "GATED" in captured.out
        assert "wildjailbreak" in captured.out

    def test_check_access_gated_dataset_with_token_offline(self, capsys):
        config = TrainingPipelineConfig(hf_token=SecretStr("hf_test_token_12345678901234567890"))
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
            "dataset_ids": ["wildjailbreak"],
            "offline": True,
        })()
        import q_guardian.cli as cli_module
        original_load = cli_module._load_config
        cli_module._load_config = lambda _: config
        try:
            exit_code = _cmd_dataset_check_access(args)
            captured = capsys.readouterr()
            assert exit_code == 0
            assert "AUTHENTICATED" in captured.out
            assert "wildjailbreak" in captured.out
        finally:
            cli_module._load_config = original_load

    def test_check_access_invalid_dataset(self, capsys):
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
            "dataset_ids": ["invalid-dataset-id"],
            "offline": True,
        })()
        exit_code = _cmd_dataset_check_access(args)
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "INVALID" in captured.out

    def test_check_access_multiple_datasets(self, capsys):
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
            "dataset_ids": ["deepset-prompt-injections", "wildjailbreak", "dolly-benign"],
            "offline": True,
        })()
        exit_code = _cmd_dataset_check_access(args)
        captured = capsys.readouterr()
        assert "deepset-prompt-injections" in captured.out
        assert "wildjailbreak" in captured.out
        assert "dolly-benign" in captured.out

    def test_check_access_public_dataset_with_token_online(self, capsys):
        """Regression: a public dataset must stay PUBLIC online even with a token."""
        config = TrainingPipelineConfig(hf_token=SecretStr("hf_test_token_12345678901234567890"))
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
            "dataset_ids": ["deepset-prompt-injections"],
            "offline": False,
        })()
        import q_guardian.cli as cli_module
        original_load = cli_module._load_config
        cli_module._load_config = lambda _: config
        try:
            exit_code = _cmd_dataset_check_access(args)
            captured = capsys.readouterr()
            assert exit_code == 0
            assert "PUBLIC" in captured.out
            assert "AUTHENTICATED" not in captured.out
        finally:
            cli_module._load_config = original_load

    def test_check_access_gated_dataset_no_token_online(self, capsys, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
            "dataset_ids": ["wildjailbreak"],
            "offline": False,
        })()
        exit_code = _cmd_dataset_check_access(args)
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "GATED" in captured.out
        assert "wildjailbreak" in captured.out

    def test_check_access_gated_dataset_with_token_online(self, capsys):
        config = TrainingPipelineConfig(hf_token=SecretStr("hf_test_token_12345678901234567890"))
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
            "dataset_ids": ["wildjailbreak"],
            "offline": False,
        })()
        import q_guardian.cli as cli_module
        original_load = cli_module._load_config
        cli_module._load_config = lambda _: config
        try:
            exit_code = _cmd_dataset_check_access(args)
            captured = capsys.readouterr()
            assert exit_code == 0
            assert "AUTHENTICATED" in captured.out
        finally:
            cli_module._load_config = original_load


class TestDatasetAuthStatusCLI:
    def test_auth_status_no_token(self, capsys, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        config = TrainingPipelineConfig()
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
        })()
        import q_guardian.cli as cli_module
        original_load = cli_module._load_config
        cli_module._load_config = lambda _: config
        try:
            exit_code = _cmd_dataset_auth_status(args)
            captured = capsys.readouterr()
            assert exit_code == 0
            assert "Token configured: NO" in captured.out
            assert "HF_TOKEN" in captured.out
            assert "Security notes" in captured.out
        finally:
            cli_module._load_config = original_load

    def test_auth_status_with_token(self, capsys):
        config = TrainingPipelineConfig(hf_token=SecretStr("hf_test_token_12345678901234567890"))
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
        })()
        import q_guardian.cli as cli_module
        original_load = cli_module._load_config
        cli_module._load_config = lambda _: config
        try:
            exit_code = _cmd_dataset_auth_status(args)
            captured = capsys.readouterr()
            assert exit_code == 0
            assert "Token configured: YES" in captured.out
            assert "Token format valid: YES" in captured.out
            # Security: no portion of the token may be exposed in output
            assert "hf_test_" not in captured.out
            assert "hf_test_token_12345678901234567890" not in captured.out
        finally:
            cli_module._load_config = original_load

    def test_auth_status_never_exposes_token_fragments(self, capsys):
        """No prefix, no fragment, no masked-but-identifiable portion may leak."""
        config = TrainingPipelineConfig(hf_token=SecretStr("hf_super_secret_token_value_99"))
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
        })()
        import q_guardian.cli as cli_module
        original_load = cli_module._load_config
        cli_module._load_config = lambda _: config
        try:
            exit_code = _cmd_dataset_auth_status(args)
            captured = capsys.readouterr()
            assert exit_code == 0
            assert "hf_super_secret_token_value_99" not in captured.out
            assert "hf_super" not in captured.out
            assert "super_secret" not in captured.out
            assert "value_99" not in captured.out
            assert "..." not in captured.out
        finally:
            cli_module._load_config = original_load

    def test_auth_status_invalid_token_format(self, capsys, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        config = TrainingPipelineConfig(hf_token=SecretStr("invalid_token"))
        args = type("Args", (), {
            "config": None,
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
        })()
        import q_guardian.cli as cli_module
        original_load = cli_module._load_config
        cli_module._load_config = lambda _: config
        try:
            exit_code = _cmd_dataset_auth_status(args)
            captured = capsys.readouterr()
            assert exit_code == 0
            assert "Token format valid: NO" in captured.out
        finally:
            cli_module._load_config = original_load

    def test_auth_status_from_config(self, capsys):
        config = TrainingPipelineConfig(hf_token=SecretStr("hf_config_token_12345678901234567890"))
        args = type("Args", (), {
            "config": "dummy.json",
            "seed": None,
            "max_samples": None,
            "output_dir": None,
            "hf_token": None,
        })()
        import q_guardian.cli as cli_module
        original_load = cli_module._load_config
        cli_module._load_config = lambda _: config
        try:
            exit_code = _cmd_dataset_auth_status(args)
            captured = capsys.readouterr()
            assert exit_code == 0
            assert "Token configured: YES" in captured.out
        finally:
            cli_module._load_config = original_load


class TestResolveTokenPriority:
    def test_env_overrides_config(self, monkeypatch):
        """Environment variable takes priority over config."""
        monkeypatch.setenv("HF_TOKEN", "hf_from_env")
        config = TrainingPipelineConfig(hf_token=SecretStr("hf_from_config"))
        from q_guardian.cli import _resolve_token

        token = _resolve_token(config)
        # Env var takes priority
        assert token == "hf_from_env"

    def test_env_used_when_no_config(self, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_from_env")
        config = TrainingPipelineConfig()
        from q_guardian.cli import _resolve_token

        token = _resolve_token(config)
        assert token == "hf_from_env"

    def test_config_used_when_no_env(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        config = TrainingPipelineConfig(hf_token=SecretStr("hf_from_config"))
        from q_guardian.cli import _resolve_token

        token = _resolve_token(config)
        assert token == "hf_from_config"

    def test_none_when_no_token_anywhere(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        config = TrainingPipelineConfig(hf_token=None)
        from q_guardian.cli import _resolve_token

        token = _resolve_token(config)
        assert token is None