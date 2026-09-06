"""FastAPI exception handlers for Q-Guardian.

Registers global exception handlers that convert application exceptions
into structured JSON API responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from q_guardian.exceptions.base import ApplicationError, ValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastapi import FastAPI, Request


def _safe_error_list(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Return validation errors with any non-JSON-safe context removed.

    Pydantic embeds the raised exception (e.g. a ``ValueError``) in the
    ``ctx`` of a custom validator error. That object is not JSON
    serializable, so only the string ``ctx`` values (if any) survive;
    the exception itself is dropped.
    """
    safe: list[dict[str, Any]] = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        ctx = entry.get("ctx")
        if isinstance(ctx, dict):
            clean_ctx = {
                key: value
                for key, value in ctx.items()
                if isinstance(value, (str, int, float, bool, type(None)))
            }
            entry["ctx"] = clean_ctx or None
        entry.pop("input", None)
        safe.append(entry)
    return safe


async def application_exception_handler(request: Request, exc: ApplicationError) -> JSONResponse:
    """Handle ApplicationError and return structured JSON response.

    Args:
        request: The incoming HTTP request.
        exc: The application exception that was raised.

    Returns:
        JSONResponse with structured error details.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle FastAPI request validation errors.

    Args:
        request: The incoming HTTP request.
        exc: The validation error from FastAPI/Pydantic.

    Returns:
        JSONResponse with structured validation error details.
    """
    details: dict[str, Any] = {"validation_errors": _safe_error_list(exc.errors())}
    exception = ValidationError(
        message="Request validation failed",
        details=details,
    )
    return JSONResponse(
        status_code=exception.status_code,
        content=exception.to_dict(),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions.

    Args:
        request: The incoming HTTP request.
        exc: The unhandled exception.

    Returns:
        JSONResponse with generic error details.
    """
    exception = ApplicationError(
        message="Internal server error",
        code="INTERNAL_ERROR",
        status_code=500,
        details={"type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=exception.status_code,
        content=exception.to_dict(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    app.add_exception_handler(
        ApplicationError,
        application_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, general_exception_handler)
