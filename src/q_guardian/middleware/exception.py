"""Exception logging middleware for Q-Guardian.

Catches and logs unhandled exceptions during request processing
before they reach the exception handlers.
"""

from __future__ import annotations

import traceback

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("middleware.exception")


class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs exceptions occurring during request handling.

    Captures unhandled exceptions, logs them with full context
    including stack trace, and re-raises them for the exception handlers.
    """

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Wrap request handling with exception logging.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The response from downstream handlers.

        Raises:
            Re-raises any exception after logging it.
        """
        from starlette.middleware.base import RequestResponseEndpoint

        call_next_typed: RequestResponseEndpoint = call_next  # type: ignore[assignment]

        try:
            return await call_next_typed(request)
        except Exception:
            logger.error(
                "unhandled_exception",
                method=request.method,
                path=str(request.url.path),
                traceback=traceback.format_exc(),
            )
            raise
