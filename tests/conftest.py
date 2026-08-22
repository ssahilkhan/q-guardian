"""Shared test configuration and fixtures for Q-Guardian.

Root conftest makes fixtures available to all test subdirectories.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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
    for making test HTTP requests. The client is unauthenticated;
    use ``authorized_client`` for protected endpoints.

    ASGITransport does not run FastAPI lifespan events, so a MongoDB
    client bound to this test's event loop is connected explicitly.
    Endpoints surface structured 503 errors when no server is reachable.

    Yields:
        AsyncClient instance connected to the test application.
    """
    from q_guardian.database import client as db_client_module

    # Motor clients bind to one event loop; reset the singleton so every
    # test gets a client attached to its own loop.
    await db_client_module.get_db_client().disconnect()
    db_client_module._client_instance = None
    database = db_client_module.get_db_client()
    with contextlib.suppress(Exception):
        await database.connect()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await database.disconnect()
        db_client_module._client_instance = None


@pytest_asyncio.fixture(scope="function")
async def auth_headers() -> dict[str, str]:
    """Bearer headers carrying a valid JWT access token."""
    from q_guardian.security.auth import get_jwt_service

    token = await get_jwt_service().create_access_token(
        {"sub": "integration-tester", "roles": ["admin"]}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def authorized_client(
    client: AsyncClient, auth_headers: dict[str, str]
) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client pre-configured with valid JWT credentials."""
    client.headers.update(auth_headers)
    yield client


@pytest.fixture
def api_key_headers() -> dict[str, str]:
    """Headers carrying a freshly provisioned, valid API key."""
    from q_guardian.config.settings import get_settings
    from q_guardian.security.auth import get_api_key_service

    raw_key, _record = get_api_key_service().generate_api_key(
        name="integration", owner="tests", roles=["service"]
    )
    return {get_settings().security.api_key_header: raw_key}


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
