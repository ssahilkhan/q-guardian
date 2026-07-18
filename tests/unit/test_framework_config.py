"""Unit tests for framework configuration."""

from __future__ import annotations

import pytest

from q_guardian.framework.config import (
    DashboardConfig,
    FrameworkConfig,
    PluginConfig,
    PolicyConfig,
    PromptScannerConfig,
    QuantumConfig,
    RuntimeConfig,
)


class TestPluginConfig:
    """Tests for PluginConfig."""

    def test_defaults(self) -> None:
        """Verify default values."""
        config = PluginConfig()
        assert config.enabled is True
        assert config.priority == 0

    def test_extra_fields_allowed(self) -> None:
        """Verify extra fields are accepted."""
        config = PluginConfig(custom_field="value")
        assert config.custom_field == "value"


class TestRuntimeConfig:
    """Tests for RuntimeConfig."""

    def test_defaults(self) -> None:
        """Verify default values."""
        config = RuntimeConfig()
        assert config.max_concurrent_agents == 100
        assert config.request_timeout_seconds == 30
        assert config.enable_caching is True


class TestPolicyConfig:
    """Tests for PolicyConfig."""

    def test_defaults(self) -> None:
        """Verify default values."""
        config = PolicyConfig()
        assert config.enforcement_mode == "enforce"
        assert config.default_policy == "allow"


class TestQuantumConfig:
    """Tests for QuantumConfig."""

    def test_defaults(self) -> None:
        """Verify default values."""
        config = QuantumConfig()
        assert config.enabled is False
        assert config.backend == "simulator"


class TestDashboardConfig:
    """Tests for DashboardConfig."""

    def test_defaults(self) -> None:
        """Verify default values."""
        config = DashboardConfig()
        assert config.enabled is False
        assert config.refresh_interval_seconds == 30


class TestPromptScannerConfig:
    """Tests for PromptScannerConfig."""

    def test_defaults(self) -> None:
        """Verify default values."""
        config = PromptScannerConfig()
        assert config.enabled is True
        assert config.sensitivity == "medium"


class TestFrameworkConfig:
    """Tests for FrameworkConfig."""

    def test_defaults(self) -> None:
        """Verify default configuration."""
        config = FrameworkConfig()
        assert config.plugins.enabled is True
        assert config.runtime.max_concurrent_agents == 100
        assert config.quantum.enabled is False

    def test_get_plugin_config_empty(self) -> None:
        """Verify empty config for unknown plugin."""
        config = FrameworkConfig()
        assert config.get_plugin_config("unknown") == {}

    def test_get_plugin_config(self) -> None:
        """Verify plugin-specific config retrieval."""
        config = FrameworkConfig(
            plugin_configs={"my-plugin": {"sensitivity": "high"}}
        )
        assert config.get_plugin_config("my-plugin") == {"sensitivity": "high"}

    def test_from_settings(self) -> None:
        """Verify FrameworkConfig creation from Module 1 settings."""
        config = FrameworkConfig.from_settings(None)
        assert isinstance(config, FrameworkConfig)
