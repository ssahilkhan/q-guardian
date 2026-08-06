"""Correlation ID middleware for Q-Guardian.

Ensures every request has a unique correlation ID for distributed tracing.
If the client provides one, it is preserved; otherwise a new one is generated.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from q_guardian.core.constants import CORRELATION_ID_HEADER

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = structlog.get_logger("middleware.correlation")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware that ensures every request has a correlation ID.

    The correlation ID is used for request tracing across services
    and is included in all log entries for the request lifecycle.
    """

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Add correlation ID to request state and response headers.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            Response with correlation ID header.
        """
        from starlette.middleware.base import RequestResponseEndpoint

        call_next_typed: RequestResponseEndpoint = call_next  # type: ignore[assignment]

        correlation_id = request.headers.get(CORRELATION_ID_HEADER)
        if not correlation_id:
            correlation_id = uuid.uuid4().hex[:12]

        request.state.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        response = await call_next_typed(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id

        return response
