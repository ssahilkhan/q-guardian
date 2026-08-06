"""Framework configuration for Q-Guardian.

Provides per-plugin and per-subsystem configuration classes
with validation, serialization, and future YAML/JSON loading support.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PluginConfig(BaseModel):
    """Base configuration for plugin-specific settings.

    Plugins extend this class with their own fields. The base
    provides common toggles for all plugins.
    """

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True, description="Whether the plugin is enabled")
    priority: int = Field(default=0, description="Plugin execution priority")


class RuntimeConfig(BaseModel):
    """Runtime behavior configuration."""

    max_concurrent_agents: int = Field(default=100, description="Maximum concurrent agent sessions")
    request_timeout_seconds: int = Field(default=30, description="Request timeout in seconds")
    enable_caching: bool = Field(default=True, description="Enable response caching")


class PolicyConfig(BaseModel):
    """Policy engine configuration."""

    enforcement_mode: str = Field(
        default="enforce",
        description="Policy enforcement mode: enforce, audit, or disabled",
    )
    default_policy: str = Field(default="allow", description="Default policy action")


class QuantumConfig(BaseModel):
    """Quantum computing configuration."""

    enabled: bool = Field(default=False, description="Enable quantum analysis")
    backend: str = Field(default="simulator", description="Quantum backend name")


class DashboardConfig(BaseModel):
    """Security dashboard configuration."""

    enabled: bool = Field(default=False, description="Enable the dashboard")
    refresh_interval_seconds: int = Field(default=30, description="Dashboard refresh interval")


class PromptScannerConfig(BaseModel):
    """Prompt scanner configuration."""

    enabled: bool = Field(default=True, description="Enable prompt scanning")
    sensitivity: str = Field(default="medium", description="Scanning sensitivity level")


class FrameworkConfig(BaseModel):
    """Aggregate framework configuration.

    Contains all sub-configurations. Supports loading from
    environment variables, dicts, and future YAML/JSON files.
    """

    model_config = ConfigDict(extra="allow")

    plugins: PluginConfig = Field(default_factory=PluginConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    quantum: QuantumConfig = Field(default_factory=QuantumConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    prompt_scanner: PromptScannerConfig = Field(default_factory=PromptScannerConfig)

    plugin_configs: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-plugin configuration overrides keyed by plugin name",
    )

    @classmethod
    def from_settings(cls, settings: Any) -> FrameworkConfig:
        """Create FrameworkConfig from Module 1 settings.

        Args:
            settings: The _SettingsComposite from Module 1 config.

        Returns:
            FrameworkConfig populated from Module 1 settings.
        """
        data: dict[str, Any] = {}

        if hasattr(settings, "app"):
            app = settings.app
            if hasattr(app, "debug"):
                data["runtime"] = {"enable_caching": not app.debug}

        if hasattr(settings, "logging"):
            logging_settings = settings.logging
            if hasattr(logging_settings, "level"):
                data.setdefault("runtime", {})["log_level"] = logging_settings.level

        return cls(**data)

    def get_plugin_config(self, plugin_name: str) -> dict[str, Any]:
        """Get configuration overrides for a specific plugin.

        Args:
            plugin_name: The plugin name.

        Returns:
            Plugin-specific configuration dictionary.
        """
        return self.plugin_configs.get(plugin_name, {})

    async def load_from_file(self, path: str) -> FrameworkConfig:
        """Load configuration from a JSON or YAML file.

        Args:
            path: Path to the configuration file.

        Returns:
            Self after loading configuration.

        Note:
            YAML loading requires PyYAML to be installed.
            This is a placeholder for future implementation.
        """
        import json
        from pathlib import Path

        file_path = Path(path)
        if file_path.suffix == ".json":
            data = json.loads(file_path.read_text(encoding="utf-8"))
            for key, value in data.items():
                if hasattr(self, key):
                    setattr(self, key, value)
        elif file_path.suffix in (".yaml", ".yml"):
            try:
                import yaml

                data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
                for key, value in data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)
            except ImportError:
                msg = "PyYAML is required for YAML configuration loading"
                raise ImportError(msg) from None

        return self
