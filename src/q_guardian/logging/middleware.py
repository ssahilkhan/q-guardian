"""Request logging middleware for Q-Guardian.

Logs incoming requests and outgoing responses with timing information,
correlation IDs, and relevant metadata.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from q_guardian.core.constants import CORRELATION_ID_HEADER
from q_guardian.utils.uuid_utils import generate_correlation_id

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


logger = structlog.get_logger("middleware.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs every HTTP request and response.

    Adds correlation IDs, measures response times, and logs
    structured request/response data.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request, log details, and pass to next handler.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The response from downstream handlers.
        """
        correlation_id = request.headers.get(CORRELATION_ID_HEADER, generate_correlation_id())
        request.state.correlation_id = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=str(request.url.path),
        )

        start_time = time.perf_counter()

        logger.info(
            "request_started",
            client_host=request.client.host if request.client else "unknown",
            query_params=str(request.query_params),
            user_agent=request.headers.get("user-agent", ""),
        )

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        response.headers[CORRELATION_ID_HEADER] = correlation_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response
