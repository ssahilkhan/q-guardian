"""Test fixtures for Q-Guardian.

Shared pytest fixtures used across unit and integration tests.
"""

from __future__ import annotations

from typing import AsyncGenerator, Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from q_guardian.api.app import create_app
from q_guardian.config.settings import Environment, get_settings


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
