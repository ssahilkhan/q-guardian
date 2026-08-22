"""Tests for the ASGI application entrypoint (q_guardian.main).

The Docker image and deployment docs start the service with
``uvicorn src.q_guardian.main:app``. These tests verify that the
entrypoint module exposes a correctly configured FastAPI application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def test_main_exposes_app() -> None:
    """The entrypoint module must expose an ``app`` attribute."""
    from q_guardian import main

    assert hasattr(main, "app")
    assert main.app is not None


def test_main_app_is_fastapi_instance() -> None:
    """The exposed app must be a FastAPI instance."""
    from fastapi import FastAPI

    from q_guardian import main

    assert isinstance(main.app, FastAPI)


def test_main_app_routes_registered() -> None:
    """Critical routes must be registered on the entrypoint app.

    Route paths are verified through the OpenAPI schema, which reflects
    every registered endpoint regardless of router wrapping.
    """
    from q_guardian import main

    app: FastAPI = main.app
    schema = app.openapi()
    paths = set(schema.get("paths", {}))

    assert "/" in paths
    assert "/api/v1/health" in paths
    assert "/api/v1/system/version" in paths
    assert "/api/v1/system/status" in paths
    assert "/api/v1/analysis/scan" in paths


def test_main_app_docs_enabled() -> None:
    """OpenAPI documentation must be enabled on the entrypoint app."""
    from q_guardian import main

    assert main.app.docs_url == "/docs"
    assert main.app.openapi_url == "/openapi.json"


def test_main_app_title_and_version() -> None:
    """App metadata must identify Q-Guardian."""
    from q_guardian import main

    assert main.app.title == "Q-Guardian"
    assert main.app.version
