"""Response timing middleware for Q-Guardian.

Measures and logs the time taken to process each HTTP request.
"""

from __future__ import annotations

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("middleware.timing")


class ResponseTimingMiddleware(BaseHTTPMiddleware):
    """Middleware that measures and logs response times.

    Adds a X-Response-Time header to every response and logs
    the duration for monitoring and performance analysis.
    """

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Measure request processing time.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            Response with timing header added.
        """
        from starlette.middleware.base import RequestResponseEndpoint

        call_next_typed: RequestResponseEndpoint = call_next  # type: ignore[assignment]

        start_time = time.perf_counter()
        response = await call_next_typed(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        logger.debug(
            "response_timing",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response
