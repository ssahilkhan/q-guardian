"""CORS middleware configuration for Q-Guardian."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

from q_guardian.config.settings import get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI


def get_cors_middleware(app: FastAPI) -> None:
    """Add CORS middleware to the FastAPI application.

    Configures Cross-Origin Resource Sharing based on application settings.
    Supports configurable origins, methods, headers, and credentials.

    Args:
        app: The FastAPI application instance.
    """
    settings = get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
    )
