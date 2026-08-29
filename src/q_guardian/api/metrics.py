"""Lightweight in-process metrics registry with Prometheus text exposition.

Dependency-free alternative to ``prometheus_client`` covering the signals
needed for basic operational monitoring: HTTP request counts/latency per
route template and analysis-scan decision counters.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_started_at = time.time()
_lock = threading.Lock()

# (method, route_template, status_code) -> {"count": int, "total_ms": float, "max_ms": float}
_http_stats: dict[tuple[str, str, int], dict[str, float]] = {}
_scan_decisions: dict[str, int] = {}


def reset_metrics() -> None:
    """Clear all recorded metrics. Intended for tests."""
    global _http_stats, _scan_decisions
    with _lock:
        _http_stats = {}
        _scan_decisions = {}


def record_request(method: str, route: str, status_code: int, duration_ms: float) -> None:
    """Record one handled HTTP request.

    Args:
        method: HTTP method (GET, POST, ...).
        route: Route template (e.g. ``/api/v1/analysis/scan``); use the
            literal path when no route matched.
        status_code: Response status code.
        duration_ms: Wall-clock handling time in milliseconds.
    """
    key = (method, route, int(status_code))
    with _lock:
        stats = _http_stats.setdefault(key, {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
        stats["count"] += 1
        stats["total_ms"] += duration_ms
        stats["max_ms"] = max(stats["max_ms"], duration_ms)


def record_scan_decision(decision: str) -> None:
    """Record one completed prompt-analysis outcome."""
    with _lock:
        key = (decision or "unknown").lower()
        _scan_decisions[key] = _scan_decisions.get(key, 0) + 1


def render_metrics() -> str:
    """Render all metrics in Prometheus text exposition format."""
    lines: list[str] = []

    uptime = max(0.0, time.time() - _started_at)
    lines.append("# HELP qg_process_uptime_seconds Process uptime in seconds.")
    lines.append("# TYPE qg_process_uptime_seconds gauge")
    lines.append(f"qg_process_uptime_seconds {uptime:.3f}")

    with _lock:
        total_requests = sum(int(s["count"]) for s in _http_stats.values())
        lines.append("# HELP qg_http_requests_total Total HTTP requests handled.")
        lines.append("# TYPE qg_http_requests_total counter")
        for (method, route, status), stats in sorted(_http_stats.items()):
            label = f'method="{method}",route="{route}",status="{status}"'
            lines.append(f"qg_http_requests_total{{{label}}} {int(stats['count'])}")

        if total_requests:
            lines.append(
                "# HELP qg_http_request_duration_milliseconds "
                "Cumulative/per-request-max handling time."
            )
            lines.append("# TYPE qg_http_request_duration_milliseconds counter")
            for (method, route, status), stats in sorted(_http_stats.items()):
                label = f'method="{method}",route="{route}",status="{status}"'
                lines.append(
                    f"qg_http_request_duration_milliseconds_sum{{{label}}} {stats['total_ms']:.2f}"
                )
                lines.append(
                    f"qg_http_request_duration_milliseconds_max{{{label}}} {stats['max_ms']:.2f}"
                )

        if _scan_decisions:
            lines.append("# HELP qg_scans_total Total prompt analyses by decision.")
            lines.append("# TYPE qg_scans_total counter")
            for decision, count in sorted(_scan_decisions.items()):
                lines.append(f'qg_scans_total{{decision="{decision}"}} {count}')

    return "\n".join(lines) + "\n"


def snapshot() -> dict[str, Any]:
    """Return a JSON-serialisable view of current metrics (for debugging/tests)."""
    with _lock:
        return {
            "uptime_seconds": round(max(0.0, time.time() - _started_at), 3),
            "http": {
                "|".join((method, route, str(status))): {
                    "count": int(stats["count"]),
                    "total_ms": round(stats["total_ms"], 2),
                    "max_ms": round(stats["max_ms"], 2),
                }
                for (method, route, status), stats in sorted(_http_stats.items())
            },
            "scans": dict(_scan_decisions),
        }


def observability() -> dict[str, Any]:
    """Return a live operational view for the console observability surface.

    Aggregates the in-process request counters per route template and the
    per-decision scan counters recorded by the response-timing middleware.

    Returns:
        A JSON-serialisable dict with ``routes`` (list), ``scan_decisions``,
        ``total_requests``, ``error_count``, ``error_rate``, ``uptime_seconds``
        and ``generated_at``.
    """
    now = time.time()
    with _lock:
        total_requests = sum(int(stats["count"]) for stats in _http_stats.values())
        error_count = sum(
            int(stats["count"])
            for (_, _, status), stats in _http_stats.items()
            if 500 <= int(status) < 600
        )
        routes: list[dict[str, Any]] = []
        by_route: dict[tuple[str, str], dict[str, float]] = {}
        for (method, route, _status), stats in _http_stats.items():
            key = (method, route)
            agg = by_route.setdefault(key, {"count": 0.0, "total_ms": 0.0, "max_ms": 0.0})
            agg["count"] += int(stats["count"])
            agg["total_ms"] += stats["total_ms"]
            agg["max_ms"] = max(agg["max_ms"], stats["max_ms"])
        for (method, route), agg in sorted(by_route.items()):
            count = int(agg["count"])
            routes.append(
                {
                    "method": method,
                    "route": route,
                    "count": count,
                    "avg_ms": round(agg["total_ms"] / count, 2) if count else 0.0,
                    "max_ms": round(agg["max_ms"], 2),
                }
            )
        error_rate = round(error_count / total_requests, 4) if total_requests else 0.0
        return {
            "generated_at": now,
            "uptime_seconds": round(max(0.0, now - _started_at), 3),
            "total_requests": total_requests,
            "error_count": error_count,
            "error_rate": error_rate,
            "routes": routes,
            "scan_decisions": dict(_scan_decisions),
        }
