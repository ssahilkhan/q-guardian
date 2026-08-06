"""Security headers middleware for Q-Guardian.

Adds standard security headers to all HTTP responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to HTTP responses.

    Adds standard security headers including X-Content-Type-Options,
    X-Frame-Options, X-XSS-Protection, and others.
    """

    SECURITY_HEADERS: ClassVar[dict[str, str]] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Permitted-Cross-Domain-Policies": "none",
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    }

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Process request and add security headers to response.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            Response with security headers added.
        """
        from starlette.middleware.base import RequestResponseEndpoint

        call_next_typed: RequestResponseEndpoint = call_next  # type: ignore[assignment]
        response = await call_next_typed(request)

        for header, value in self.SECURITY_HEADERS.items():
            response.headers[header] = value

        return response
