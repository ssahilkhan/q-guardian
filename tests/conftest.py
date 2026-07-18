"""Shared test configuration and fixtures for Q-Guardian.

Root conftest makes fixtures available to all test subdirectories.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import AsyncGenerator, Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def _set_test_environment() -> None:
    """Automatically set the testing environment for all tests."""
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["DEBUG"] = "true"
    os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
    os.environ["MONGODB_DATABASE"] = "q_guardian_test"
    yield
    os.environ.pop("ENVIRONMENT", None)
    os.environ.pop("DEBUG", None)
    os.environ.pop("MONGODB_URL", None)
    os.environ.pop("MONGODB_DATABASE", None)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Specify the async backend for pytest-asyncio.

    Returns:
        The async backend name.
    """
    return "asyncio"


@pytest.fixture(scope="session")
def app() -> Any:
    """Create a FastAPI application for testing.

    Returns:
        The configured FastAPI application instance.
    """
    from q_guardian.api.app import create_app

    return create_app()


@pytest_asyncio.fixture(scope="function")
async def client(app: Any) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP test client.

    Provides an httpx AsyncClient connected to the FastAPI app
    for making test HTTP requests.

    Yields:
        AsyncClient instance connected to the test application.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def settings() -> Any:
    """Get application settings for testing.

    Returns:
        The composite settings object.
    """
    from q_guardian.config.settings import get_settings

    return get_settings()


@pytest.fixture
def sample_uuid() -> str:
    """Generate a sample UUID for testing.

    Returns:
        A UUID v4 string.
    """
    from q_guardian.utils.uuid_utils import generate_uuid

    return generate_uuid()


@pytest.fixture
def sample_correlation_id() -> str:
    """Generate a sample correlation ID for testing.

    Returns:
        A 12-character correlation ID string.
    """
    from q_guardian.utils.uuid_utils import generate_correlation_id

    return generate_correlation_id()
