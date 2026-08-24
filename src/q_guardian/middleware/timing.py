"""Response timing middleware for Q-Guardian.

Measures and records the time taken to process each HTTP request.

Implemented as a plain ASGI middleware (rather than ``BaseHTTPMiddleware``)
so that it observes the same ``scope`` object mutated by the router; this is
what makes ``scope["route"]`` resolvable for per-route-template metrics.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from q_guardian.api.metrics import record_request

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger("middleware.timing")


def _resolve_route_template(scope: Scope) -> str:
    """Best-effort route-template lookup for cardinality-safe labels."""
    route = scope.get("route")
    explicit = str(getattr(route, "path", "") or "")
    template = explicit or str(scope.get("path", ""))
    if not explicit:
        # FastAPI >= 0.141 nests prefixed routes behind ``_IncludedRouter``,
        # leaving ``route.path`` empty; rebuild the template from the
        # matched path parameters instead of touching private APIs.
        for name, value in (scope.get("path_params") or {}).items():
            template = template.replace(str(value), "{" + str(name) + "}")
    return template or "unmatched"


class ResponseTimingMiddleware:
    """Middleware that measures, records and logs response times.

    Adds a X-Response-Time header to every response and feeds
    request counters/latency histograms into :mod:`q_guardian.api.metrics`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        start_time = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

                headers = list(message.get("headers", []))
                headers.append((b"x-response-time", f"{duration_ms}ms".encode("latin-1")))
                message = {**message, "headers": headers}

                route_template = _resolve_route_template(scope)
                method = scope.get("method", "?")
                path = scope.get("path", "?")
                record_request(
                    str(method),
                    route_template,
                    int(message.get("status", 0)),
                    duration_ms,
                )
                logger.debug(
                    "response_timing",
                    method=str(method),
                    path=str(path),
                    status_code=int(message.get("status", 0)),
                    duration_ms=duration_ms,
                )
            await send(message)

        await self._app(scope, receive, send_wrapper)
