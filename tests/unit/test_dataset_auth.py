"""Tests for the dataset authentication module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from q_guardian.benchmark.registry import DatasetSpec
from q_guardian.ml.datasets.auth import (
    AuthConfig,
    AuthProvider,
    DatasetAccessInfo,
    DatasetAccessType,
    DatasetAuthResolver,
    create_auth_resolver,
)


class TestAuthConfig:
    def test_from_env_with_token(self, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_test_token_123")
        config = AuthConfig.from_env()
        assert config.hf_token == "hf_test_token_123"
        assert config.token_env_var == "HF_TOKEN"

    def test_from_env_without_token(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        config = AuthConfig.from_env()
        assert config.hf_token is None

    def test_from_config_explicit_token(self):
        config = AuthConfig.from_config("hf_explicit_token")
        assert config.hf_token == "hf_explicit_token"

    def test_from_config_fallback_to_env(self, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_env_token")
        config = AuthConfig.from_config(None)
        assert config.hf_token == "hf_env_token"

    def test_from_config_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_env_token")
        config = AuthConfig.from_config("hf_explicit_token")
        assert config.hf_token == "hf_explicit_token"

    def test_resolve_token(self):
        config = AuthConfig(hf_token="hf_token_123")
        assert config.resolve_token() == "hf_token_123"

    def test_resolve_token_none(self):
        config = AuthConfig(hf_token=None)
        assert config.resolve_token() is None


class TestDatasetAuthResolver:
    def _make_public_spec(self) -> DatasetSpec:
        return DatasetSpec(
            dataset_id="public-dataset",
            name="Public Dataset",
            source="org/public-dataset",
            format="hf",
            requires_token=False,
        )

    def _make_gated_spec(self) -> DatasetSpec:
        return DatasetSpec(
            dataset_id="gated-dataset",
            name="Gated Dataset",
            source="org/gated-dataset",
            format="hf",
            requires_token=True,
            homepage="https://huggingface.co/datasets/org/gated-dataset",
        )

    def _make_local_spec(self) -> DatasetSpec:
        return DatasetSpec(
            dataset_id="local-dataset",
            name="Local Dataset",
            source="/path/to/local.jsonl",
            format="jsonl",
        )

    def test_classify_public_dataset(self):
        resolver = create_auth_resolver()
        spec = self._make_public_spec()
        info = resolver.classify_access(spec)

        assert info.access_type == DatasetAccessType.PUBLIC
        assert info.requires_token is False
        assert info.is_accessible is True
        assert info.needs_user_action is False

    def test_classify_gated_dataset_without_token(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        resolver = create_auth_resolver()
        spec = self._make_gated_spec()
        info = resolver.classify_access(spec)

        assert info.access_type == DatasetAccessType.GATED
        assert info.requires_token is True
        assert info.provider == AuthProvider.HUGGINGFACE
        assert info.is_accessible is False
        assert info.needs_user_action is True
        assert "gated" in info.message.lower()

    def test_classify_gated_dataset_with_token(self):
        resolver = create_auth_resolver("hf_test_token")
        spec = self._make_gated_spec()
        info = resolver.classify_access(spec)

        assert info.access_type == DatasetAccessType.AUTHENTICATED
        assert info.requires_token is True
        assert info.is_accessible is True
        assert info.needs_user_action is True  # Still need to accept terms

    def test_classify_gated_dataset_with_token_does_not_overclaim(self):
        """A configured token only classifies access; it never confirms content access.

        Repository metadata visibility must not be reported as actual dataset
        access. The guidance must remain conservative about remaining steps.
        """
        resolver = create_auth_resolver("hf_test_token")
        spec = self._make_gated_spec()
        info = resolver.classify_access(spec)

        assert info.access_type == DatasetAccessType.AUTHENTICATED
        message = info.message.lower()
        assert "complete any required" in message
        assert "approval" in message or "terms acceptance" in message
        assert "confirmed" not in message
        assert "granted" not in message
        assert "fully accessible" not in message

    def test_classify_local_dataset(self):
        resolver = create_auth_resolver()
        spec = self._make_local_spec()
        info = resolver.classify_access(spec)

        assert info.access_type == DatasetAccessType.PUBLIC
        assert info.requires_token is False
        assert "local" in info.message.lower()

    def test_validate_token_format_valid(self):
        resolver = create_auth_resolver("hf_12345678901234567890")
        is_valid, msg = resolver.validate_token()
        assert is_valid is True

    def test_validate_token_format_invalid_short(self):
        resolver = create_auth_resolver("hf_short")
        is_valid, msg = resolver.validate_token()
        assert is_valid is False
        assert "too short" in msg.lower()

    def test_validate_token_format_invalid_prefix(self):
        resolver = create_auth_resolver("invalid_token_12345678901234567890")
        is_valid, msg = resolver.validate_token()
        assert is_valid is False
        assert "invalid" in msg.lower()

    def test_validate_token_no_token(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        resolver = create_auth_resolver()
        is_valid, msg = resolver.validate_token()
        assert is_valid is False
        assert "no token" in msg.lower()

    def test_get_auth_headers_with_token(self):
        resolver = create_auth_resolver("hf_test_token")
        headers = resolver.get_auth_headers()
        assert headers == {"Authorization": "Bearer hf_test_token"}

    def test_get_auth_headers_without_token(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        resolver = create_auth_resolver()
        headers = resolver.get_auth_headers()
        assert headers == {}

    def test_check_dataset_access_public(self):
        resolver = create_auth_resolver()
        spec = self._make_public_spec()
        info = resolver.check_dataset_access(spec, allow_offline=True)

        assert info.access_type == DatasetAccessType.PUBLIC

    def test_check_dataset_access_gated_offline(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        resolver = create_auth_resolver()
        spec = self._make_gated_spec()
        info = resolver.check_dataset_access(spec, allow_offline=True)

        assert info.access_type == DatasetAccessType.GATED

    def test_check_dataset_access_gated_with_token_offline(self):
        resolver = create_auth_resolver("hf_test_token")
        spec = self._make_gated_spec()
        info = resolver.check_dataset_access(spec, allow_offline=True)

        assert info.access_type == DatasetAccessType.AUTHENTICATED

    def test_check_dataset_access_public_no_token_online(self):
        resolver = create_auth_resolver()
        spec = self._make_public_spec()
        info = resolver.check_dataset_access(spec, allow_offline=False)

        assert info.access_type == DatasetAccessType.PUBLIC
        assert info.requires_token is False
        assert info.is_accessible is True

    def test_check_dataset_access_public_with_token_online(self):
        # Regression: a genuinely public dataset must remain PUBLIC even when
        # an HF_TOKEN is configured (a token does not make it gated).
        resolver = create_auth_resolver("hf_test_token_12345678901234567890")
        spec = self._make_public_spec()
        info = resolver.check_dataset_access(spec, allow_offline=False)

        assert info.access_type == DatasetAccessType.PUBLIC
        assert info.requires_token is False
        assert info.is_accessible is True
        assert info.needs_user_action is False

    def test_check_dataset_access_public_with_token_offline(self):
        resolver = create_auth_resolver("hf_test_token_12345678901234567890")
        spec = self._make_public_spec()
        info = resolver.check_dataset_access(spec, allow_offline=True)

        assert info.access_type == DatasetAccessType.PUBLIC

    def test_check_dataset_access_gated_no_token_online(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        resolver = create_auth_resolver()
        spec = self._make_gated_spec()
        info = resolver.check_dataset_access(spec, allow_offline=False)

        assert info.access_type == DatasetAccessType.GATED
        assert info.requires_token is True
        assert info.is_accessible is False
        assert info.needs_user_action is True

    def test_check_dataset_access_gated_with_token_online(self):
        resolver = create_auth_resolver("hf_test_token_12345678901234567890")
        spec = self._make_gated_spec()
        info = resolver.check_dataset_access(spec, allow_offline=False)

        assert info.access_type == DatasetAccessType.AUTHENTICATED
        assert info.requires_token is True
        assert info.provider == AuthProvider.HUGGINGFACE
        assert info.is_accessible is True
        assert info.needs_user_action is True

    def test_check_dataset_access_local_online(self):
        resolver = create_auth_resolver("hf_test_token_12345678901234567890")
        spec = self._make_local_spec()
        info = resolver.check_dataset_access(spec, allow_offline=False)

        assert info.access_type == DatasetAccessType.PUBLIC
        assert "local" in info.message.lower()


class TestCreateAuthResolver:
    def test_factory_function(self):
        resolver = create_auth_resolver("hf_factory_token")
        assert isinstance(resolver, DatasetAuthResolver)
        assert resolver.token == "hf_factory_token"

    def test_factory_uses_env(self, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_env_factory")
        resolver = create_auth_resolver()
        assert resolver.token == "hf_env_factory"


class TestDatasetAccessInfo:
    def test_is_accessible_public(self):
        info = DatasetAccessInfo(
            dataset_id="test",
            access_type=DatasetAccessType.PUBLIC,
        )
        assert info.is_accessible is True

    def test_is_accessible_authenticated(self):
        info = DatasetAccessInfo(
            dataset_id="test",
            access_type=DatasetAccessType.AUTHENTICATED,
        )
        assert info.is_accessible is True

    def test_is_accessible_gated(self):
        info = DatasetAccessInfo(
            dataset_id="test",
            access_type=DatasetAccessType.GATED,
        )
        assert info.is_accessible is False

    def test_needs_user_action_gated(self):
        info = DatasetAccessInfo(
            dataset_id="test",
            access_type=DatasetAccessType.GATED,
        )
        assert info.needs_user_action is True

    def test_needs_user_action_private(self):
        info = DatasetAccessInfo(
            dataset_id="test",
            access_type=DatasetAccessType.PRIVATE,
        )
        assert info.needs_user_action is True

    def test_needs_user_action_public(self):
        info = DatasetAccessInfo(
            dataset_id="test",
            access_type=DatasetAccessType.PUBLIC,
        )
        assert info.needs_user_action is False


class TestAuthConfigIntegration:
    def test_cli_priority_over_env(self, monkeypatch):
        """Test that explicit token takes priority over env var."""
        monkeypatch.setenv("HF_TOKEN", "hf_from_env")
        config = AuthConfig.from_config("hf_from_cli")
        assert config.hf_token == "hf_from_cli"

    def test_env_fallback_when_no_cli(self, monkeypatch):
        """Test that env var is used when no explicit token."""
        monkeypatch.setenv("HF_TOKEN", "hf_from_env")
        config = AuthConfig.from_config(None)
        assert config.hf_token == "hf_from_env"

    def test_custom_env_var(self, monkeypatch):
        """Test custom environment variable name."""
        monkeypatch.setenv("CUSTOM_HF_TOKEN", "hf_custom")
        config = AuthConfig.from_env(token_env_var="CUSTOM_HF_TOKEN")
        assert config.hf_token == "hf_custom"
        assert config.token_env_var == "CUSTOM_HF_TOKEN"