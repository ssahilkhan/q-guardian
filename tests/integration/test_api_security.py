"""Integration tests for API-level security behavior.

Covers security headers, CORS enforcement, correlation ID handling,
and structured error responses served by the live application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

ALLOWED_ORIGIN = "http://localhost:3000"
DISALLOWED_ORIGIN = "https://evil.example.com"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "no-store, no-cache, must-revalidate",
}


@pytest.mark.asyncio
class TestSecurityHeaders:
    """Verify every response carries the standard security headers."""

    async def test_headers_on_success_response(self, authorized_client: AsyncClient) -> None:
        response = await authorized_client.get("/api/v1/health")
        assert response.status_code == 200
        for header, value in SECURITY_HEADERS.items():
            assert response.headers.get(header) == value, header

    async def test_headers_on_error_response(self, client: AsyncClient) -> None:
        """Security headers must also be applied to error responses."""
        response = await client.get("/api/v1/definitely-not-a-route")
        assert response.status_code == 404
        for header, value in SECURITY_HEADERS.items():
            assert response.headers.get(header) == value, header


@pytest.mark.asyncio
class TestCors:
    """Verify CORS allows configured origins and rejects others."""

    async def test_allowed_origin_gets_cors_headers(self, authorized_client: AsyncClient) -> None:
        response = await authorized_client.get("/api/v1/health", headers={"Origin": ALLOWED_ORIGIN})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
        assert response.headers.get("access-control-allow-credentials") == "true"

    async def test_disallowed_origin_gets_no_cors_headers(
        self, authorized_client: AsyncClient
    ) -> None:
        response = await authorized_client.get(
            "/api/v1/health", headers={"Origin": DISALLOWED_ORIGIN}
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    async def test_preflight_allowed_origin(self, client: AsyncClient) -> None:
        response = await client.options(
            "/api/v1/analysis/scan",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN

    async def test_preflight_disallowed_origin_rejected(self, client: AsyncClient) -> None:
        response = await client.options(
            "/api/v1/analysis/scan",
            headers={
                "Origin": DISALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
class TestCorrelationIDPropagation:
    """Verify correlation IDs are generated and honored."""

    async def test_correlation_id_generated_when_absent(self, client: AsyncClient) -> None:
        first = await client.get("/")
        second = await client.get("/")
        id_first = first.headers["X-Correlation-ID"]
        id_second = second.headers["X-Correlation-ID"]
        assert id_first and id_second
        assert id_first != id_second

    async def test_client_provided_correlation_id_preserved(self, client: AsyncClient) -> None:
        correlation_id = "test-corr-123456"
        response = await client.get("/", headers={"X-Correlation-ID": correlation_id})
        assert response.headers["X-Correlation-ID"] == correlation_id


@pytest.mark.asyncio
class TestStructuredErrors:
    """Verify API errors use the structured envelope."""

    async def test_validation_error_shape(self, authorized_client: AsyncClient) -> None:
        """Auth runs before body validation; valid auth yields the 422 envelope."""
        response = await authorized_client.post("/api/v1/analysis/scan", json={})
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["message"]
        assert body["error"]["details"]["validation_errors"]

    async def test_validation_requires_authentication(self, client: AsyncClient) -> None:
        """Invalid body without credentials is rejected as unauthenticated."""
        response = await client.post("/api/v1/analysis/scan", json={})
        assert response.status_code == 401

    async def test_unknown_route_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/no-such-endpoint")
        assert response.status_code == 404


@pytest.mark.asyncio
class TestApiDocsExposed:
    """Verify OpenAPI schema remains reachable."""

    async def test_openapi_schema_available(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"]
        assert "/api/v1/health" in schema["paths"]
