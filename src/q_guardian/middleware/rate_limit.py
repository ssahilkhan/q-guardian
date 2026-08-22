"""Rate limiting middleware for Q-Guardian.

Applies a sliding-window request limit per client, backed by the
in-memory :class:`~q_guardian.security.auth.RateLimitService`. Limits are
configured through ``RATE_LIMIT_*`` settings and can be disabled entirely
for development or testing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from q_guardian.config.settings import get_settings
from q_guardian.exceptions.base import RateLimitError
from q_guardian.security.auth import get_rate_limit_service

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = structlog.get_logger("middleware.rate_limit")

FORWARDED_FOR_HEADER = "X-Forwarded-For"


def _client_identifier(request: Request) -> str:
    """Derive the rate limit key for a request.

    Prefers the first entry of ``X-Forwarded-For`` when present (reverse
    proxy deployments) and falls back to the direct client host.

    Args:
        request: The incoming HTTP request.

    Returns:
        A stable identifier for the calling client.
    """
    forwarded = request.headers.get(FORWARDED_FOR_HEADER)
    if forwarded:
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return first_hop
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiting middleware.

    Rejects requests exceeding ``RATE_LIMIT_REQUESTS`` within
    ``RATE_LIMIT_WINDOW_SECONDS`` per client with a structured 429
    response including a ``Retry-After`` header. Disabled entirely when
    ``RATE_LIMIT_ENABLED`` is false (the default).
    """

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Check the caller against the configured rate limit.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The downstream response, or 429 when the limit is exceeded.
        """
        from starlette.middleware.base import RequestResponseEndpoint
        from starlette.responses import JSONResponse

        call_next_typed: RequestResponseEndpoint = call_next  # type: ignore[assignment]

        settings = get_settings().rate_limit
        if not settings.enabled:
            return await call_next_typed(request)

        identifier = _client_identifier(request)
        allowed = await get_rate_limit_service().check_rate_limit(
            identifier,
            limit=settings.requests,
            window=settings.window_seconds,
        )
        if not allowed:
            retry_after = get_rate_limit_service().retry_after(
                identifier, window=settings.window_seconds
            )
            logger.warning(
                "rate_limit_response_429",
                identifier=identifier,
                path=str(request.url.path),
                retry_after=retry_after,
            )
            error = RateLimitError(
                message="Rate limit exceeded",
                details={"retry_after_seconds": retry_after},
            )
            return JSONResponse(
                status_code=error.status_code,
                content=error.to_dict(),
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next_typed(request)
