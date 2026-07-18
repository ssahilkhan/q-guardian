"""Integration tests for API health and system endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRootEndpoint:
    """Tests for the root endpoint."""

    async def test_root_returns_200(self, client: AsyncClient) -> None:
        """Verify root endpoint returns 200."""
        response = await client.get("/")
        assert response.status_code == 200

    async def test_root_returns_app_info(self, client: AsyncClient) -> None:
        """Verify root endpoint returns application info."""
        response = await client.get("/")
        data = response.json()
        assert "application" in data
        assert "version" in data
        assert data["application"] == "Q-Guardian"


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    async def test_health_returns_200(self, client: AsyncClient) -> None:
        """Verify health endpoint returns 200."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_health_response_structure(self, client: AsyncClient) -> None:
        """Verify health response contains required fields."""
        response = await client.get("/api/v1/health")
        data = response.json()
        assert "status" in data
        assert "application" in data
        assert "version" in data
        assert "environment" in data
        assert "timestamp" in data

    async def test_health_has_correlation_id(self, client: AsyncClient) -> None:
        """Verify health response includes correlation ID header."""
        response = await client.get("/api/v1/health")
        assert "X-Correlation-ID" in response.headers


@pytest.mark.asyncio
class TestVersionEndpoint:
    """Tests for the system version endpoint."""

    async def test_version_returns_200(self, client: AsyncClient) -> None:
        """Verify version endpoint returns 200."""
        response = await client.get("/api/v1/system/version")
        assert response.status_code == 200

    async def test_version_response_structure(self, client: AsyncClient) -> None:
        """Verify version response contains required fields."""
        response = await client.get("/api/v1/system/version")
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "application" in data["data"]
        assert "version" in data["data"]
        assert "environment" in data["data"]
        assert "python_version" in data["data"]


@pytest.mark.asyncio
class TestStatusEndpoint:
    """Tests for the system status endpoint."""

    async def test_status_returns_200(self, client: AsyncClient) -> None:
        """Verify status endpoint returns 200."""
        response = await client.get("/api/v1/system/status")
        assert response.status_code == 200

    async def test_status_is_operational(self, client: AsyncClient) -> None:
        """Verify status response indicates operational."""
        response = await client.get("/api/v1/system/status")
        data = response.json()
        assert data["data"]["status"] == "operational"
