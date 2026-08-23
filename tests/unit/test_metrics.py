"""Unit tests for the dependency-free /metrics registry (F-10 fix)."""

from __future__ import annotations

import pytest

from q_guardian.api.metrics import (
    record_request,
    record_scan_decision,
    render_metrics,
    reset_metrics,
    snapshot,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    reset_metrics()


class TestRecordRequest:
    def test_increments_request_counter(self) -> None:
        record_request("GET", "/api/v1/health", 200, 12.5)
        record_request("GET", "/api/v1/health", 200, 8.0)
        http = snapshot()["http"]
        assert http["GET|/api/v1/health|200"]["count"] == 2

    def test_tracks_duration_sum_and_max(self) -> None:
        record_request("POST", "/api/v1/analyze", 200, 100.0)
        record_request("POST", "/api/v1/analyze", 200, 40.0)
        record_request("POST", "/api/v1/analyze", 500, 20.0)
        http = snapshot()["http"]
        assert http["POST|/api/v1/analyze|200"]["total_ms"] == pytest.approx(140.0)
        assert http["POST|/api/v1/analyze|200"]["max_ms"] == pytest.approx(100.0)

    def test_records_literal_route_as_given(self) -> None:
        # Route templating/fallback ("unmatched") is a middleware concern.
        record_request("GET", "/nope/xyz/abc", 404, 1.0)
        assert "GET|/nope/xyz/abc|404" in snapshot()["http"]


class TestScanDecisions:
    def test_counts_by_decision(self) -> None:
        record_scan_decision("allow")
        record_scan_decision("allow")
        record_scan_decision("block")
        assert snapshot()["scans"] == {"allow": 2, "block": 1}

    def test_reset_clears_everything(self) -> None:
        record_request("GET", "/", 200, 1.0)
        record_scan_decision("block")
        reset_metrics()
        snap = snapshot()
        assert snap["http"] == {}
        assert snap["scans"] == {}


class TestRenderMetrics:
    def test_renders_uptime_and_counters(self) -> None:
        record_request("GET", "/api/v1/health", 200, 5.0)
        record_scan_decision("allow")
        text = render_metrics()
        assert "# HELP qg_process_uptime_seconds" in text
        assert 'qg_http_requests_total{method="GET",route="/api/v1/health",status="200"} 1' in text
        assert 'qg_scans_total{decision="allow"} 1' in text
        assert (
            'qg_http_request_duration_milliseconds_sum{method="GET",route="/api/v1/health",'
            'status="200"} 5.00' in text
        )

    def test_output_is_prometheus_text_format(self) -> None:
        text = render_metrics()
        assert text.startswith("# HELP ")
        assert "\n# TYPE " in text
        assert text.endswith("\n")

    def test_empty_registry_still_renders_uptime(self) -> None:
        assert "qg_process_uptime_seconds" in render_metrics()
