"""Centralized exception handling framework for Q-Guardian.

Provides a hierarchy of application-specific exceptions and
exception handlers for FastAPI integration.
"""

from q_guardian.exceptions.base import (
    ApplicationException,
    DatabaseException,
    ExternalServiceException,
    SecurityException,
    ValidationException,
)
from q_guardian.exceptions.handlers import (
    application_exception_handler,
    register_exception_handlers,
    validation_exception_handler,
)

__all__ = [
    "ApplicationException",
    "DatabaseException",
    "ExternalServiceException",
    "SecurityException",
    "ValidationException",
    "application_exception_handler",
    "register_exception_handlers",
    "validation_exception_handler",
]
