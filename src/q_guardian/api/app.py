"""FastAPI application factory for Q-Guardian.

Creates and configures the FastAPI application with all middleware,
exception handlers, routes, and lifecycle events.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from q_guardian.api.v1.router import api_v1_router
from q_guardian.config.settings import get_settings
from q_guardian.core.constants import API_V1_PREFIX, APP_DESCRIPTION, APP_TITLE, APP_VERSION
from q_guardian.database.client import get_db_client
from q_guardian.exceptions.handlers import register_exception_handlers
from q_guardian.logging.config import setup_logging
from q_guardian.middleware.correlation import CorrelationIDMiddleware
from q_guardian.middleware.exception import ExceptionLoggingMiddleware
from q_guardian.middleware.timing import ResponseTimingMiddleware
from q_guardian.security.cors import get_cors_middleware
from q_guardian.security.headers import SecurityHeadersMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = structlog.get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown events.

    On startup:
    - Configures logging
    - Connects to MongoDB
    - Logs application readiness

    On shutdown:
    - Disconnects from MongoDB
    - Logs shutdown

    Args:
        app: The FastAPI application instance.

    Yields:
        None during the application lifecycle.
    """
    settings = get_settings()
    setup_logging(
        log_level=settings.app.log_level,
        log_dir=settings.app.log_dir,
        log_format=settings.logging.format,
    )

    logger.info(
        "application_starting",
        name=settings.app.name,
        version=settings.app.version,
        environment=settings.app.environment.value,
    )

    db_client = get_db_client()
    try:
        await db_client.connect()
    except Exception as e:
        logger.warning("mongodb_connection_failed", error=str(e))

    logger.info(
        "application_started",
        name=settings.app.name,
        version=settings.app.version,
    )

    yield

    logger.info("application_shutting_down")
    await db_client.disconnect()
    logger.info("application_shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    This is the application factory function. It assembles all
    components: middleware, routes, exception handlers, and lifecycle.

    Returns:
        Configured FastAPI application instance.
    """
    get_settings()

    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    _register_middleware(app)
    register_exception_handlers(app)
    _register_routes(app)

    return app


def _register_middleware(app: FastAPI) -> None:
    """Register all middleware on the application in correct order.

    Middleware executes in reverse registration order, so the first
    registered middleware wraps the outermost layer.

    Args:
        app: The FastAPI application instance.
    """
    settings = get_settings()

    if not settings.app.is_production:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

    get_cors_middleware(app)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ExceptionLoggingMiddleware)
    app.add_middleware(ResponseTimingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)


def _register_routes(app: FastAPI) -> None:
    """Register all API routes on the application.

    Args:
        app: The FastAPI application instance.
    """
    settings = get_settings()

    @app.get("/", tags=["Root"])
    async def root() -> dict[str, str]:
        """Root endpoint providing basic application information.

        Returns:
            Dictionary with application name and documentation links.
        """
        return {
            "application": settings.app.name,
            "version": settings.app.version,
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/api/v1/health",
        }

    app.include_router(api_v1_router, prefix=API_V1_PREFIX)

    _register_ui(app)


def _register_ui(app: FastAPI) -> None:
    """Mount the console static UI.

    The console is a dependency-free single-page app (HTML/CSS/JS) shipped
    as package data and served by the same application that runs the API.

    Args:
        app: The FastAPI application instance.
    """
    static_dir = Path(__file__).resolve().parent.parent / "ui" / "static"
    if static_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="ui")
