"""Integration tests for the /metrics endpoint (F-10 fix)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from q_guardian.api.metrics import reset_metrics

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    reset_metrics()


@pytest.mark.asyncio
class TestMetricsEndpoint:
    async def test_metrics_returns_200_text(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")

    async def test_metrics_exposes_uptime_gauge(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert "qg_process_uptime_seconds" in response.text

    async def test_metrics_counts_requests_via_middleware(
        self, authorized_client: AsyncClient
    ) -> None:
        await authorized_client.get("/api/v1/health")
        response = await authorized_client.get("/metrics")
        assert (
            'qg_http_requests_total{method="GET",route="/api/v1/health",status="200"} 1'
            in response.text
        )

    async def test_metrics_hidden_from_openapi(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        assert "/metrics" not in response.json()["paths"]
