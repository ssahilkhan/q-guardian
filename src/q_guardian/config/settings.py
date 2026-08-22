"""Application configuration using pydantic-settings.

Reads environment variables from .env files and supports
multiple environment profiles (development, testing, production).
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported application environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """General application settings."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    name: str = Field(default="Q-Guardian", description="Application name")
    version: str = Field(default="1.1.0", description="Application version")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT, description="Runtime environment"
    )
    debug: bool = Field(default=True, description="Enable debug mode")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")
    log_dir: str = Field(default="logs", description="Log file directory")

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.environment == Environment.TESTING

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION


class DatabaseSettings(BaseSettings):
    """MongoDB database configuration."""

    model_config = SettingsConfigDict(
        env_prefix="MONGODB_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    url: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URL")
    database: str = Field(default="q_guardian", description="Database name")
    min_pool_size: int = Field(default=1, description="Minimum connection pool size")
    max_pool_size: int = Field(default=10, description="Maximum connection pool size")
    timeout_ms: int = Field(default=5000, description="Connection timeout in milliseconds")

    @property
    def client_kwargs(self) -> dict[str, Any]:
        """Return kwargs for Motor async client."""
        return {
            "serverSelectionTimeoutMS": self.timeout_ms,
            "minPoolSize": self.min_pool_size,
            "maxPoolSize": self.max_pool_size,
        }


class SecuritySettings(BaseSettings):
    """Security and authentication configuration."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    secret_key: str = Field(
        default="change-me-to-a-random-secret-key",
        description="Application secret key",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expiration_minutes: int = Field(default=30, description="JWT token expiration")
    jwt_refresh_expiration_days: int = Field(default=7, description="JWT refresh expiration")
    api_key_header: str = Field(default="X-API-Key", description="API key header name")
    admin_username: str = Field(default="admin", description="Admin username for token issuance")
    admin_password: str = Field(
        default="change-me-admin-password",
        description="Admin password for token issuance",
    )

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable API rate limiting")
    rate_limit_requests: int = Field(default=100, description="Max requests per window per client")
    rate_limit_window_seconds: int = Field(default=60, description="Rate limit window in seconds")

    @field_validator("secret_key", "admin_password")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        """Validate that insecure default credentials have been changed."""
        insecure_defaults = ("change-me-to-a-random-secret-key", "change-me-admin-password")
        if value in insecure_defaults:
            import os

            if os.getenv("ENVIRONMENT") == "production":
                msg = "SECRET_KEY and ADMIN_PASSWORD must be changed in production!"
                raise ValueError(msg)
        return value


class CORSSettings(BaseSettings):
    """CORS configuration."""

    model_config = SettingsConfigDict(
        env_prefix="CORS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins",
    )
    allow_credentials: bool = Field(default=True, description="Allow credentials")
    allow_methods: list[str] = Field(default=["*"], description="Allowed HTTP methods")
    allow_headers: list[str] = Field(default=["*"], description="Allowed headers")


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    level: str = Field(default="INFO", description="Global log level")
    dir: str = Field(default="logs", description="Log directory path")
    max_bytes: int = Field(default=10_485_760, description="Max log file size (10MB)")
    backup_count: int = Field(default=30, description="Number of log backups to keep")
    format: str = Field(default="json", description="Log format: json or console")


@lru_cache(maxsize=1)
def get_settings() -> _SettingsComposite:
    """Return a composite settings object.

    This function is cached to ensure settings are loaded only once.
    Uses lru_cache to act as a singleton for the settings object.

    Returns:
        _SettingsComposite: Combined settings from all categories.
    """
    return _SettingsComposite()


class _SettingsComposite:
    """Composite settings object that aggregates all configuration categories.

    Provides a single access point for all application settings.
    """

    def __init__(self) -> None:
        self.app = AppSettings()
        self.database = DatabaseSettings()
        self.security = SecuritySettings()
        self.cors = CORSSettings()
        self.logging = LoggingSettings()
