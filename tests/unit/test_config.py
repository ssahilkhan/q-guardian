"""Unit tests for configuration module."""

from __future__ import annotations

import os

import pytest


class TestAppSettings:
    """Tests for AppSettings configuration."""

    def test_default_app_name(self) -> None:
        """Verify default application name."""
        os.environ.pop("APP_NAME", None)
        from q_guardian.config.settings import AppSettings

        settings = AppSettings()
        assert settings.name == "Q-Guardian"

    def test_default_environment(self) -> None:
        """Verify default environment is development."""
        os.environ.pop("APP_ENVIRONMENT", None)
        from q_guardian.config.settings import AppSettings

        settings = AppSettings()
        assert settings.is_development is True

    def test_debug_mode_default(self) -> None:
        """Verify debug mode is enabled by default."""
        from q_guardian.config.settings import AppSettings

        settings = AppSettings()
        assert settings.debug is True


class TestDatabaseSettings:
    """Tests for DatabaseSettings configuration."""

    def test_default_database_name(self) -> None:
        """Verify default database name."""
        os.environ.pop("MONGODB_DATABASE", None)
        from q_guardian.config.settings import DatabaseSettings

        settings = DatabaseSettings()
        assert settings.database == "q_guardian"

    def test_default_pool_size(self) -> None:
        """Verify default connection pool sizes."""
        from q_guardian.config.settings import DatabaseSettings

        settings = DatabaseSettings()
        assert settings.min_pool_size == 1
        assert settings.max_pool_size == 10


class TestSecuritySettings:
    """Tests for SecuritySettings configuration."""

    def test_default_jwt_algorithm(self) -> None:
        """Verify default JWT algorithm."""
        from q_guardian.config.settings import SecuritySettings

        settings = SecuritySettings()
        assert settings.jwt_algorithm == "HS256"

    def test_default_api_key_header(self) -> None:
        """Verify default API key header name."""
        from q_guardian.config.settings import SecuritySettings

        settings = SecuritySettings()
        assert settings.api_key_header == "X-API-Key"
