"""Integration tests for API rate limiting.

Exercises :class:`~q_guardian.middleware.rate_limit.RateLimitMiddleware`
against a live app instance configured with a low request limit. Each
test uses a unique ``X-Forwarded-For`` identity so the shared in-memory
RateLimitService state never leaks between tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

LIMIT = 3


@pytest_asyncio.fixture
async def limited_context(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[tuple[AsyncClient, Any], None]:
    """Build an app with rate limiting enabled at limit={LIMIT}.

    Clears the settings cache so the new env vars take effect, then
    clears it again on teardown to avoid polluting other tests.
    """
    from q_guardian.api.app import create_app
    from q_guardian.config.settings import get_settings

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", str(LIMIT))
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    get_settings.cache_clear()
    try:
        from q_guardian.security.auth import get_jwt_service

        access = await get_jwt_service().create_access_token({"sub": "rate-limit-tester"})
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Bearer {access}"},
        ) as ac:
            yield ac, app
    finally:
        get_settings.cache_clear()


def _identity(index: int) -> dict[str, str]:
    """Unique per-test client identity."""
    return {"X-Forwarded-For": f"10.{index}.0.{index}"}


@pytest.mark.asyncio
async def test_requests_within_limit_pass(limited_context) -> None:
    client, _app = limited_context
    headers = _identity(1)

    for expected in range(LIMIT):
        response = await client.get("/api/v1/health", headers=headers)
        assert response.status_code == 200, f"request {expected + 1} of {LIMIT}"


@pytest.mark.asyncio
async def test_request_over_limit_returns_429(limited_context) -> None:
    client, _app = limited_context
    headers = _identity(2)

    for _ in range(LIMIT):
        assert (await client.get("/api/v1/health", headers=headers)).status_code == 200

    blocked = await client.get("/api/v1/health", headers=headers)
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"]["code"] == "RATE_LIMIT_ERROR"
    assert body["error"]["message"]


@pytest.mark.asyncio
async def test_429_includes_retry_after_header(limited_context) -> None:
    client, _app = limited_context
    headers = _identity(3)

    for _ in range(LIMIT):
        await client.get("/api/v1/health", headers=headers)
    blocked = await client.get("/api/v1/health", headers=headers)

    assert blocked.status_code == 429
    retry_after = int(blocked.headers["Retry-After"])
    assert 1 <= retry_after <= 60


@pytest.mark.asyncio
async def test_429_carries_security_headers(limited_context) -> None:
    client, _app = limited_context
    headers = _identity(4)

    for _ in range(LIMIT):
        await client.get("/api/v1/health", headers=headers)
    blocked = await client.get("/api/v1/health", headers=headers)

    assert blocked.status_code == 429
    assert blocked.headers.get("X-Frame-Options") == "DENY"
    assert blocked.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.asyncio
async def test_limits_are_per_client(limited_context) -> None:
    client, _app = limited_context
    exhausted = _identity(5)
    fresh = _identity(6)

    for _ in range(LIMIT):
        assert (await client.get("/api/v1/health", headers=exhausted)).status_code == 200
    assert (await client.get("/api/v1/health", headers=exhausted)).status_code == 429

    other_client = await client.get("/api/v1/health", headers=fresh)
    assert other_client.status_code == 200


@pytest.mark.asyncio
async def test_forwarded_for_first_hop_is_key(limited_context) -> None:
    client, _app = limited_context
    chain = "203.0.113.7, 70.41.3.18"

    for _ in range(LIMIT):
        assert (
            await client.get("/api/v1/health", headers={"X-Forwarded-For": chain})
        ).status_code == 200
    blocked = await client.get("/api/v1/health", headers={"X-Forwarded-For": chain})
    assert blocked.status_code == 429

    # A different first hop is treated as a different client.
    other = await client.get(
        "/api/v1/health", headers={"X-Forwarded-For": "198.51.100.9, 70.41.3.18"}
    )
    assert other.status_code == 200


@pytest.mark.asyncio
async def test_rate_limiting_disabled_by_default(client: AsyncClient) -> None:
    """Without RATE_LIMIT_ENABLED the middleware is a pass-through."""
    token_headers: dict[str, str] = {}
    from q_guardian.security.auth import get_jwt_service

    access = await get_jwt_service().create_access_token({"sub": "no-limit-tester"})
    token_headers.update({"Authorization": f"Bearer {access}"})
    client.headers.update(token_headers)

    for _ in range(LIMIT * 2):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
